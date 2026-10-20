#!/usr/bin/env python3
'''Build the scuolagrab desktop app.

    python3 packaging/build.py                 # bundle Chromium and build the package
    python3 packaging/build.py --no-browsers   # smaller build, Sanoma login needs Chromium later

Output (packaging/dist/):
    Linux    scuolagrab-x86_64.AppImage   (or a .tar.gz if appimagetool is unavailable)
    Windows  scuolagrab-windows-x64.zip   (contains scuolagrab.exe)
    macOS    scuolagrab-macos.zip         (contains scuolagrab.app)
'''

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
DIST = HERE / "dist"
NAME = "scuolagrab"
APPIMAGETOOL_URL = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

def run(command, **kwargs):
	print("+ " + " ".join(str(c) for c in command), flush=True)
	subprocess.run([str(c) for c in command], check=True, **kwargs)

def makeicon(path):
	'''Simple 256x256 icon, drawn with PyMuPDF so no extra dependency is needed'''
	import pymupdf
	doc = pymupdf.open()
	page = doc.new_page(width=256, height=256)
	page.draw_rect(page.rect, color=None, fill=(0.12, 0.30, 0.55))
	page.insert_text((58, 172), "sg", fontsize=128, color=(1, 1, 1))
	path.parent.mkdir(parents=True, exist_ok=True)
	page.get_pixmap(alpha=False).save(str(path))
	doc.close()

def installbrowsers():
	dest = BUILD / "browsers"
	dest.mkdir(parents=True, exist_ok=True)
	env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(dest))
	run([sys.executable, "-m", "playwright", "install", "chromium"], env=env)
	return dest

def pyinstaller(browsers):
	env = dict(os.environ)
	env.pop("PLAYWRIGHT_BROWSERS_PATH", None)
	if browsers:
		env["SCUOLAGRAB_BROWSERS"] = str(browsers)
	run(
		[
			sys.executable,
			"-m",
			"PyInstaller",
			"--noconfirm",
			"--clean",
			"--distpath",
			DIST,
			"--workpath",
			BUILD / "pyinstaller",
			HERE / "scuolagrab.spec",
		],
		env=env,
		cwd=ROOT,
	)

def appimage(icon):
	appdir = BUILD / "AppDir"
	if appdir.exists():
		shutil.rmtree(appdir)
	appdir.mkdir(parents=True)
	shutil.copytree(DIST / NAME, appdir / "usr" / "bin")

	apprun = appdir / "AppRun"
	apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/bin/scuolagrab" "$@"\n')
	apprun.chmod(apprun.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

	(appdir / f"{NAME}.desktop").write_text(
		"[Desktop Entry]\n"
		"Type=Application\n"
		f"Name={NAME}\n"
		"Comment=Download your digital schoolbooks\n"
		"Exec=scuolagrab\n"
		"Icon=scuolagrab\n"
		"Categories=Education;Utility;\n"
		"Terminal=false\n"
	)
	shutil.copyfile(icon, appdir / f"{NAME}.png")

	tool = BUILD / "appimagetool"
	if not tool.is_file():
		print("+ download appimagetool", flush=True)
		urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)
		tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

	env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
	run([tool, "--no-appstream", appdir, DIST / f"{NAME}-x86_64.AppImage"], env=env)

def windows():
	target = DIST / f"{NAME}-windows-x64.zip"
	with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as package:
		package.write(DIST / f"{NAME}.exe", f"{NAME}.exe")
	print(f"created {target}", flush=True)

def macos():
	app = DIST / f"{NAME}.app"
	if not app.is_dir():
		raise SystemExit("scuolagrab.app was not created")
	arch = "arm64" if platform.machine() == "arm64" else "x64"
	target = DIST / f"{NAME}-macos-{arch}.zip"
	run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, target])

def main():
	parser = argparse.ArgumentParser(description="Build the scuolagrab desktop app")
	parser.add_argument("--no-browsers", action="store_true", help="do not bundle Chromium (smaller build)")
	parser.add_argument("--browsers", action="store_true", help="bundle Chromium also on macOS (PyInstaller cannot codesign Chrome's .app on macOS)")
	args = parser.parse_args()

	BUILD.mkdir(exist_ok=True)
	DIST.mkdir(exist_ok=True)
	icon = BUILD / f"{NAME}.png"
	makeicon(icon)

	bundle = not args.no_browsers
	if sys.platform == "darwin" and not args.browsers:
		# codesign fails on Chrome's nested .app: the macOS app downloads Chromium on first run
		print("macOS: Chromium is not bundled (use --browsers to force it); the app downloads it on first run.", flush=True)
		bundle = False

	browsers = installbrowsers() if bundle else None
	pyinstaller(browsers)

	if sys.platform.startswith("linux"):
		appimage(icon)
	elif sys.platform.startswith("win"):
		windows()
	elif sys.platform == "darwin":
		macos()
	else:
		raise SystemExit(f"Unsupported platform: {sys.platform}")

	print(f"\nDone. Files in {DIST}", flush=True)

if __name__ == "__main__":
	main()
