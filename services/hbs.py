import requests
import pymupdf as fitz
from io import BytesIO
import zipfile
import lib
import config

service = "hbs"

apibase = "https://ms-api.hubscuola.it"
mmsbase = "https://ms-mms.hubscuola.it"
pdfbase = "https://ms-pdf.hubscuola.it"

# The PDF service rejects clients that are too old and wants a valid Document Engine client version.
# 2020.6.0 (the one used by the old app) is refused now, these ones are accepted.
clientversions = ["protocol=3, client=2024.1.0", "protocol=3, client=2025.1.0", "protocol=3, client=1.0.0"]

config = config.getconfig()

class HBSError(Exception):
	pass

def parsejson(r, what):
	if r.status_code != 200:
		raise HBSError(f"{what} failed (HTTP {r.status_code}): {r.text[:200].strip()}")
	try:
		return r.json()
	except ValueError:
		raise HBSError(f"{what} returned invalid data (HTTP {r.status_code}): {r.text[:200].strip()}")

def getlogindata(username, password):
	r = requests.get("https://bce.mondadorieducation.it//app/mondadorieducation/login/loginJsonp", params={"username": username, "password": password})
	return parsejson(r, "Login")

def getsessiontoken(jwt, internalusername, sessionid):
	data = {"username": internalusername, "sessionId": sessionid, "jwt": jwt}
	r = requests.post(apibase + "/user/internalLogin", json=data)
	return parsejson(r, "Session creation")

def getlibrary(token, platform):
	r = requests.get(apibase + "/getLibrary/" + platform, headers={"Token-Session": token})
	return parsejson(r, f"Library ({platform})")

def getbookinfo(token, bookid, platform):
	r = requests.get(apibase + "/me" + platform + "/publication/" + str(bookid), headers={"Token-Session": token})
	return parsejson(r, "Book info")

def downloadchapter(token, bookid, chapterid, progress, total, done):
	r = requests.get(mmsbase + "/public/" + str(bookid) + "/" + str(chapterid) + ".zip", params={"tokenId": token, "app": "v2"}, headers={"Token-Session": token}, stream=True)
	if r.status_code != 200:
		raise HBSError(f"Chapter {chapterid} download failed (HTTP {r.status_code}): {r.text[:200].strip()}")

	length = int(r.headers.get("content-length", 0)) or 1
	file = bytearray()
	for data in r.iter_content(chunk_size=102400):
		file += data
		progress(round(done + len(file) / length * total))
	try:
		return zipfile.ZipFile(BytesIO(file), "r")
	except zipfile.BadZipFile:
		raise HBSError(f"Chapter {chapterid} is not a valid zip file")

def cover(token, bookid, data):
	url = data["cover"]
	if isinstance(url, dict):
		url = url.get("fileName") or url.get("fullFilename")
	r = requests.get(url, params={"tokenId": token}, headers={"Token-Session": token})
	r.raise_for_status()
	return r.content

def checktoken(token):
	r = requests.get(apibase + "/annotation/user-preferences", headers={"Token-Session": token})
	return r.status_code == 200 and "not valid" not in r.text

def getauth(jwt, bookid, platform):
	origin = "https://" + platform + ".hubscuola.it/viewer/" + bookid + "?page=1"
	version = config.get(service, "ClientVersion", fallback=clientversions[0])
	last = None
	for v in [version] + [i for i in clientversions if i != version]:
		r = requests.post(pdfbase + "/i/d/" + bookid + "/auth", json={"jwt": jwt, "origin": origin}, headers={"PSPDFKit-Platform": "web", "PSPDFKit-Version": v})
		if r.status_code == 412:
			# Outdated client version, try the next one
			last = v
			continue
		auth = parsejson(r, "PDF authentication")
		if "token" not in auth or "layerHandle" not in auth:
			raise HBSError("PDF authentication returned an invalid response")
		return auth
	raise HBSError(f"The PDF service refused every client version (last tried: {last})")

def downloadpdf(token, bookid, layerhandle, progress, total, done):
	r = requests.get(pdfbase + "/i/d/" + bookid + "/h/" + layerhandle + "/pdf", params={"token": token}, stream=True)
	if r.status_code != 200:
		raise HBSError(f"PDF download failed (HTTP {r.status_code}): {r.text[:200].strip()}")

	length = int(r.headers.get("content-length", 0)) or 1
	file = bytearray()
	for data in r.iter_content(chunk_size=102400):
		file += data
		progress(round(done + len(file) / length * total))
	if not file.startswith(b"%PDF"):
		raise HBSError("The PDF service did not return a pdf file")
	return bytes(file)

def extractpage(zipfile, chapterid, pageid):
	file = zipfile.read(str(chapterid) + "/" + str(pageid) + ".pdf")
	return fitz.open(stream=file, filetype="pdf")

def login(username, password):
	logindata = getlogindata(username, password)
	if not logindata["data"]:
		print("Login failed: " + logindata["error"])
		return None
	session = getsessiontoken(logindata["data"]["hubEncryptedUser"], logindata["data"]["username"], logindata["data"]["sessionId"])
	return session["tokenId"]

def library(token):
	books = dict()
	def getbooktitle(book):
		title = book["title"]
		if volume := book.get("volume"):
			title += f" {volume}"
		if subtitle := book.get("subtitle"):
			title += f" - {subtitle}"
		return title

	for platform in ["young", "kids"]:
		try:
			platformbooks = getlibrary(token, platform)
		except HBSError:
			# A user might not have access to one of the two platforms at all
			continue
		for i in platformbooks:
			cover = i.get("coverBig") or i.get("coverSmall") or i.get("cover")
			books[str(i["id"])] = {"title": getbooktitle(i), "cover": cover, "platform": platform}

	return books

def firstpage(node, pagepos):
	for child in node["children"]:
		if isinstance(child, dict):
			found = firstpage(child, pagepos)
			if found is not None:
				return found
		elif child in pagepos:
			return child

def buildtoc(bookinfo):
	'''Build a (level, title, page) toc from the book index, skipping empty nodes'''
	pages = bookinfo["pagesId"]
	pagepos = {i: n + 1 for n, i in enumerate(pages)}
	toc = []

	def walk(nodes, level, parent):
		for node in nodes:
			first = firstpage(node, pagepos)
			if first is None:
				continue
			title = (node.get("title") or "").strip()
			page = pagepos[first]
			# Chapters with a single subchapter with the same name would create duplicated entries
			if parent is None or (title, page) != parent:
				toc.append([level, title, page])
				parent = (title, page)
			walk([i for i in node["children"] if isinstance(i, dict)], level + 1, parent)

	walk(bookinfo["indexContents"]["chapters"], 1, None)
	return toc

def pageowners(bookinfo):
	'''Map every page id to the top level chapter zip that contains it'''
	pagepos = {i: n for n, i in enumerate(bookinfo["pagesId"])}
	owners = {}

	def collect(nodes, chapterid):
		for node in nodes:
			if isinstance(node, dict):
				collect(node["children"], chapterid)
			elif node in pagepos:
				owners[node] = chapterid

	for chapter in bookinfo["indexContents"]["chapters"]:
		collect(chapter["children"], chapter["chapterId"])

	return owners

def applylabels(pdf, bookinfo):
	if not config.getboolean(service, "PageLabels", fallback=False):
		return
	labels = list(bookinfo["multiRangeIndex"]["valToLabel"].values())[:len(pdf)]
	if labels:
		pdf.set_page_labels(lib.generatelabelsrule(labels))

def downloadbook_legacy(token, bookid, data, progress):
	'''Download the pdf one chapter at a time. This is the only downloader that still works.'''
	bookinfo = getbookinfo(token, bookid, data["platform"])
	pages = bookinfo["pagesId"]
	owners = pageowners(bookinfo)
	chapters = bookinfo["indexContents"]["chapters"]

	pdf = fitz.open()
	chapterwidth = 92 / max(len(chapters), 1)

	for i, chapter in enumerate(chapters):
		chapterstart = 5 + (i * chapterwidth)
		chapterpages = [page for page in pages if owners.get(page) == chapter["chapterId"]]
		if not chapterpages:
			continue
		progress(chapterstart, f"Downloading chapter {i + 1}/{len(chapters)}: {chapter['title']}")
		chapterzip = downloadchapter(token, bookid, chapter["chapterId"], progress, chapterwidth, chapterstart)
		for page in chapterpages:
			try:
				pdf.insert_pdf(extractpage(chapterzip, chapter["chapterId"], page))
			except KeyError:
				# Some books advertise pages that are not actually in the chapter archive
				continue

	progress(97, "Applying toc/labels")
	pdf.set_toc(buildtoc(bookinfo))
	applylabels(pdf, bookinfo)
	return pdf

def downloadbook_documentengine(token, bookid, data, progress):
	'''Download a single pdf from the viewer backend. Currently broken on Mondadori's side.'''
	bookinfo = getbookinfo(token, bookid, data["platform"])

	progress(2, "Fetching authentication data")
	auth = getauth(bookinfo["jwt"], bookid, data["platform"])

	progress(4, "Downloading unencrypted pdf")
	pdfbytes = downloadpdf(auth["token"], bookid, auth["layerHandle"], progress, 91, 4)

	pdf = fitz.open(stream=pdfbytes, filetype="pdf")

	progress(97, "Applying toc/labels")
	pdf.set_toc(buildtoc(bookinfo))
	applylabels(pdf, bookinfo)
	return pdf

def downloadbook(token, bookid, data, progress):
	if config.has_option(service, "Downloader"):
		downloader = config.get(service, "Downloader").strip().lower()
	else:
		# Backwards compatibility with the old option
		downloader = "chapters" if config.getboolean(service, "UseLegacy", fallback=True) else "documentengine"

	if downloader == "documentengine":
		try:
			return downloadbook_documentengine(token, bookid, data, progress)
		except (HBSError, requests.RequestException) as e:
			print(f"\nThe single-pdf downloader failed ({e}), falling back to the chapter downloader.")
			progress(0, "Falling back to chapter download")

	return downloadbook_legacy(token, bookid, data, progress)
