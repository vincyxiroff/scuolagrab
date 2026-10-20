import sys

import paths

paths.setup()

import i18n

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
		messagebox.showerror("scuolagrab", i18n.t("app.crash", error=exc, log=paths.datadir() / "error.log"))
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

# interface language: the saved choice, otherwise the system locale
LANGUAGE = i18n.setlanguage(utils.getsetting("language", i18n.detect()))

class LoginPage(ttk.Frame):
	'''Login/registration page shown inside the main window.

	It is a frame and not a second window: a Toplevel created as a transient of a
	hidden root is never mapped by some desktops (KDE/Wayland), so the app looked
	like it did not start at all. The password also protects the accounts saved on
	the server: the key is derived here with vault.py and never leaves the app.
	'''

	def __init__(self, master, onsuccess, server=DEFAULTSERVER, username="", password=""):
		super().__init__(master, padding=24)
		self.onsuccess = onsuccess
		self.mode = "login"
		self.busy = False
		self.queue = queue.Queue()
		self.polldid = None

		self.columnconfigure(1, weight=1)
		self.rowconfigure(9, weight=1)

		ttk.Label(self, text=appname, font=("TkDefaultFont", 20, "bold")).grid(row=0, column=0, sticky="w")
		ttk.Label(self, text=i18n.t("app.tagline"), foreground="#666").grid(row=0, column=1, sticky="e")
		self.hint = ttk.Label(self, text=i18n.t("login.hint"), foreground="#666", wraplength=470, justify="left")
		self.hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

		ttk.Label(self, text=i18n.t("login.server")).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(3, 0))
		chooser = ttk.Frame(self)
		chooser.grid(row=2, column=1, sticky="we", pady=(3, 0))
		self.servermode = tk.StringVar(value="default")
		# the server hosted for everyone, or one you run yourself
		self.defaultbutton = ttk.Radiobutton(chooser, text=i18n.t("login.default"), value="default", variable=self.servermode, command=self.updateserver)
		self.defaultbutton.pack(side="left")
		self.custombutton = ttk.Radiobutton(chooser, text=i18n.t("login.custom"), value="custom", variable=self.servermode, command=self.updateserver)
		self.custombutton.pack(side="left", padx=(12, 0))

		ttk.Label(self, text=i18n.t("login.address")).grid(row=3, column=0, sticky="w", padx=(0, 10), pady=3)
		self.server = ttk.Entry(self, width=44)
		self.server.insert(0, server or DEFAULTSERVER)
		self.server.grid(row=3, column=1, sticky="we", pady=3)

		ttk.Label(self, text=i18n.t("login.username")).grid(row=4, column=0, sticky="w", padx=(0, 10), pady=3)
		self.username = ttk.Entry(self, width=44)
		self.username.insert(0, username)
		self.username.grid(row=4, column=1, sticky="we", pady=3)

		ttk.Label(self, text=i18n.t("login.password")).grid(row=5, column=0, sticky="w", padx=(0, 10), pady=3)
		self.password = ttk.Entry(self, width=44, show="*")
		self.password.insert(0, password)
		self.password.grid(row=5, column=1, sticky="we", pady=3)

		self.confirmlabel = ttk.Label(self, text=i18n.t("login.confirm"))
		self.confirmlabel.grid(row=6, column=0, sticky="w", padx=(0, 10), pady=3)
		self.confirm = ttk.Entry(self, width=44, show="*")
		self.confirm.grid(row=6, column=1, sticky="we", pady=3)
		self.confirmlabel.grid_remove()
		self.confirm.grid_remove()

		self.status = ttk.Label(self, text="", foreground="#666", wraplength=470, justify="left")
		self.status.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 10))

		buttons = ttk.Frame(self)
		buttons.grid(row=8, column=0, columnspan=2, sticky="we")
		self.submitbutton = ttk.Button(buttons, text=i18n.t("login.signin"), command=self.submit)
		self.submitbutton.pack(side="left")
		self.switchbutton = ttk.Button(buttons, text=i18n.t("login.create"), command=self.switch)
		self.switchbutton.pack(side="left", padx=8)

		ttk.Label(self, text=i18n.t("login.note"), foreground="#888", wraplength=470, justify="left").grid(row=9, column=0, columnspan=2, sticky="sw", pady=(16, 0))

		langframe = ttk.Frame(self)
		langframe.grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
		ttk.Label(langframe, text=i18n.t("app.language"), foreground="#666").pack(side="left", padx=(0, 8))
		self.languagebox = ttk.Combobox(langframe, state="readonly", width=12, values=list(i18n.LANGUAGES.values()))
		self.languagebox.set(i18n.LANGUAGES[i18n.language])
		self.languagebox.bind("<<ComboboxSelected>>", self.onlanguage)
		self.languagebox.pack(side="left")

		for widget in (self.server, self.username, self.password, self.confirm):
			widget.bind("<Return>", self.onsubmit)

		# remember the choice: a custom address stays selected the next time
		if server and server.strip().rstrip("/") != DEFAULTSERVER.rstrip("/"):
			self.servermode.set("custom")
		else:
			self.servermode.set("default")
		self.updateserver()

		self.polldid = self.after(80, self.poll)
		if password:
			self.submitbutton.focus_set()
		else:
			(self.password if username else self.username).focus_set()

	def updateserver(self, focus=True):
		'''The address field is usable only with "Altro server"'''
		custom = self.servermode.get() == "custom"
		# a disabled Entry ignores delete/insert: edit while it is enabled, then lock it
		self.server.configure(state="normal")
		if self.busy:
			self.server.configure(state="disabled")
			return
		if custom:
			if focus:
				self.server.focus_set()
				self.server.selection_range(0, "end")
		else:
			self.server.delete(0, "end")
			self.server.insert(0, DEFAULTSERVER)
			self.server.configure(state="disabled")

	def serverurl(self):
		'''Address to connect to: the hosted server or the one typed by the user'''
		if self.servermode.get() == "custom":
			return self.server.get().strip()
		return DEFAULTSERVER

	def onsubmit(self, event=None):
		self.submit()
		return "break"

	def onlanguage(self, event=None):
		'''Switch language without losing what is already typed'''
		name = self.languagebox.get()
		for code, label in i18n.LANGUAGES.items():
			if label == name:
				app = self.winfo_toplevel()
				if hasattr(app, "switchlanguage"):
					app.switchlanguage(code)
				return

	def switch(self):
		if self.busy:
			return
		self.mode = "register" if self.mode == "login" else "login"
		root = self.winfo_toplevel()
		if self.mode == "register":
			root.title(i18n.t("app.title.register"))
			self.submitbutton.configure(text=i18n.t("login.registeraction"))
			self.switchbutton.configure(text=i18n.t("login.back"))
			self.hint.configure(text=i18n.t("login.hint.register"))
			self.confirmlabel.grid()
			self.confirm.grid()
			self.confirm.focus_set()
		else:
			root.title(i18n.t("app.title.login"))
			self.submitbutton.configure(text=i18n.t("login.signin"))
			self.switchbutton.configure(text=i18n.t("login.create"))
			self.hint.configure(text=i18n.t("login.hint"))
			self.confirmlabel.grid_remove()
			self.confirm.grid_remove()
		self.setstatus("")

	def setstatus(self, text, error=False):
		self.status.configure(text=text, foreground="#b00020" if error else "#666")

	def setbusy(self, busy):
		self.busy = busy
		state = "disabled" if busy else "normal"
		for widget in (self.submitbutton, self.switchbutton, self.username, self.password, self.confirm, self.defaultbutton, self.custombutton, self.languagebox):
			widget.configure(state=state)
		# the address follows the radio choice, not the busy state
		self.updateserver(focus=False)

	def submit(self):
		if self.busy:
			return
		server = self.serverurl()
		username = self.username.get().strip()
		password = self.password.get()
		if not server.startswith(("http://", "https://")):
			return self.setstatus(i18n.t("login.error.url"), error=True)
		if not username or not password:
			return self.setstatus(i18n.t("login.error.credentials"), error=True)
		if self.mode == "register":
			if len(password) < 6:
				return self.setstatus(i18n.t("login.error.short"), error=True)
			if password != self.confirm.get():
				return self.setstatus(i18n.t("login.error.match"), error=True)
		self.setbusy(True)
		self.setstatus(i18n.t("login.busy.register") if self.mode == "register" else i18n.t("login.busy.login"))
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
				self.setstatus(i18n.servermessage(payload), error=True)
		except queue.Empty:
			pass
		except tk.TclError:
			return
		try:
			self.polldid = self.after(80, self.poll)
		except tk.TclError:
			pass

	def finish(self, result):
		self.stop()
		self.onsuccess(result)

	def stop(self):
		try:
			if self.polldid:
				self.after_cancel(self.polldid)
				self.polldid = None
		except tk.TclError:
			pass

	def destroy(self):
		self.stop()
		super().destroy()

class App(tk.Tk):
	def __init__(self, auth=True):
		super().__init__()
		self.title(i18n.t("app.title"))
		self.geometry("1000x720")
		self.minsize(860, 620)
		self.queue = queue.Queue()
		self.books = {}
		self.token = None
		self.busy = False
		self.ready = False
		self.service = next(iter(utils.services))
		self.userid = None
		self.session = None
		self.key = None
		self.accounts = {}
		self.loginpage = None
		self.polldid = self.after(80, self.poll)
		if auth:
			# nothing works without an account: the first page is the login form
			self.showlogin()
		else:
			self.userid = self.getuser()
			self.build()
			self.ready = True
			self.refreshaccount()

	def resetpage(self):
		'''Remove the current page (login form or main layout) before showing the other'''
		self.ready = False
		self.loginpage = None
		for child in self.winfo_children():
			child.destroy()

	def showlogin(self, server=None, username=None, password=None):
		'''The window always shows a page: a separate modal window is not mapped by every desktop'''
		self.resetpage()
		self.title(i18n.t("app.title.login"))
		self.minsize(1, 1)
		self.resizable(False, False)
		self.geometry("580x530")
		if server is None:
			server = utils.getsetting("server", DEFAULTSERVER)
		if username is None:
			username = utils.getsetting("username", "")
		self.loginpage = LoginPage(self, self.onauth, server=server, username=username, password=password or "")
		self.loginpage.pack(fill="both", expand=True)

	def switchlanguage(self, code):
		'''Change the interface language and rebuild the current page keeping the user state'''
		if code == i18n.language:
			return
		i18n.setlanguage(code)
		utils.settingset("language", code)
		if self.ready:
			books = self.books
			self.resetpage()
			self.build()
			self.ready = True
			self.userlabel.configure(text=self.session["username"] if self.session else "")
			self.refreshaccount()
			if books:
				self.books = books
				for bid, book in books.items():
					self.tree.insert("", "end", iid=bid, values=(bid, book.get("title", "")))
				self.setstatus(i18n.t("status.books", count=len(books)))
		else:
			page = self.loginpage
			username = page.username.get() if page else None
			password = page.password.get() if page else ""
			server = page.server.get().strip() if page and page.servermode.get() == "custom" else None
			self.showlogin(server=server, username=username, password=password)

	def onlanguage(self, event=None):
		name = self.languagebox.get()
		for code, label in i18n.LANGUAGES.items():
			if label == name:
				self.switchlanguage(code)
				return

	def onauth(self, result):
		self.session = result
		self.key = result["key"]
		self.accounts = result["accounts"]
		utils.settingset("username", result["username"])
		utils.settingset("server", result["server"])
		# local storage of the platform tokens, keyed by the server username
		self.userid = utils.new_login(result["username"], "", False) or utils.register(result["username"], "")
		self.resetpage()
		self.resizable(True, True)
		self.minsize(860, 620)
		self.geometry("1000x720")
		self.title(i18n.t("app.title.user", user=result["username"]))
		self.build()
		self.ready = True
		self.userlabel.configure(text=result["username"])
		self.log(i18n.t("log.welcome", user=result["username"], count=len(result["accounts"])))
		self.log(i18n.t("log.folder", folder=self.folder()))
		if result["failed"]:
			self.log(i18n.t("log.unreadable", list=", ".join(utils.services.get(s, s) for s in result["failed"])))
		self.refreshaccount()
		self.setstatus(i18n.t("app.ready"))

	def saveaccount(self, service, username, password):
		'''Store the platform login on the server, encrypted with the key held in memory'''
		if not (self.session and self.key):
			return
		blob = vault.encrypt(self.key, self.session["userid"], service, {"username": username, "password": password})
		apiclient.Client(self.session["server"]).saveaccount(self.session["token"], service, blob)
		self.accounts[service] = {"username": username, "password": password}

	def logout(self):
		'''Back to the login page, forgetting the key and the decrypted accounts'''
		if self.busy:
			return
		session = self.session
		self.session, self.key, self.accounts = None, None, {}
		self.token, self.books = None, {}
		if session:
			threading.Thread(target=lambda: self.dologout(session), daemon=True).start()
		self.showlogin()

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
		ttk.Label(header, text=i18n.t("app.tagline"), foreground="#666").pack(side="left", padx=(10, 0), pady=(8, 0))
		self.logoutbutton = ttk.Button(header, text=i18n.t("app.signout"), command=self.logout)
		self.logoutbutton.pack(side="right")
		self.userlabel = ttk.Label(header, text="", foreground="#666")
		self.userlabel.pack(side="right", padx=8)
		self.languagebox = ttk.Combobox(header, state="readonly", width=10, values=list(i18n.LANGUAGES.values()))
		self.languagebox.set(i18n.LANGUAGES[i18n.language])
		self.languagebox.bind("<<ComboboxSelected>>", self.onlanguage)
		self.languagebox.pack(side="right", padx=(0, 12))

		top = ttk.LabelFrame(self, text=i18n.t("app.service"), padding=10)
		top.pack(fill="x", padx=16, pady=(8, 0))
		self.servicebox = ttk.Combobox(top, state="readonly", values=list(utils.services.values()), width=28)
		self.servicebox.set(utils.services[self.service])
		self.servicebox.bind("<<ComboboxSelected>>", self.onservice)
		self.servicebox.grid(row=0, column=0, sticky="w")
		self.tokenlabel = ttk.Label(top, text="", foreground="#666")
		self.tokenlabel.grid(row=0, column=1, sticky="w", padx=12)

		account = ttk.LabelFrame(self, text=i18n.t("app.account"), padding=10)
		account.pack(fill="x", padx=16, pady=(8, 0))
		ttk.Label(account, text=i18n.t("app.email")).grid(row=0, column=0, sticky="w")
		self.email = ttk.Entry(account, width=34)
		self.email.grid(row=1, column=0, sticky="we", padx=(0, 8))
		ttk.Label(account, text=i18n.t("login.password")).grid(row=0, column=1, sticky="w")
		self.password = ttk.Entry(account, width=26, show="*")
		self.password.grid(row=1, column=1, sticky="we", padx=(0, 8))
		self.loginbutton = ttk.Button(account, text=i18n.t("app.signin"), command=self.login)
		self.loginbutton.grid(row=1, column=2, padx=(0, 8))
		self.loadbutton = ttk.Button(account, text=i18n.t("app.loadlibrary"), command=self.loadlibrary)
		self.loadbutton.grid(row=1, column=3)
		account.columnconfigure(0, weight=3)
		account.columnconfigure(1, weight=2)

		booksframe = ttk.LabelFrame(self, text=i18n.t("app.books"), padding=10)
		booksframe.pack(fill="both", expand=True, padx=16, pady=(8, 0))
		self.tree = ttk.Treeview(booksframe, columns=("id", "title"), show="headings", selectmode="extended")
		self.tree.heading("id", text=i18n.t("app.id"))
		self.tree.heading("title", text=i18n.t("app.title_column"))
		self.tree.column("id", width=230, stretch=False)
		self.tree.column("title", width=620)
		scroll = ttk.Scrollbar(booksframe, orient="vertical", command=self.tree.yview)
		self.tree.configure(yscrollcommand=scroll.set)
		self.tree.pack(side="left", fill="both", expand=True)
		scroll.pack(side="right", fill="y")

		location = ttk.Frame(self, padding=(16, 8, 16, 0))
		location.pack(fill="x")
		ttk.Label(location, text=i18n.t("app.folder"), foreground="#666").pack(side="left", padx=(0, 8))
		self.folderpath = ttk.Entry(location, state="readonly")
		self.folderpath.pack(side="left", fill="x", expand=True)
		ttk.Button(location, text=i18n.t("app.openfolder"), command=self.openfolder).pack(side="left", padx=(8, 0))

		actions = ttk.Frame(self, padding=(16, 8))
		actions.pack(fill="x")
		self.downloadbutton = ttk.Button(actions, text=i18n.t("app.downloadselected"), command=self.downloadselected)
		self.downloadbutton.pack(side="left")
		ttk.Button(actions, text=i18n.t("app.downloadall"), command=lambda: self.download(allbooks=True)).pack(side="left", padx=8)
		self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
		self.progress.pack(side="left", fill="x", expand=True, padx=12)
		self.status = ttk.Label(actions, text=i18n.t("app.ready"), width=34)
		self.status.pack(side="right")

		logframe = ttk.LabelFrame(self, text=i18n.t("app.activity"), padding=6)
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
		text = i18n.t("app.account.saved") if account else i18n.t("app.account.none")
		if self.token:
			text = i18n.t("app.account.token", text=text)
		self.tokenlabel.configure(text=text)

	def log(self, message):
		'''Messages can arrive from a thread while the login page is shown: ignore them'''
		if not self.ready or not self.logbox.winfo_exists():
			return
		self.logbox.configure(state="normal")
		self.logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
		self.logbox.see("end")
		self.logbox.configure(state="disabled")

	def setstatus(self, text):
		if self.ready:
			self.status.configure(text=text)

	def setbusy(self, busy):
		self.busy = busy
		if not self.ready:
			return
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
				self.queue.put(("log", i18n.t("log.error", error=e)))
				self.call(self.setbusy, False)
				self.call(self.setstatus, i18n.t("app.error"))
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
			messagebox.showwarning(appname, i18n.t("dialog.needcredential"))
			return
		self.setbusy(True)
		self.setstatus(i18n.t("status.signingin"))
		self.log(i18n.t("log.loggingin", service=utils.services[self.service]))
		service = self.service

		def work():
			token = utils.login(service, email, password)
			if token and utils.checktoken(service, token):
				utils.addtoken(self.userid, service, token)
				try:
					self.saveaccount(service, email, password)
				except Exception as e:
					self.queue.put(("log", i18n.t("log.notsaved", error=i18n.servermessage(e))))
				return token
			if token:
				raise RuntimeError(i18n.t("error.tokenrejected"))
			raise RuntimeError(i18n.t("error.badcredentials"))

		def done(token, error):
			self.setbusy(False)
			if error:
				self.setstatus(i18n.t("status.loginfailed"))
				self.log(i18n.t("log.loginfailed", error=error))
				return
			self.token = token
			if service in self.accounts:
				self.tokenlabel.configure(text=i18n.t("app.account.saved"))
			else:
				self.tokenlabel.configure(text=i18n.t("app.token"))
			self.log(i18n.t("log.loginok"))
			self.setstatus(i18n.t("app.ready"))
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
		self.setstatus(i18n.t("status.loadinglibrary"))
		self.log(i18n.t("log.loadinglibrary", service=utils.services[self.service]))
		token = self.token

		def work():
			if not utils.checktoken(self.service, token):
				raise RuntimeError(i18n.t("error.tokenexpired"))
			return utils.library(self.service, token)

		def done(books, error):
			self.setbusy(False)
			if error:
				self.setstatus(i18n.t("status.libraryfailed"))
				self.log(i18n.t("log.libraryfailed", error=error))
				return
			self.books = books
			self.tree.delete(*self.tree.get_children())
			for bid, book in books.items():
				self.tree.insert("", "end", iid=bid, values=(bid, book.get("title", "")))
			self.log(i18n.t("log.books", count=len(books)))
			self.setstatus(i18n.t("status.books", count=len(books)))

		self.task(work, done)

	def downloadselected(self):
		selected = list(self.tree.selection())
		if not selected:
			messagebox.showinfo(appname, i18n.t("dialog.needbook"))
			return
		self.download(ids=selected)

	def download(self, ids=None, allbooks=False):
		if self.busy:
			return
		if not self.books:
			messagebox.showinfo(appname, i18n.t("dialog.needlibrary"))
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
				self.queue.put(("log", i18n.t("log.downloading", title=data.get("title", bid))))
				last = [-1, ""]

				def progress(value, status=""):
					if value != last[0] or status != last[1]:
						last[0], last[1] = value, status
						self.queue.put(("progress", value, status or data.get("title", "")))

				try:
					path = Path(utils.downloadbook(service, token, bid, data, progress)).resolve()
					downloaded.append(str(path))
					self.queue.put(("log", i18n.t("log.saved", path=path)))
				except Exception as e:
					failed.append((data.get("title", bid), str(e)))
					self.queue.put(("log", i18n.t("log.downloaderror", title=data.get("title", bid), error=e)))
			return downloaded, failed

		def done(result, error):
			self.setbusy(False)
			if error:
				self.setstatus(i18n.t("status.downloadfailed"))
				return
			downloaded, failed = result
			self.progress["value"] = 100
			self.setstatus(i18n.t("status.done", downloaded=len(downloaded), failed=len(failed)))
			self.log(i18n.t("log.done", downloaded=len(downloaded), failed=len(failed)))
			if failed:
				messagebox.showwarning(appname, i18n.t("dialog.failedbooks", list="\n".join(title for title, _ in failed)))

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
			messagebox.showinfo(appname, i18n.t("dialog.nofilemanager", folder=folder))

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
