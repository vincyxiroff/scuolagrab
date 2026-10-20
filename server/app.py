'''scuolagrab web server.

Everything stays on the server: the users, their session cookie and the tokens
of the school platforms are kept in a SQLite database (server/data/server.db),
the browser only receives an httpOnly session cookie.

Run it with:
	python3 server/app.py                                  # 84.8.252.233:8749
	python3 server/app.py --host 0.0.0.0 --port 8749
'''

import argparse
import importlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import dependencies

missing = dependencies.missingmodules()
if missing or not dependencies.chromiuminstalled():
	print("Missing dependencies: run")
	print("  python3 -m pip install -r requirements.txt")
	print("  python3 -m playwright install chromium")
	print("then start the server again.")
	sys.exit(1)

import config
import db
import pymupdf as fitz

STATIC = Path(__file__).resolve().parent / "static"
FILES = ROOT / "files"

# Keep in sync with utils.services: only the services tested with a real account
SERVICES = {"bsm": "bSmart", "hbs": "Mondadori HUB Scuola", "plc": "Sanoma My Place"}

settings = config.getconfig()
COOKIE = "sbg_session"
# Set SBG_SECURE=1 when the server is published over HTTPS (reverse proxy): the cookie then gets the Secure flag
SECURE = os.environ.get("SBG_SECURE", "").lower() in ("1", "true", "yes")
jobs = {}
jobslock = threading.Lock()

def service(name):
	if name not in SERVICES:
		raise ValueError("Unknown service")
	return importlib.import_module("services." + name)

def savepdf(servicename, token, bookid, data, progress):
	'''Build the pdf exactly like the cli does, without touching the local tinydb'''
	module = service(servicename)
	pdf = module.downloadbook(token, bookid, data, progress)
	now = fitz.get_pdf_now()
	author = settings.get(servicename, "Author", fallback="").strip()
	metadata = {
		"producer": "PyMuPDF " + fitz.version[0],
		"format": "PDF 1.7",
		"encryption": None,
		"author": author,
		"modDate": now,
		"keywords": "none",
		"title": data.get("title", ""),
		"creationDate": now,
		"creator": "scuolagrab-server",
		"subject": "none",
	}
	pdf.set_metadata(metadata)
	path = FILES / servicename / (str(bookid) + ".pdf")
	path.parent.mkdir(parents=True, exist_ok=True)
	progress(99, "Saving pdf")
	if settings.getboolean(servicename, "EzSave", fallback=True):
		pdf.ez_save(path)
	elif settings.getboolean(servicename, "Compress", fallback=False):
		pdf.save(path, garbage=settings.getint(servicename, "Garbage", fallback=3), clean=settings.getboolean(servicename, "Clean", fallback=True))
	else:
		pdf.save(path)
	return path, len(pdf)

def runjob(jobid):
	with jobslock:
		job = jobs[jobid]
	try:
		module = service(job["service"])
		token = db.gettoken(job["userid"], job["service"])
		library = module.library(token)
		for item in job["items"]:
			bookid = item["bookid"]
			data = library.get(bookid)
			if data is None:
				item["status"] = "error"
				item["error"] = "book no longer in the library"
				continue
			item["title"] = data.get("title", item["title"])
			item["status"] = "downloading"

			def progress(percent, status=""):
				item["progress"] = max(0, min(100, int(percent)))
				if status:
					item["message"] = status

			try:
				path, pages = savepdf(job["service"], token, bookid, data, progress)
			except Exception as e:
				# the error stays in the job for the page, the traceback goes to the journal (stderr)
				traceback.print_exc()
				item["status"] = "error"
				item["error"] = str(e) or e.__class__.__name__
				continue
			db.savebook(job["userid"], job["service"], bookid, data.get("title", bookid), pages, str(path.relative_to(ROOT)))
			item["status"] = "done"
			item["progress"] = 100
			item["pages"] = pages
	except Exception as e:
		traceback.print_exc()
		with jobslock:
			job["error"] = str(e) or e.__class__.__name__
		for item in job["items"]:
			if item["status"] in ("queued", "downloading"):
				item["status"] = "error"
				item["error"] = "download aborted"
	finally:
		with jobslock:
			job["state"] = "done"
			job["ended"] = time.time()

class Handler(BaseHTTPRequestHandler):
	server_version = "scuolagrab"
	protocol_version = "HTTP/1.1"

	# ---------- helpers ----------

	def sendjson(self, data, status=200, headers=None):
		body = json.dumps(data).encode()
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self.send_header("Cache-Control", "no-store")
		for key, value in (headers or {}).items():
			self.send_header(key, value)
		self.end_headers()
		self.wfile.write(body)

	def error(self, status, message):
		self.sendjson({"error": message}, status)

	def body(self):
		try:
			length = int(self.headers.get("Content-Length", 0))
		except ValueError:
			length = 0
		if length <= 0 or length > 1024 * 1024:
			return {}
		try:
			return json.loads(self.rfile.read(length))
		except ValueError:
			return {}

	def session(self):
		'''Browser: httpOnly cookie. App: Authorization: Bearer <session token>'''
		header = self.headers.get("Authorization", "")
		if header.lower().startswith("bearer "):
			return db.getsession(header[7:].strip())
		cookies = SimpleCookie(self.headers.get("Cookie", ""))
		morsel = cookies.get(COOKIE)
		return db.getsession(morsel.value if morsel else None)

	def require(self):
		user = self.session()
		if not user:
			self.error(401, "login required")
			return None
		return user

	# ---------- routes ----------

	def do_GET(self):
		url = urlparse(self.path)
		path = url.path
		try:
			if path == "/" or path == "/index.html":
				return self.static("index.html")
			if path.startswith("/static/"):
				return self.static(unquote(path[len("/static/"):]))
			if path == "/api/me":
				user = self.session()
				# 200 with a null username: the page asks this at startup, a 401 would only fill the browser console with an error
				return self.sendjson({"username": user["username"] if user else None})
			if path == "/api/services":
				return self.sendjson({"services": SERVICES})
			if path == "/api/app/vault":
				user = self.require()
				if not user:
					return
				return self.sendjson({"items": db.vaultentries(user["id"])})
			if path == "/api/tokens":
				user = self.require()
				if not user:
					return
				info = db.tokensinfo(user["id"])
				return self.sendjson({"tokens": [{"service": s, "saved": s in info, "updated": info.get(s)} for s in SERVICES]})
			if path == "/api/library":
				user = self.require()
				if not user:
					return
				name = parse_qs(url.query).get("service", [""])[0]
				if name not in SERVICES:
					return self.error(400, "unknown service")
				token = db.gettoken(user["id"], name)
				if not token:
					return self.sendjson({"error": "no saved login for this service", "needlogin": True}, 409)
				module = service(name)
				try:
					if not module.checktoken(token):
						return self.sendjson({"error": "saved login expired", "needlogin": True}, 409)
					books = module.library(token)
				except Exception as e:
					return self.error(502, f"library unavailable: {e}")
				return self.sendjson({"books": [{"id": bid, "title": data.get("title", bid)} for bid, data in books.items()]})
			if path.startswith("/api/downloads/"):
				user = self.require()
				if not user:
					return
				jobid = path.rsplit("/", 1)[-1]
				with jobslock:
					job = jobs.get(jobid)
					if not job or job["userid"] != user["id"]:
						return self.error(404, "unknown download")
					return self.sendjson(self.jobview(job))
			if path == "/api/books":
				user = self.require()
				if not user:
					return
				books = db.listbooks(user["id"])
				for book in books:
					book["size"] = (ROOT / book["path"]).stat().st_size if (ROOT / book["path"]).exists() else 0
				return self.sendjson({"books": books})
			if path.startswith("/api/file/"):
				user = self.require()
				if not user:
					return
				try:
					bookid = int(path.rsplit("/", 1)[-1])
				except ValueError:
					return self.error(400, "invalid book")
				book = db.getbook(user["id"], bookid)
				if not book:
					return self.error(404, "unknown book")
				return self.sendfile(ROOT / book["path"], book)
			return self.error(404, "not found")
		except (BrokenPipeError, ConnectionResetError):
			pass
		except Exception:
			traceback.print_exc()
			self.error(500, "internal error")

	def do_POST(self):
		path = urlparse(self.path).path
		try:
			if path == "/api/register":
				return self.register()
			if path == "/api/login":
				return self.login()
			if path == "/api/logout":
				return self.logout()
			if path == "/api/app/register":
				return self.appregister()
			if path == "/api/app/login":
				return self.applogin()
			if path == "/api/app/logout":
				return self.applogout()
			if path == "/api/tokens":
				return self.savetoken()
			if path == "/api/downloads":
				return self.startdownload()
			return self.error(404, "not found")
		except (BrokenPipeError, ConnectionResetError):
			pass
		except Exception:
			traceback.print_exc()
			self.error(500, "internal error")

	def do_PUT(self):
		path = urlparse(self.path).path
		try:
			if path.startswith("/api/app/vault/"):
				return self.appvaultsave(unquote(path.rsplit("/", 1)[-1]))
			return self.error(404, "not found")
		except (BrokenPipeError, ConnectionResetError):
			pass
		except Exception:
			traceback.print_exc()
			self.error(500, "internal error")

	def do_DELETE(self):
		path = urlparse(self.path).path
		if path.startswith("/api/app/vault/"):
			user = self.require()
			if not user:
				return
			name = unquote(path.rsplit("/", 1)[-1])
			if name not in SERVICES:
				return self.error(400, "unknown service")
			db.deletevault(user["id"], name)
			return self.sendjson({"ok": True})
		if path.startswith("/api/tokens/"):
			user = self.require()
			if not user:
				return
			name = path.rsplit("/", 1)[-1]
			if name not in SERVICES:
				return self.error(400, "unknown service")
			db.deletetoken(user["id"], name)
			return self.sendjson({"ok": True})
		self.error(404, "not found")

	# ---------- auth ----------

	def cookieheader(self, token, maxttl):
		secure = "; Secure" if SECURE else ""
		return f"{COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={maxttl}{secure}"

	def credentialproblem(self, username, password):
		if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
			return "username: 3-32 characters (letters, digits, . _ -)"
		if len(password) < 6:
			return "password too short (min 6 characters)"
		return ""

	def register(self):
		data = self.body()
		username = str(data.get("username", "")).strip()
		password = str(data.get("password", ""))
		problem = self.credentialproblem(username, password)
		if problem:
			return self.error(400, problem)
		if db.finduser(username):
			return self.error(409, "username already taken")
		user = db.newuser(username, password)
		token = db.createsession(user["id"])
		return self.sendjson({"username": username}, 200, {"Set-Cookie": self.cookieheader(token, db.SESSION_AGE)})

	def login(self):
		data = self.body()
		user = db.finduser(str(data.get("username", "")).strip())
		if not user or not db.checkpassword(user["password"], str(data.get("password", ""))):
			return self.error(403, "wrong username or password")
		token = db.createsession(user["id"])
		return self.sendjson({"username": user["username"]}, 200, {"Set-Cookie": self.cookieheader(token, db.SESSION_AGE)})

	def logout(self):
		user = self.session()
		if user:
			morsel = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
			db.deletesession(morsel.value if morsel else "")
		self.sendjson({"ok": True}, 200, {"Set-Cookie": self.cookieheader("", 0)})

	# ---------- desktop app ----------

	def appsession(self, user):
		'''Login of the app: same users table as the site, so one account works in both'''
		return self.sendjson({
			"username": user["username"],
			"userid": user["id"],
			"salt": db.ensurevaultsalt(user["id"]),
			"token": db.createsession(user["id"]),
			"vault": db.vaultentries(user["id"]),
		})

	def appregister(self):
		data = self.body()
		username = str(data.get("username", "")).strip()
		password = str(data.get("password", ""))
		problem = self.credentialproblem(username, password)
		if problem:
			return self.error(400, problem)
		if db.finduser(username):
			return self.error(409, "username already taken")
		return self.appsession(db.newuser(username, password))

	def applogin(self):
		data = self.body()
		user = db.finduser(str(data.get("username", "")).strip())
		if not user or not db.checkpassword(user["password"], str(data.get("password", ""))):
			return self.error(403, "wrong username or password")
		return self.appsession(user)

	def applogout(self):
		header = self.headers.get("Authorization", "")
		if header.lower().startswith("bearer "):
			db.deletesession(header[7:].strip())
		return self.sendjson({"ok": True})

	def appvaultsave(self, service):
		'''The app sends only the encrypted blob: the server cannot read the account'''
		user = self.require()
		if not user:
			return
		if service not in SERVICES:
			return self.error(400, "unknown service")
		data = self.body()
		nonce = str(data.get("nonce", ""))
		payload = str(data.get("data", ""))
		if not nonce or not payload:
			return self.error(400, "empty entry")
		if len(nonce) > 64 or len(payload) > 16384:
			return self.error(400, "entry too large")
		db.savevault(user["id"], service, nonce, payload)
		return self.sendjson({"ok": True, "service": service})

	# ---------- platform login ----------

	def savetoken(self):
		user = self.require()
		if not user:
			return
		data = self.body()
		name = data.get("service", "")
		username = str(data.get("username", "")).strip()
		password = str(data.get("password", ""))
		if name not in SERVICES:
			return self.error(400, "unknown service")
		if not username or not password:
			return self.error(400, "email and password required")
		module = service(name)
		try:
			token = module.login(username, password)
			if not token:
				return self.error(403, "the platform refused the login")
			if not module.checktoken(token):
				return self.error(502, "the platform returned an unusable login")
		except Exception as e:
			return self.error(502, f"login failed: {e}")
		db.savetoken(user["id"], name, token)
		return self.sendjson({"ok": True, "service": name})

	# ---------- downloads ----------

	def startdownload(self):
		user = self.require()
		if not user:
			return
		data = self.body()
		name = data.get("service", "")
		bookids = data.get("books") or []
		if name not in SERVICES:
			return self.error(400, "unknown service")
		if not isinstance(bookids, list) or not bookids:
			return self.error(400, "nothing selected")
		if not db.gettoken(user["id"], name):
			return self.sendjson({"error": "no saved login for this service", "needlogin": True}, 409)
		bookids = [str(i) for i in bookids[:50]]
		jobid = uuid.uuid4().hex
		job = {
			"id": jobid,
			"userid": user["id"],
			"service": name,
			"state": "running",
			"started": time.time(),
			"items": [{"bookid": i, "title": i, "progress": 0, "status": "queued", "message": "", "error": ""} for i in bookids],
		}
		with jobslock:
			jobs[jobid] = job
		threading.Thread(target=runjob, args=(jobid,), daemon=True).start()
		return self.sendjson({"job": jobid}, 202)

	def jobview(self, job):
		return {
			"id": job["id"],
			"service": job["service"],
			"state": job["state"],
			"error": job.get("error"),
			"items": job["items"],
		}

	# ---------- files ----------

	def static(self, name):
		path = (STATIC / name).resolve()
		if not path.is_file() or STATIC not in path.parents:
			return self.error(404, "not found")
		ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
		body = path.read_bytes()
		self.send_response(200)
		self.send_header("Content-Type", ctype)
		self.send_header("Content-Length", str(len(body)))
		self.send_header("Cache-Control", "no-cache")
		self.end_headers()
		self.wfile.write(body)

	def sendfile(self, path, book):
		if not path.is_file():
			return self.error(404, "file missing on the server")
		name = re.sub(r"[^A-Za-z0-9 _.-]", "", book["title"]).strip() or book["bookid"]
		size = path.stat().st_size
		self.send_response(200)
		self.send_header("Content-Type", "application/pdf")
		self.send_header("Content-Length", str(size))
		self.send_header("Content-Disposition", f'attachment; filename="{name[:80]}.pdf"')
		self.send_header("Cache-Control", "no-store")
		self.end_headers()
		with open(path, "rb") as file:
			while chunk := file.read(256 * 1024):
				self.wfile.write(chunk)

	def log_message(self, fmt, *args):
		print(f"{self.address_string()} [{time.strftime('%d/%b/%Y %H:%M:%S')}] {fmt % args}", flush=True)

def main():
	parser = argparse.ArgumentParser(description="scuolagrab web server")
	parser.add_argument("--host", default=os.environ.get("SBG_HOST", "84.8.252.233"))
	parser.add_argument("--port", type=int, default=int(os.environ.get("SBG_PORT", "8749")))
	args = parser.parse_args()

	db.init()
	FILES.mkdir(exist_ok=True)
	try:
		server = ThreadingHTTPServer((args.host, args.port), Handler)
	except OSError as e:
		print(f"Cannot bind {args.host}:{args.port}: {e}")
		print("Use --host 0.0.0.0 to listen on every interface, or --host 127.0.0.1 for local tests.")
		sys.exit(1)
	server.daemon_threads = True
	print(f"scuolagrab server on http://{args.host}:{args.port}", flush=True)
	print(f"database: {db.DBPATH}", flush=True)
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print("\nStopping.", flush=True)
		server.shutdown()

if __name__ == "__main__":
	main()
