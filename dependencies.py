import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

modules = {
	"pymupdf": "pymupdf",
	"rich": "rich",
	"requests": "requests",
	"Crypto": "pycryptodome",
	"umsgpack": "u-msgpack-python",
	"tinydb": "tinydb",
	"playwright": "playwright",
}

def missingmodules():
	return [package for module, package in modules.items() if importlib.util.find_spec(module) is None]

def chromiuminstalled():
	cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright")))
	if not cache.is_dir():
		return False
	return any(path.name.startswith("chromium") for path in cache.iterdir())

def run(command):
	print("+ " + " ".join(command), flush=True)
	return subprocess.call(command, cwd=ROOT) == 0

def ask(question, gui=False):
	if gui:
		try:
			from tkinter import messagebox
			return messagebox.askyesno("scuolagrab", question)
		except Exception:
			return False
	if not sys.stdin.isatty():
		return False
	try:
		return input(question + " [y/N] ").strip().lower() in ("y", "yes", "s", "si", "sì")
	except EOFError:
		return False

def ensure(gui=False):
	'''Check the python packages and the playwright browser, offering to install what is missing'''
	missing = missingmodules()
	if missing:
		print("Missing python packages: " + ", ".join(missing))
		if ask("Do you want to install them now with pip?", gui):
			if not run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
				print("pip install failed. Run it manually: python3 -m pip install -r requirements.txt")
				return False
			if missingmodules():
				print("Some packages are still missing after the installation.")
				return False
		else:
			print("Run: python3 -m pip install -r requirements.txt")
			return False

	if not chromiuminstalled():
		print("The Chromium browser used by playwright is not installed.")
		if ask("Do you want to download it now (~120 MB)?", gui):
			if not run([sys.executable, "-m", "playwright", "install", "chromium"]):
				print("Browser installation failed. Run it manually: python3 -m playwright install chromium")
				return False
		else:
			print("Run: python3 -m playwright install chromium")
			print("(The services that open a browser will not work without it.)")
	return True
