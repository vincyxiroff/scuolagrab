import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

modules = {
	"pymupdf": "pymupdf",
	"requests": "requests",
	"Crypto": "pycryptodome",
	"umsgpack": "u-msgpack-python",
	"tinydb": "tinydb",
	"playwright": "playwright",
}

# the CLI needs rich, the GUI does not: the packaged app has no rich inside
clionly = {
	"rich": "rich",
}

def isfrozen():
	return bool(getattr(sys, "frozen", False))

def missingmodules():
	checks = dict(modules)
	if not isfrozen():
		checks.update(clionly)
	return [package for module, package in checks.items() if importlib.util.find_spec(module) is None]

def browserspath():
	env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
	if env and env not in ("0", ""):
		return Path(env)
	return Path.home() / ".cache" / "ms-playwright"

def chromiuminstalled():
	cache = browserspath()
	if not cache.is_dir():
		return False
	return any(path.name.startswith("chromium") for path in cache.iterdir())

def installbrowser():
	'''Download Chromium. In a packaged app the playwright driver is inside the bundle.'''
	if isfrozen():
		try:
			from playwright.__main__ import main as playwrightmain
		except Exception as e:
			print(f"Playwright driver not available: {e}")
			return False
		argv = sys.argv
		sys.argv = ["playwright", "install", "chromium"]
		try:
			playwrightmain()
		except SystemExit as e:
			return e.code in (None, 0)
		except Exception as e:
			print(f"Browser installation failed: {e}")
			return False
		finally:
			sys.argv = argv
		return True
	return run([sys.executable, "-m", "playwright", "install", "chromium"])

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

def ensure(gui=False, interactive=True):
	'''Check the python packages and the playwright browser, offering to install what is missing.
	interactive=False only reports (used by the packaged app self test).'''
	missing = missingmodules()
	if missing:
		if isfrozen():
			print("This build is incomplete, missing modules: " + ", ".join(missing))
			return False
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
		if interactive and ask("Do you want to download it now (~130 MB)?", gui):
			if not installbrowser():
				print("Browser installation failed. Run it manually: python3 -m playwright install chromium")
				return False
		else:
			print("Run: python3 -m playwright install chromium")
			print("(The services that open a browser will not work without it.)")
	return True
