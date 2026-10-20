# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
ONEFILE = sys.platform.startswith("win")
CONSOLE = not sys.platform.startswith("win")

datas, binaries, hiddenimports = [], [], []

# the playwright driver (node) is needed at runtime to launch the bundled browser
for package in ("playwright",):
	d, b, h = collect_all(package)
	datas += d
	binaries += b
	hiddenimports += h

# the services are imported dynamically by utils.getservice()
hiddenimports += ["services.bsm", "services.hbs", "services.plc"]

for name in ("config-default.ini", "README.md", "LICENSE"):
	datas.append((str(ROOT / name), "."))

browsers = os.environ.get("SCUOLAGRAB_BROWSERS")
if browsers and Path(browsers).is_dir():
	datas.append((browsers, "browsers"))

a = Analysis(
	[str(ROOT / "gui.py")],
	pathex=[str(ROOT)],
	binaries=binaries,
	datas=datas,
	hiddenimports=hiddenimports,
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[
		"pytest",
		"unittest",
		"pydoc_data",
		# pulled in by optional imports but never used by the app: keep the bundle small
		"pandas",
		"numpy",
		"matplotlib",
		"scipy",
		"botocore",
		"boto3",
		"openpyxl",
		"fsspec",
		"IPython",
		"jupyter",
		"notebook",
	],
	noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
	exe = EXE(
		pyz,
		a.scripts,
		a.binaries,
		a.datas,
		[],
		name="scuolagrab",
		debug=False,
		bootloader_ignore_signals=False,
		strip=False,
		upx=False,
		console=False,
		disable_windowed_traceback=False,
		target_arch=None,
		codesign_identity=None,
		entitlements_file=None,
	)
else:
	exe = EXE(
		pyz,
		a.scripts,
		[],
		exclude_binaries=True,
		name="scuolagrab",
		debug=False,
		bootloader_ignore_signals=False,
		strip=False,
		upx=False,
		console=CONSOLE,
	)
	coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="scuolagrab")

	if sys.platform == "darwin":
		app = BUNDLE(
			coll,
			name="scuolagrab.app",
			icon=None,
			bundle_identifier="it.scuolagrab.app",
			info_plist={
				"CFBundleName": "scuolagrab",
				"CFBundleDisplayName": "scuolagrab",
				"CFBundleShortVersionString": "1.0",
				"NSHighResolutionCapable": True,
			},
		)
