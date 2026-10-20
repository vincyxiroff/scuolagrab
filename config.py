import configparser
from pathlib import Path
import shutil

import paths

root = paths.setup()

def getconfig():
	config = configparser.ConfigParser()
	conffile = root / "config.ini"
	if not conffile.is_file():
		shutil.copyfile(paths.bundled() / "config-default.ini", conffile)
	config.read_file(open(conffile))
	return config