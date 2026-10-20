import hashlib
import os
import secrets
import sqlite3
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)
DBPATH = Path(os.environ.get("SBG_DB", DATA / "server.db"))

SESSION_AGE = 7 * 24 * 3600

def connect():
	conn = sqlite3.connect(DBPATH, timeout=30)
	conn.row_factory = sqlite3.Row
	conn.execute("PRAGMA journal_mode = WAL")
	conn.execute("PRAGMA foreign_keys = ON")
	return conn

def init():
	with connect() as conn:
		conn.executescript(
			"""
			CREATE TABLE IF NOT EXISTS users (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				username TEXT NOT NULL UNIQUE,
				password TEXT NOT NULL,
				created REAL NOT NULL
			);
			CREATE TABLE IF NOT EXISTS sessions (
				token TEXT PRIMARY KEY,
				user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
				created REAL NOT NULL,
				expires REAL NOT NULL
			);
			CREATE TABLE IF NOT EXISTS service_tokens (
				user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
				service TEXT NOT NULL,
				value TEXT NOT NULL,
				updated REAL NOT NULL,
				PRIMARY KEY (user_id, service)
			);
			CREATE TABLE IF NOT EXISTS books (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
				service TEXT NOT NULL,
				bookid TEXT NOT NULL,
				title TEXT NOT NULL,
				pages INTEGER NOT NULL,
				path TEXT NOT NULL,
				created REAL NOT NULL,
				UNIQUE (user_id, service, bookid)
			);
			"""
		)

def hashpassword(password):
	salt = secrets.token_hex(16)
	digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()
	return salt + "$" + digest

def checkpassword(stored, password):
	try:
		salt, digest = stored.split("$", 1)
	except ValueError:
		return False
	attempt = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()
	return secrets.compare_digest(attempt, digest)

def createuser(username, password):
	with connect() as conn:
		conn.execute("INSERT INTO users (username, password, created) VALUES (?, ?, ?)", (username, hashpassword(password), time.time()))

def finduser(username):
	with connect() as conn:
		return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

def newuser(username, password):
	createuser(username, password)
	return finduser(username)

def createsession(userid):
	token = secrets.token_urlsafe(32)
	now = time.time()
	with connect() as conn:
		conn.execute("DELETE FROM sessions WHERE expires < ?", (now,))
		conn.execute("INSERT INTO sessions (token, user_id, created, expires) VALUES (?, ?, ?, ?)", (token, userid, now, now + SESSION_AGE))
	return token

def getsession(token):
	if not token:
		return None
	with connect() as conn:
		return conn.execute(
			"SELECT users.id, users.username FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ? AND sessions.expires > ?",
			(token, time.time()),
		).fetchone()

def deletesession(token):
	with connect() as conn:
		conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

def gettoken(userid, service):
	with connect() as conn:
		row = conn.execute("SELECT value FROM service_tokens WHERE user_id = ? AND service = ?", (userid, service)).fetchone()
	return row["value"] if row else None

def savetoken(userid, service, value):
	with connect() as conn:
		conn.execute(
			"INSERT INTO service_tokens (user_id, service, value, updated) VALUES (?, ?, ?, ?) ON CONFLICT (user_id, service) DO UPDATE SET value = excluded.value, updated = excluded.updated",
			(userid, service, value, time.time()),
		)

def deletetoken(userid, service):
	with connect() as conn:
		conn.execute("DELETE FROM service_tokens WHERE user_id = ? AND service = ?", (userid, service))

def tokensinfo(userid):
	with connect() as conn:
		rows = conn.execute("SELECT service, updated FROM service_tokens WHERE user_id = ?", (userid,)).fetchall()
	return {row["service"]: row["updated"] for row in rows}

def savebook(userid, service, bookid, title, pages, path):
	with connect() as conn:
		conn.execute(
			"INSERT INTO books (user_id, service, bookid, title, pages, path, created) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, service, bookid) DO UPDATE SET title = excluded.title, pages = excluded.pages, path = excluded.path, created = excluded.created",
			(userid, service, bookid, title, pages, path, time.time()),
		)

def listbooks(userid):
	with connect() as conn:
		rows = conn.execute("SELECT * FROM books WHERE user_id = ? ORDER BY created DESC", (userid,)).fetchall()
	return [dict(row) for row in rows]

def getbook(userid, bookid):
	with connect() as conn:
		row = conn.execute("SELECT * FROM books WHERE user_id = ? AND id = ?", (userid, bookid)).fetchone()
	return dict(row) if row else None
