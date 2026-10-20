'''Runtime folders for scuolagrab.

Run from the source tree nothing changes: the working directory is the project
folder and the files stay there. In a packaged app (PyInstaller: AppImage, .exe,
macOS .app) the program folder is read-only or temporary, so the config, the
database, the downloaded books and the browser cache go to the user data folder.
'''

import os
import sys
from pathlib import Path

NAME = "scuolagrab"

def isfrozen():
	return bool(getattr(sys, "frozen", False))

def bundled():
	'''Folder that contains the files shipped with the app (read-only when frozen)'''
	if isfrozen():
		return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
	return Path(__file__).resolve().parent

def datadir():
	'''Writable folder for config.ini, db.json and files/'''
	if not isfrozen():
		return Path(__file__).resolve().parent
	if sys.platform.startswith("win"):
		base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
	elif sys.platform == "darwin":
		base = Path.home() / "Library" / "Application Support"
	else:
		base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
	path = base / NAME
	path.mkdir(parents=True, exist_ok=True)
	return path

def browsersdir():
	'''Chromium shipped inside the bundle, None when running from the source tree'''
	if isfrozen():
		return bundled() / "browsers"
	return None

def setup():
	'''Prepare cwd and the playwright browser path before importing the services'''
	data = datadir()
	os.chdir(data)
	browsers = browsersdir()
	if browsers is not None:
		os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
	return data
