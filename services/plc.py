import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pymupdf as fitz
import requests
from playwright.sync_api import sync_playwright

import config
import lib

service = "plc"

base = "https://place.sanoma.it"
ebook = "https://ebook.sanoma.it"
cdn = "https://npmitaly-pro-apidistribucion.sanoma.it"

ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
htmlheaders = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "it-IT,it;q=0.9"}

config = config.getconfig()

class PlaceError(Exception):
	pass

def cookielist(token):
	'''The token is the json encoded MY_PLACE_SESSION cookie'''
	try:
		cookies = json.loads(token)
		if isinstance(cookies, list):
			return cookies
	except (TypeError, ValueError):
		pass
	return [{"name": "MY_PLACE_SESSION", "value": token, "domain": "place.sanoma.it", "path": "/"}]

def mksession(token):
	session = requests.Session()
	session.headers.update({"User-Agent": ua, "Accept-Language": "it-IT,it;q=0.9"})
	for cookie in cookielist(token):
		session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
	return session

def get(url, session=None, **kwargs):
	'''GET with retries, the place frontend sometimes answers 502 under load'''
	response = None
	for attempt in range(4):
		try:
			response = session.get(url, **kwargs) if session is not None else requests.get(url, **kwargs)
		except requests.RequestException:
			if attempt == 3:
				raise
			response = None
		if response is not None and response.status_code < 500:
			return response
		time.sleep(1.5 * (attempt + 1))
	return response

def unescape(value):
	try:
		return json.loads('"' + value + '"')
	except ValueError:
		return value

def loginonce(username, password):
	'''Returns the token, False when the credentials are rejected and None on a technical failure'''
	try:
		with sync_playwright() as p:
			browser = p.chromium.launch()
			ctx = browser.new_context(locale="it-IT", user_agent=ua)
			page = ctx.new_page()
			# Auth0 can be slow, so the waits are generous: a slow page must not look like a wrong password
			page.goto(base + "/login", wait_until="domcontentloaded", timeout=90000)
			field = "input[type=text], input[type=email]"
			page.wait_for_selector(field, timeout=60000)
			page.fill(field, username)
			page.click("button[type=submit]")
			page.wait_for_selector("input[type=password]", timeout=60000)
			page.fill("input[type=password]", password)
			page.click("button[type=submit]")

			deadline = time.time() + 90
			while time.time() < deadline:
				if page.url.startswith(base) and "/login" not in page.url:
					break
				try:
					if "utente non riconosciuto" in page.inner_text("body").lower():
						print("Login failed: wrong email or password")
						browser.close()
						return False
				except Exception:
					pass
				page.wait_for_timeout(1000)

			# Only the session cookie is needed at runtime: keep it alone so no personal data (the analytics cookies carry the login email) is saved.
			cookies = [{"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c["path"]} for c in ctx.cookies() if c["name"] == "MY_PLACE_SESSION"]
			browser.close()
	except Exception as e:
		print(f"Login attempt failed: {e}")
		return None
	if not cookies:
		print("Login failed: wrong email or password")
		return False
	return json.dumps(cookies)

def login(username, password):
	for attempt in range(2):
		token = loginonce(username, password)
		if token:
			return token
		if token is False:
			return None
		if attempt == 0:
			print("Retrying the login...")
			time.sleep(3)
	return None

def checktoken(token):
	try:
		r = get(base + "/prodotti_digitali", session=mksession(token), headers=dict(htmlheaders, **{"User-Agent": ua}), allow_redirects=False, timeout=30)
	except requests.RequestException:
		return False
	return r is not None and r.status_code == 200

def parsebooks(html):
	'''Extract the libromedia resources serialized inside the product page'''
	books = {}
	for match in re.finditer(r'\{id:"([0-9a-f]{24})",display_name:"((?:[^"\\]|\\.)*)"', html):
		start = match.start()
		end = html.find("},{", start)
		block = html[start:end if end != -1 else start + 4000]
		if 'external_platform_id:"LIBROMEDIA"' not in block:
			continue
		if "flag_reflowable:false" not in block:
			# Liquid books use a different viewer
			continue
		gedi = re.search(r'external_id:"([^"]*)"', block)
		cover = re.search(r'cover_url:"([^"]*)"', block)
		title = unescape(match.group(2)).strip()
		if not gedi:
			continue
		books[match.group(1)] = {"title": title, "cover": cover.group(1) if cover else "", "gedi": gedi.group(1), "platform": "libromedia"}
	return books

def library(token):
	session = mksession(token)
	r = get(base + "/prodotti_digitali", session=session, headers=dict(htmlheaders, **{"User-Agent": ua}), timeout=30)
	if r is None or r.status_code != 200:
		raise PlaceError(f"Library request failed (HTTP {getattr(r, 'status_code', 'no response')})")

	# The whole library (products and their resources) is serialized in the page
	return parsebooks(r.text)

def cover(token, bookid, data):
	r = get(data["cover"], timeout=30)
	r.raise_for_status()
	return r.content

def getbookaccess(token, bookid):
	'''Get the real product id and the signed CloudFront cookies for this book'''
	cookies = cookielist(token)
	with sync_playwright() as p:
		browser = p.chromium.launch()
		ctx = browser.new_context(locale="it-IT", user_agent=ua)
		ctx.add_cookies(cookies)
		page = ctx.new_page()
		try:
			with page.expect_response(lambda r: "display-books" in r.url, timeout=60000) as response:
				page.goto(base + "/prodotti_digitali/libromedia/" + bookid, wait_until="domcontentloaded", timeout=90000)
			payload = response.value.json()
		except Exception as e:
			browser.close()
			raise PlaceError(f"Unable to open the book viewer: {e}")
		browser.close()

	if not payload.get("data"):
		raise PlaceError("The book viewer returned no book")
	book = payload["data"][0]
	return book["gedi"], book["book"]["cookies"], book["book"]["url"]

def fetchpage(pagenumber, assetsbase, cookies, headers):
	r = requests.get(f"{assetsbase}/{pagenumber}/{pagenumber}.svg", headers=headers, cookies=cookies, timeout=90)
	if r.status_code != 200:
		return None
	svg = r.text
	for href in set(re.findall(r'(?:xlink:)?href="((?!data:|#)[^"]+)"', svg)):
		asset = requests.get(f"{assetsbase}/{pagenumber}/{href}", headers=headers, cookies=cookies, timeout=90)
		if asset.status_code != 200:
			continue
		if href.endswith(".png"):
			mime = "image/png"
		elif href.endswith((".jpg", ".jpeg")):
			mime = "image/jpeg"
		elif href.endswith(".woff2"):
			mime = "font/woff2"
		else:
			mime = "application/octet-stream"
		data = base64.b64encode(asset.content).decode()
		svg = svg.replace(f'"{href}"', f'"data:{mime};base64,{data}"')
	return svg.encode()

def buildtoc(master):
	pages = sorted(master["pages"], key=lambda p: p["number"])
	position = {page["number"]: i + 1 for i, page in enumerate(pages)}
	units = {}
	for unit in master.get("units", []):
		units.setdefault(unit["idUnit"], unit)

	toc, seenunits, seenchapters = [], set(), set()
	for page in pages:
		chapter = page.get("chapter") or {}
		if chapter:
			parent = (chapter.get("parent_unit") or {}).get("unit_name") or ""
			parent = parent.strip()
			name = (chapter.get("chapter_name") or "").strip()
			if parent and parent not in seenunits:
				seenunits.add(parent)
				toc.append([1, parent, position[page["number"]]])
			key = (name, (chapter.get("parent_unit") or {}).get("unit_id"))
			if name and key not in seenchapters:
				seenchapters.add(key)
				toc.append([2, name, position[page["number"]]])
		else:
			title = (units.get(page["idUnit"], {}).get("title") or "").strip()
			if title and title not in seenunits:
				seenunits.add(title)
				toc.append([1, title, position[page["number"]]])

	return toc

def downloadbook(token, bookid, data, progress):
	progress(0, "Opening book")
	gedi, cfcookies, bookurl = getbookaccess(token, bookid)

	progress(2, "Fetching book data")
	assetsbase = f"{cdn}/product/{gedi}/ONLINE/assets/book"
	pagesbase = assetsbase + "/pages"
	headers = {"User-Agent": ua, "Referer": cdn + "/viewers/lm60/online/index.html"}
	try:
		master = requests.get(assetsbase + "/data/master.json", headers=headers, cookies=cfcookies, timeout=60)
		master.raise_for_status()
		master = master.json()
	except (requests.RequestException, ValueError) as e:
		raise PlaceError(f"Unable to fetch the book manifest: {e}")

	pages = sorted(master["pages"], key=lambda p: p["number"])
	if not pages:
		raise PlaceError("The book has no pages")

	pdf = fitz.open()
	workers = max(1, config.getint(service, "Workers", fallback=6))
	chunksize = workers * 3
	done = 0

	for start in range(0, len(pages), chunksize):
		batch = pages[start:start + chunksize]
		with ThreadPoolExecutor(max_workers=workers) as pool:
			results = list(pool.map(lambda page: fetchpage(page["number"], pagesbase, cfcookies, headers), batch))

		for page, svg in zip(batch, results):
			if svg is None:
				# Keep page numbering aligned even if an asset is missing
				pdf.new_page(width=844, height=1125)
			else:
				try:
					source = fitz.open(stream=svg, filetype="svg")
					pagepdf = fitz.open("pdf", source.convert_to_pdf())
					source.close()
					pdf.insert_pdf(pagepdf)
					pagepdf.close()
				except Exception:
					pdf.new_page(width=844, height=1125)
			done += 1

		progress(4 + round(92 * done / len(pages)), f"Downloading page {done}/{len(pages)}")

	progress(97, "Applying toc/labels")
	pdf.set_toc(buildtoc(master))
	if config.getboolean(service, "PageLabels", fallback=False):
		labels = [str(page.get("label", "")).strip() for page in pages]
		if any(labels):
			try:
				pdf.set_page_labels(lib.generatelabelsrule(labels))
			except Exception:
				pass
	return pdf
