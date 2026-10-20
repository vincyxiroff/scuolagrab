import sys
import dependencies

if not dependencies.ensure(gui=True):
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

import utils

appname = "scuolagrab"

class App(tk.Tk):
	def __init__(self):
		super().__init__()
		self.title(f"{appname} — by vincyxiroff")
		self.geometry("1000x720")
		self.minsize(860, 620)
		self.queue = queue.Queue()
		self.books = {}
		self.token = None
		self.busy = False
		self.service = next(iter(utils.services))
		self.userid = self.getuser()
		self.build()
		self.after(80, self.poll)
		self.refreshaccount()

	def getuser(self):
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

		actions = ttk.Frame(self, padding=(16, 8))
		actions.pack(fill="x")
		self.downloadbutton = ttk.Button(actions, text="Scarica selezionati", command=self.downloadselected)
		self.downloadbutton.pack(side="left")
		ttk.Button(actions, text="Scarica tutti", command=lambda: self.download(allbooks=True)).pack(side="left", padx=8)
		ttk.Button(actions, text="Apri cartella", command=self.openfolder).pack(side="left")
		self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
		self.progress.pack(side="left", fill="x", expand=True, padx=12)
		self.status = ttk.Label(actions, text="Pronto", width=34)
		self.status.pack(side="right")

		logframe = ttk.LabelFrame(self, text="Attività", padding=6)
		logframe.pack(fill="both", expand=False, padx=16, pady=(0, 14))
		self.logbox = ScrolledText(logframe, height=10, state="disabled", wrap="word")
		self.logbox.pack(fill="both", expand=True)

	def onservice(self, event=None):
		name = self.servicebox.get()
		for code, label in utils.services.items():
			if label == name:
				self.service = code
				break
		self.books = {}
		self.tree.delete(*self.tree.get_children())
		self.token = None
		self.refreshaccount()

	def refreshaccount(self):
		self.token = utils.gettoken(self.userid, self.service)
		if self.token:
			self.tokenlabel.configure(text="Token salvato ✓")
		else:
			self.tokenlabel.configure(text="Nessun token salvato")

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
		self.after(80, self.poll)

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

		def work():
			token = utils.login(self.service, email, password)
			if token and utils.checktoken(self.service, token):
				utils.addtoken(self.userid, self.service, token)
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
			self.tokenlabel.configure(text="Token salvato ✓")
			self.password.delete(0, "end")
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
			self.refreshaccount()
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
					path = utils.downloadbook(service, token, bid, data, progress)
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
		folder = Path("files") / self.service
		folder.mkdir(parents=True, exist_ok=True)
		try:
			if sys.platform.startswith("win"):
				os.startfile(folder)  # type: ignore[attr-defined]
			elif sys.platform == "darwin":
				subprocess.Popen(["open", str(folder)])
			else:
				subprocess.Popen(["xdg-open", str(folder)])
		except Exception:
			messagebox.showinfo(appname, f"Cartella: {folder.resolve()}")

if __name__ == "__main__":
	App().mainloop()
