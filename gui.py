import sys

import paths

paths.setup()

def logexception(exc_type, exc, tb):
	'''In the packaged app there is no terminal: write the traceback to the data folder'''
	import traceback
	text = "".join(traceback.format_exception(exc_type, exc, tb))
	try:
		(paths.datadir() / "error.log").write_text(text)
	except Exception:
		pass
	print(text, file=sys.stderr)
	try:
		from tkinter import messagebox
		messagebox.showerror("scuolagrab", f"Errore imprevisto: {exc}\n\nDettagli in {paths.datadir() / 'error.log'}")
	except Exception:
		pass

sys.excepthook = logexception

import dependencies

if not dependencies.ensure(gui=True, interactive=not any(a in sys.argv for a in ("--selftest", "--checkbrowser"))):
	sys.exit(1)

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import apiclient
import config
import utils
import vault

appname = "scuolagrab"

settings = config.getconfig()
# address of the scuolagrab server, used for the account and for the encrypted vault
DEFAULTSERVER = os.environ.get("SBG_SERVER") or settings.get("app", "Server", fallback="http://84.8.252.233:8749")

class AuthDialog(tk.Toplevel):
	'''Login/registration window shown at startup, before the main window.

	The same password protects the accounts saved on the server: the key is derived
	here with vault.py and never leaves the app, the server only keeps ciphertext.
	'''

	def __init__(self, app, server=DEFAULTSERVER, username=""):
		super().__init__(app)
		self.app = app
		self.result = None
		self.cancelled = False
		self.mode = "login"
		self.busy = False
		self.queue = queue.Queue()

		self.title(f"{appname} — accedi o registrati")
		self.resizable(False, False)
		self.transient(app)
		self.protocol("WM_DELETE_WINDOW", self.cancel)
		self.bind("<Return>", lambda event: self.submit())
		self.bind("<Escape>", lambda event: self.cancel())

		frame = ttk.Frame(self, padding=16)
		frame.pack(fill="both", expand=True)
		frame.columnconfigure(1, weight=1)

		ttk.Label(frame, text=appname, font=("TkDefaultFont", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
		ttk.Label(frame, text="by vincyxiroff", foreground="#666").grid(row=0, column=2, sticky="e")
		self.hint = ttk.Label(frame, text="Accedi con il tuo account scuolagrab, oppure creane uno.", foreground="#666", wraplength=420)
		self.hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

		ttk.Label(frame, text="Server").grid(row=2, column=0, sticky="w", padx=(0, 8))
		self.server = ttk.Entry(frame, width=44)
		self.server.insert(0, server)
		self.server.grid(row=2, column=1, columnspan=2, sticky="we", pady=3)

		ttk.Label(frame, text="Username").grid(row=3, column=0, sticky="w", padx=(0, 8))
		self.username = ttk.Entry(frame, width=44)
		self.username.insert(0, username)
		self.username.grid(row=3, column=1, columnspan=2, sticky="we", pady=3)

		ttk.Label(frame, text="Password").grid(row=4, column=0, sticky="w", padx=(0, 8))
		self.password = ttk.Entry(frame, width=44, show="*")
		self.password.grid(row=4, column=1, columnspan=2, sticky="we", pady=3)

		self.confirmlabel = ttk.Label(frame, text="Ripeti password")
		self.confirmlabel.grid(row=5, column=0, sticky="w", padx=(0, 8))
		self.confirm = ttk.Entry(frame, width=44, show="*")
		self.confirm.grid(row=5, column=1, columnspan=2, sticky="we", pady=3)
		self.confirmlabel.grid_remove()
		self.confirm.grid_remove()

		self.status = ttk.Label(frame, text="", foreground="#666", wraplength=440)
		self.status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 8))

		buttons = ttk.Frame(frame)
		buttons.grid(row=7, column=0, columnspan=3, sticky="we")
		self.submitbutton = ttk.Button(buttons, text="Accedi", command=self.submit)
		self.submitbutton.pack(side="left")
		self.switchbutton = ttk.Button(buttons, text="Crea un account", command=self.switch)
		self.switchbutton.pack(side="left", padx=8)
		ttk.Button(buttons, text="Esci", command=self.cancel).pack(side="right")

		self.update_idletasks()
		self.center(app)
		self.grab_set()
		(self.password if username else self.username).focus_set()
		self.polldid = self.after(60, self.poll)

	def center(self, parent):
		try:
			x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
			y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
			self.geometry(f"+{x}+{y}")
		except Exception:
			pass

	def switch(self):
		if self.busy:
			return
		self.mode = "register" if self.mode == "login" else "login"
		if self.mode == "register":
			self.title(f"{appname} — registrazione")
			self.submitbutton.configure(text="Registrati")
			self.switchbutton.configure(text="Ho già un account")
			self.hint.configure(text="Crea l'account sul server. La password protegge anche gli account delle piattaforme: se la perdi non si possono recuperare.")
			self.confirmlabel.grid()
			self.confirm.grid()
			self.confirm.focus_set()
		else:
			self.title(f"{appname} — accedi o registrati")
			self.submitbutton.configure(text="Accedi")
			self.switchbutton.configure(text="Crea un account")
			self.hint.configure(text="Accedi con il tuo account scuolagrab, oppure creane uno.")
			self.confirmlabel.grid_remove()
			self.confirm.grid_remove()
		self.setstatus("")

	def setstatus(self, text, error=False):
		self.status.configure(text=text, foreground="#b00020" if error else "#666")

	def setbusy(self, busy):
		self.busy = busy
		state = "disabled" if busy else "normal"
		for widget in (self.submitbutton, self.switchbutton, self.server, self.username, self.password, self.confirm):
			widget.configure(state=state)

	def submit(self):
		if self.busy:
			return
		server = self.server.get().strip()
		username = self.username.get().strip()
		password = self.password.get()
		if not server.startswith(("http://", "https://")):
			return self.setstatus("L'indirizzo del server deve iniziare con http:// o https://", error=True)
		if not username or not password:
			return self.setstatus("Inserisci username e password.", error=True)
		if self.mode == "register":
			if len(password) < 6:
				return self.setstatus("La password deve avere almeno 6 caratteri.", error=True)
			if password != self.confirm.get():
				return self.setstatus("Le password non coincidono.", error=True)
		self.setbusy(True)
		self.setstatus("Creazione dell'account…" if self.mode == "register" else "Accesso…")
		threading.Thread(target=self.work, args=(self.mode, server, username, password), daemon=True).start()

	def work(self, mode, server, username, password):
		try:
			client = apiclient.Client(server)
			if mode == "register":
				data = client.register(username, password)
			else:
				data = client.login(username, password)
			key = vault.derivekey(password, str(data.get("salt", "")))
			userid = data["userid"]
			accounts, failed = {}, []
			for name, blob in (data.get("vault") or {}).items():
				if name not in utils.services:
					continue
				try:
					accounts[name] = vault.decrypt(key, userid, name, blob)
				except vault.VaultError:
					failed.append(name)
			self.queue.put(("ok", {
				"server": server,
				"token": data["token"],
				"userid": userid,
				"username": data["username"],
				"key": key,
				"accounts": accounts,
				"failed": failed,
			}))
		except Exception as e:
			self.queue.put(("error", str(e) or e.__class__.__name__))

	def poll(self):
		try:
			while True:
				kind, payload = self.queue.get_nowait()
				if kind == "ok":
					return self.finish(payload)
				self.setbusy(False)
				self.setstatus(payload, error=True)
		except queue.Empty:
			pass
		except tk.TclError:
			return
		try:
			self.polldid = self.after(60, self.poll)
		except tk.TclError:
			pass

	def finish(self, result):
		self.result = result
		self.release()
		self.destroy()
		self.app.onauth(result)

	def cancel(self):
		self.cancelled = True
		self.release()
		self.destroy()

	def release(self):
		'''Stop the timers before destroying, otherwise tk complains about the pending poll'''
		try:
			if self.polldid:
				self.after_cancel(self.polldid)
				self.polldid = None
		except tk.TclError:
			pass
		try:
			self.grab_release()
		except tk.TclError:
			pass

class App(tk.Tk):
	def __init__(self, auth=True):
		super().__init__()
		self.title(f"{appname} — by vincyxiroff")
		self.geometry("1000x720")
		self.minsize(860, 620)
		self.queue = queue.Queue()
		self.books = {}
		self.token = None
		self.busy = False
		self.service = next(iter(utils.services))
		self.userid = None
		self.session = None
		self.key = None
		self.accounts = {}
		self.build()
		self.polldid = self.after(80, self.poll)
		if auth:
			# nothing works without an account: ask before showing the main window
			self.withdraw()
			self.after(60, self.asklogin)
		else:
			self.userid = self.getuser()
			self.refreshaccount()

	def asklogin(self):
		'''Show the login/registration window and keep the app closed until it succeeds'''
		if self.session:
			return
		self.withdraw()
		dialog = AuthDialog(self, server=utils.getsetting("server", DEFAULTSERVER), username=utils.getsetting("username", ""))
		self.wait_window(dialog)
		if dialog.result is None:
			self.destroy()

	def onauth(self, result):
		self.session = result
		self.key = result["key"]
		self.accounts = result["accounts"]
		utils.settingset("username", result["username"])
		utils.settingset("server", result["server"])
		# local storage of the platform tokens, keyed by the server username
		self.userid = utils.new_login(result["username"], "", False) or utils.register(result["username"], "")
		self.title(f"{appname} — {result['username']}")
		self.userlabel.configure(text=result["username"])
		self.deiconify()
		self.log(f"Accesso come {result['username']}: {len(result['accounts'])} account salvati sul server.")
		self.log(f"I libri vengono salvati in {self.folder()}")
		if result["failed"]:
			self.log("Account non leggibili (password diversa o dati rovinati): " + ", ".join(utils.services.get(s, s) for s in result["failed"]))
		self.refreshaccount()
		self.setstatus("Pronto")

	def saveaccount(self, service, username, password):
		'''Store the platform login on the server, encrypted with the key held in memory'''
		if not (self.session and self.key):
			return
		blob = vault.encrypt(self.key, self.session["userid"], service, {"username": username, "password": password})
		apiclient.Client(self.session["server"]).saveaccount(self.session["token"], service, blob)
		self.accounts[service] = {"username": username, "password": password}

	def logout(self):
		if self.busy:
			return
		session = self.session
		self.session, self.key, self.accounts = None, None, {}
		self.token, self.books = None, {}
		self.tree.delete(*self.tree.get_children())
		self.email.delete(0, "end")
		self.password.delete(0, "end")
		self.userlabel.configure(text="")
		self.tokenlabel.configure(text="")
		self.setstatus("Pronto")
		self.log("Uscito.")
		if session:
			threading.Thread(target=lambda: self.dologout(session), daemon=True).start()
		self.asklogin()

	def dologout(self, session):
		try:
			apiclient.Client(session["server"]).logout(session["token"])
		except Exception:
			pass

	def getuser(self):
		'''Local user used by the self test, where there is no server account'''
		users = utils.getusers()
		if not users:
			utils.register("locale", "")
			users = utils.getusers()
		return utils.new_login(users[0], "", False)

	def build(self):
		style = ttk.Style(self)
		try:
			style.theme_use("clam")
		except tk.TclError:
			pass

		header = ttk.Frame(self, padding=(16, 12, 16, 4))
		header.pack(fill="x")
		ttk.Label(header, text="scuolagrab", font=("TkDefaultFont", 20, "bold")).pack(side="left")
		ttk.Label(header, text="by vincyxiroff", foreground="#666").pack(side="left", padx=(10, 0), pady=(8, 0))
		self.logoutbutton = ttk.Button(header, text="Esci", command=self.logout)
		self.logoutbutton.pack(side="right")
		self.userlabel = ttk.Label(header, text="", foreground="#666")
		self.userlabel.pack(side="right", padx=8)

		top = ttk.LabelFrame(self, text="Servizio", padding=10)
		top.pack(fill="x", padx=16, pady=(8, 0))
		self.servicebox = ttk.Combobox(top, state="readonly", values=list(utils.services.values()), width=28)
		self.servicebox.set(utils.services[self.service])
		self.servicebox.bind("<<ComboboxSelected>>", self.onservice)
		self.servicebox.grid(row=0, column=0, sticky="w")
		self.tokenlabel = ttk.Label(top, text="", foreground="#666")
		self.tokenlabel.grid(row=0, column=1, sticky="w", padx=12)

		account = ttk.LabelFrame(self, text="Account del servizio", padding=10)
		account.pack(fill="x", padx=16, pady=(8, 0))
		ttk.Label(account, text="Email / username").grid(row=0, column=0, sticky="w")
		self.email = ttk.Entry(account, width=34)
		self.email.grid(row=1, column=0, sticky="we", padx=(0, 8))
		ttk.Label(account, text="Password").grid(row=0, column=1, sticky="w")
		self.password = ttk.Entry(account, width=26, show="*")
		self.password.grid(row=1, column=1, sticky="we", padx=(0, 8))
		self.loginbutton = ttk.Button(account, text="Accedi", command=self.login)
		self.loginbutton.grid(row=1, column=2, padx=(0, 8))
		self.loadbutton = ttk.Button(account, text="Carica libreria", command=self.loadlibrary)
		self.loadbutton.grid(row=1, column=3)
		account.columnconfigure(0, weight=3)
		account.columnconfigure(1, weight=2)

		booksframe = ttk.LabelFrame(self, text="Libri", padding=10)
		booksframe.pack(fill="both", expand=True, padx=16, pady=(8, 0))
		self.tree = ttk.Treeview(booksframe, columns=("id", "title"), show="headings", selectmode="extended")
		self.tree.heading("id", text="ID")
		self.tree.heading("title", text="Titolo")
		self.tree.column("id", width=230, stretch=False)
		self.tree.column("title", width=620)
		scroll = ttk.Scrollbar(booksframe, orient="vertical", command=self.tree.yview)
		self.tree.configure(yscrollcommand=scroll.set)
		self.tree.pack(side="left", fill="both", expand=True)
		scroll.pack(side="right", fill="y")

		location = ttk.Frame(self, padding=(16, 8, 16, 0))
		location.pack(fill="x")
		ttk.Label(location, text="Salvataggio in", foreground="#666").pack(side="left", padx=(0, 8))
		self.folderpath = ttk.Entry(location, state="readonly")
		self.folderpath.pack(side="left", fill="x", expand=True)
		ttk.Button(location, text="Apri cartella", command=self.openfolder).pack(side="left", padx=(8, 0))

		actions = ttk.Frame(self, padding=(16, 8))
		actions.pack(fill="x")
		self.downloadbutton = ttk.Button(actions, text="Scarica selezionati", command=self.downloadselected)
		self.downloadbutton.pack(side="left")
		ttk.Button(actions, text="Scarica tutti", command=lambda: self.download(allbooks=True)).pack(side="left", padx=8)
		self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
		self.progress.pack(side="left", fill="x", expand=True, padx=12)
		self.status = ttk.Label(actions, text="Pronto", width=34)
		self.status.pack(side="right")

		logframe = ttk.LabelFrame(self, text="Attività", padding=6)
		logframe.pack(fill="both", expand=False, padx=16, pady=(0, 14))
		self.logbox = ScrolledText(logframe, height=10, state="disabled", wrap="word")
		self.logbox.pack(fill="both", expand=True)
		self.refreshfolder()

	def folder(self):
		'''Absolute folder where the pdf of the selected service is saved'''
		return (paths.datadir() / "files" / self.service).resolve()

	def refreshfolder(self):
		self.folderpath.configure(state="normal")
		self.folderpath.delete(0, "end")
		self.folderpath.insert(0, str(self.folder()))
		self.folderpath.configure(state="readonly")

	def onservice(self, event=None):
		name = self.servicebox.get()
		for code, label in utils.services.items():
			if label == name:
				self.service = code
				break
		self.books = {}
		self.tree.delete(*self.tree.get_children())
		self.token = None
		self.refreshfolder()
		self.refreshaccount()

	def refreshaccount(self):
		'''Show the account saved on the server (decrypted in memory) for this service'''
		self.token = utils.gettoken(self.userid, self.service) if self.userid else None
		account = self.accounts.get(self.service)
		self.email.delete(0, "end")
		self.password.delete(0, "end")
		if account:
			self.email.insert(0, account["username"])
			self.password.insert(0, account["password"])
		text = "Account salvato sul server ✓" if account else "Nessun account salvato"
		if self.token:
			text += " · token attivo"
		self.tokenlabel.configure(text=text)

	def log(self, message):
		self.logbox.configure(state="normal")
		self.logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
		self.logbox.see("end")
		self.logbox.configure(state="disabled")

	def setstatus(self, text):
		self.status.configure(text=text)

	def setbusy(self, busy):
		self.busy = busy
		state = "disabled" if busy else "normal"
		self.loginbutton.configure(state=state)
		self.loadbutton.configure(state=state)
		self.downloadbutton.configure(state=state)
		self.logoutbutton.configure(state=state)

	def call(self, function, *args):
		self.queue.put(("call", function, args))

	def poll(self):
		try:
			while True:
				kind, *payload = self.queue.get_nowait()
				if kind == "log":
					self.log(payload[0])
				elif kind == "status":
					self.setstatus(payload[0])
				elif kind == "progress":
					self.progress["value"] = payload[0]
					if payload[1]:
						self.setstatus(payload[1])
				elif kind == "call":
					payload[0](*payload[1])
		except queue.Empty:
			pass
		self.polldid = self.after(80, self.poll)

	def destroy(self):
		try:
			if self.polldid:
				self.after_cancel(self.polldid)
				self.polldid = None
		except tk.TclError:
			pass
		super().destroy()

	def task(self, function, done=None):
		def runner():
			try:
				result = function()
			except Exception as e:
				self.queue.put(("log", f"Errore: {e}"))
				self.call(self.setbusy, False)
				self.call(self.setstatus, "Errore")
				if done:
					self.call(done, None, e)
				return
			if done:
				self.call(done, result, None)
		threading.Thread(target=runner, daemon=True).start()

	def login(self, thenload=False):
		if self.busy:
			return
		email, password = self.email.get().strip(), self.password.get()
		if not email or not password:
			messagebox.showwarning(appname, "Inserisci email e password del servizio.")
			return
		self.setbusy(True)
		self.setstatus("Login in corso…")
		self.log(f"Login su {utils.services[self.service]}…")
		service = self.service

		def work():
			token = utils.login(service, email, password)
			if token and utils.checktoken(service, token):
				utils.addtoken(self.userid, service, token)
				try:
					self.saveaccount(service, email, password)
				except Exception as e:
					self.queue.put(("log", f"Account non salvato sul server: {e}"))
				return token
			if token:
				raise RuntimeError("il servizio ha rifiutato il token ottenuto")
			raise RuntimeError("credenziali non valide")

		def done(token, error):
			self.setbusy(False)
			if error:
				self.setstatus("Login fallito")
				self.log(f"Login fallito: {error}")
				return
			self.token = token
			if service in self.accounts:
				self.tokenlabel.configure(text="Account salvato sul server ✓")
			else:
				self.tokenlabel.configure(text="Token salvato ✓")
			self.log("Login riuscito.")
			self.setstatus("Pronto")
			if thenload:
				self.loadlibrary()

		self.task(work, done)

	def loadlibrary(self):
		if self.busy:
			return
		if not self.token:
			self.login(thenload=True)
			return
		if not self.tree.get_children():
			self.token = utils.gettoken(self.userid, self.service) if self.userid else None
		self.setbusy(True)
		self.setstatus("Carico la libreria…")
		self.log(f"Carico la libreria di {utils.services[self.service]}…")
		token = self.token

		def work():
			if not utils.checktoken(self.service, token):
				raise RuntimeError("token scaduto, effettua di nuovo il login")
			return utils.library(self.service, token)

		def done(books, error):
			self.setbusy(False)
			if error:
				self.setstatus("Libreria non disponibile")
				self.log(f"Impossibile caricare la libreria: {error}")
				return
			self.books = books
			self.tree.delete(*self.tree.get_children())
			for bid, book in books.items():
				self.tree.insert("", "end", iid=bid, values=(bid, book.get("title", "")))
			self.log(f"Trovati {len(books)} libri.")
			self.setstatus(f"{len(books)} libri")

		self.task(work, done)

	def downloadselected(self):
		selected = list(self.tree.selection())
		if not selected:
			messagebox.showinfo(appname, "Seleziona almeno un libro.")
			return
		self.download(ids=selected)

	def download(self, ids=None, allbooks=False):
		if self.busy:
			return
		if not self.books:
			messagebox.showinfo(appname, "Carica prima la libreria.")
			return
		if allbooks:
			ids = list(self.books)
		ids = [i for i in ids if i in self.books]
		if not ids:
			return
		self.setbusy(True)
		self.progress["value"] = 0
		token = self.token
		service = self.service

		def work():
			downloaded, failed = [], []
			for index, bid in enumerate(ids):
				data = self.books[bid]
				self.queue.put(("log", f"Scarico {data.get('title', bid)}…"))
				last = [-1, ""]

				def progress(value, status=""):
					if value != last[0] or status != last[1]:
						last[0], last[1] = value, status
						self.queue.put(("progress", value, status or data.get("title", "")))

				try:
					path = Path(utils.downloadbook(service, token, bid, data, progress)).resolve()
					downloaded.append(str(path))
					self.queue.put(("log", f"Salvato: {path}"))
				except Exception as e:
					failed.append((data.get("title", bid), str(e)))
					self.queue.put(("log", f"Errore su {data.get('title', bid)}: {e}"))
			return downloaded, failed

		def done(result, error):
			self.setbusy(False)
			if error:
				self.setstatus("Download fallito")
				return
			downloaded, failed = result
			self.progress["value"] = 100
			self.setstatus(f"{len(downloaded)} scaricati, {len(failed)} falliti")
			self.log(f"Finito: {len(downloaded)} scaricati, {len(failed)} falliti.")
			if failed:
				messagebox.showwarning(appname, "Alcuni libri non sono stati scaricati:\n" + "\n".join(t for t, _ in failed))

		self.task(work, done)

	def openfolder(self):
		folder = self.folder()
		folder.mkdir(parents=True, exist_ok=True)
		try:
			if sys.platform.startswith("win"):
				os.startfile(folder)  # type: ignore[attr-defined]
			elif sys.platform == "darwin":
				if subprocess.run(["open", str(folder)]).returncode:
					raise RuntimeError("open failed")
			else:
				# xdg-open exits non zero when there is no file manager: say where the files are instead of doing nothing
				if subprocess.run(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
					raise RuntimeError("xdg-open failed")
		except Exception:
			messagebox.showinfo(appname, f"Non riesco ad aprire il file manager.\n\nI libri sono in:\n{folder}")

if __name__ == "__main__":
	if "--checkbrowser" in sys.argv:
		from playwright.sync_api import sync_playwright
		with sync_playwright() as p:
			browser = p.chromium.launch()
			print(f"chromium ok: {browser.version}")
			browser.close()
		sys.exit(0)
	if "--selftest" in sys.argv:
		app = App(auth=False)
		print(f"ok: {app.title()} — {len(app.servicebox['values'])} services")
		app.destroy()
		sys.exit(0)
	App().mainloop()
