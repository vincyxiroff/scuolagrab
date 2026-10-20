'''HTTP client for the scuolagrab server used by the app.

The app registers/logs in on the server at startup and receives a session token
kept in memory for the whole run. The encrypted accounts travel as opaque blobs
(nonce + ciphertext): see vault.py for the encryption.
'''

import requests

# (connect, read): a server that is down must say so at once, not after a long wait
TIMEOUT = (5, 20)

class ServerError(Exception):
	pass

class SessionExpired(ServerError):
	pass

class Client:
	def __init__(self, baseurl):
		self.baseurl = baseurl.strip().rstrip("/")
		if not self.baseurl.startswith(("http://", "https://")):
			raise ServerError("server address must start with http:// or https://")

	def request(self, method, path, token=None, **kwargs):
		headers = {"Accept": "application/json"}
		if token:
			headers["Authorization"] = "Bearer " + token
		try:
			response = requests.request(method, self.baseurl + path, timeout=TIMEOUT, headers=headers, **kwargs)
		except requests.RequestException as e:
			raise ServerError(f"server not reachable ({e.__class__.__name__})") from e
		try:
			data = response.json()
		except ValueError:
			raise ServerError(f"invalid reply from the server (HTTP {response.status_code})") from e
		if response.status_code == 404 and path.startswith("/api/app/"):
			# a server that was never updated does not know the app API
			raise ServerError("this server has no app API yet: update scuolagrab on the server")
		if response.status_code == 401:
			raise SessionExpired("session expired, restart the app and log in again")
		if response.status_code >= 400:
			raise ServerError(data.get("error") or f"HTTP {response.status_code}")
		return data

	def register(self, username, password):
		return self.request("POST", "/api/app/register", json={"username": username, "password": password})

	def login(self, username, password):
		return self.request("POST", "/api/app/login", json={"username": username, "password": password})

	def logout(self, token):
		self.request("POST", "/api/app/logout", token=token)

	def saveaccount(self, token, service, blob):
		return self.request("PUT", "/api/app/vault/" + service, token=token, json={"nonce": blob["nonce"], "data": blob["data"]})

	def deleteaccount(self, token, service):
		return self.request("DELETE", "/api/app/vault/" + service, token=token)
