'''Encrypted store for the school platform accounts.

The key is derived inside the app from the scuolagrab password the user types at
startup: the server only ever receives a nonce and the ciphertext, so a copy of
the database is not enough to read the saved accounts.

key = PBKDF2-HMAC-SHA256(password, salt stored per user on the server)
blob = AES-256-GCM(key, nonce, json({"username": ..., "password": ...}))
aad = "scuolagrab-vault|<userid>|<service>"  (binds an entry to its owner and service)
'''

import base64
import hashlib
import json
import os

from Crypto.Cipher import AES

ITERATIONS = 300_000
KEYLEN = 32
NONCELEN = 12
MAXDATA = 16384

class VaultError(Exception):
	pass

def newsalt():
	return os.urandom(16).hex()

def derivekey(password, salt):
	'''Key for one user, from the password and the salt the server stores for it'''
	if not password:
		raise VaultError("password required")
	try:
		raw = bytes.fromhex(salt)
	except (TypeError, ValueError) as e:
		raise VaultError("invalid salt from the server") from e
	if len(raw) < 8:
		raise VaultError("invalid salt from the server")
	return hashlib.pbkdf2_hmac("sha256", password.encode(), raw, ITERATIONS, KEYLEN)

def aad(userid, service):
	return f"scuolagrab-vault|{userid}|{service}".encode()

def encrypt(key, userid, service, account):
	'''Return the blob to send to the server'''
	payload = json.dumps({"username": account.get("username", ""), "password": account.get("password", "")}, separators=(",", ":")).encode()
	nonce = os.urandom(NONCELEN)
	cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
	cipher.update(aad(userid, service))
	ciphertext, tag = cipher.encrypt_and_digest(payload)
	blob = {"nonce": base64.b64encode(nonce).decode(), "data": base64.b64encode(ciphertext + tag).decode()}
	if len(blob["data"]) > MAXDATA:
		raise VaultError("entry too large")
	return blob

def decrypt(key, userid, service, blob):
	try:
		nonce = base64.b64decode(blob["nonce"], validate=True)
		raw = base64.b64decode(blob["data"], validate=True)
	except (KeyError, TypeError, ValueError) as e:
		raise VaultError("damaged entry") from e
	if len(nonce) != NONCELEN or len(raw) < 17:
		raise VaultError("damaged entry")
	cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
	cipher.update(aad(userid, service))
	try:
		plain = cipher.decrypt_and_verify(raw[:-16], raw[-16:])
	except ValueError as e:
		# wrong password or the entry was changed/copied from another user
		raise VaultError("wrong password or damaged entry") from e
	try:
		data = json.loads(plain)
	except ValueError as e:
		raise VaultError("damaged entry") from e
	if not isinstance(data, dict):
		raise VaultError("damaged entry")
	return {"username": str(data.get("username", "")), "password": str(data.get("password", ""))}
