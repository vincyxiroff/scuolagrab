'''Translations for the graphical app (english / italian).

Only gui.py uses this module: the CLI keeps its english output. The language is
chosen in the login page or in the header and saved in db.json (settings table);
without a saved choice it follows the system locale.
'''

import os

LANGUAGES = {"en": "English", "it": "Italiano"}
DEFAULT = "en"

STRINGS = {
	# window titles
	"app.title": {"en": "scuolagrab — by vincyxiroff", "it": "scuolagrab — by vincyxiroff"},
	"app.title.login": {"en": "scuolagrab — sign in or register", "it": "scuolagrab — accedi o registrati"},
	"app.title.register": {"en": "scuolagrab — registration", "it": "scuolagrab — registrazione"},
	"app.title.user": {"en": "scuolagrab — {user}", "it": "scuolagrab — {user}"},
	"app.tagline": {"en": "by vincyxiroff", "it": "by vincyxiroff"},
	"app.crash": {"en": "Unexpected error: {error}\n\nDetails in {log}", "it": "Errore imprevisto: {error}\n\nDettagli in {log}"},

	# login page
	"login.hint": {"en": "Sign in with your scuolagrab account, or create one.", "it": "Accedi con il tuo account scuolagrab, oppure creane uno."},
	"login.hint.register": {"en": "The account is created on the server. The same password protects the platform accounts: if you lose it they cannot be recovered.", "it": "L'account viene creato sul server. La stessa password protegge gli account delle piattaforme: se la perdi non si possono recuperare."},
	"login.server": {"en": "Server", "it": "Server"},
	"login.address": {"en": "Address", "it": "Indirizzo"},
	"login.username": {"en": "Username", "it": "Username"},
	"login.password": {"en": "Password", "it": "Password"},
	"login.confirm": {"en": "Repeat password", "it": "Ripeti password"},
	"login.default": {"en": "Default (hosted)", "it": "Predefinito (hostato)"},
	"login.custom": {"en": "Other server", "it": "Altro server"},
	"login.signin": {"en": "Sign in", "it": "Accedi"},
	"login.create": {"en": "Create account", "it": "Crea un account"},
	"login.registeraction": {"en": "Register", "it": "Registrati"},
	"login.back": {"en": "I already have an account", "it": "Ho già un account"},
	"login.note": {"en": "Platform accounts are stored on the server encrypted with this password.", "it": "Gli account delle piattaforme vengono salvati sul server cifrati con questa password."},
	"login.busy.register": {"en": "Creating the account…", "it": "Creazione dell'account…"},
	"login.busy.login": {"en": "Signing in…", "it": "Accesso…"},
	"login.error.url": {"en": "The server address must start with http:// or https://", "it": "L'indirizzo del server deve iniziare con http:// o https://"},
	"login.error.credentials": {"en": "Enter username and password.", "it": "Inserisci username e password."},
	"login.error.short": {"en": "The password must be at least 6 characters long.", "it": "La password deve avere almeno 6 caratteri."},
	"login.error.match": {"en": "The passwords do not match.", "it": "Le password non coincidono."},
	"login.error.unreachable": {"en": "Server not reachable ({detail})", "it": "Server non raggiungibile ({detail})"},
	"login.error.reply": {"en": "Invalid reply from the server ({detail})", "it": "Risposta non valida dal server ({detail})"},

	# main window
	"app.signout": {"en": "Sign out", "it": "Esci"},
	"app.service": {"en": "Service", "it": "Servizio"},
	"app.account": {"en": "Service account", "it": "Account del servizio"},
	"app.email": {"en": "Email / username", "it": "Email / username"},
	"app.signin": {"en": "Sign in", "it": "Accedi"},
	"app.loadlibrary": {"en": "Load library", "it": "Carica libreria"},
	"app.books": {"en": "Books", "it": "Libri"},
	"app.id": {"en": "ID", "it": "ID"},
	"app.title_column": {"en": "Title", "it": "Titolo"},
	"app.folder": {"en": "Saving in", "it": "Salvataggio in"},
	"app.openfolder": {"en": "Open folder", "it": "Apri cartella"},
	"app.downloadselected": {"en": "Download selected", "it": "Scarica selezionati"},
	"app.downloadall": {"en": "Download all", "it": "Scarica tutti"},
	"app.activity": {"en": "Activity", "it": "Attività"},
	"app.ready": {"en": "Ready", "it": "Pronto"},
	"app.error": {"en": "Error", "it": "Errore"},
	"app.token": {"en": "Token saved ✓", "it": "Token salvato ✓"},
	"app.account.saved": {"en": "Account saved on the server ✓", "it": "Account salvato sul server ✓"},
	"app.account.none": {"en": "No saved account", "it": "Nessun account salvato"},
	"app.account.token": {"en": "{text} · token active", "it": "{text} · token attivo"},
	"app.language": {"en": "Language", "it": "Lingua"},

	# log and status messages
	"log.welcome": {"en": "Signed in as {user}: {count} accounts stored on the server.", "it": "Accesso come {user}: {count} account salvati sul server."},
	"log.folder": {"en": "Books are saved in {folder}", "it": "I libri vengono salvati in {folder}"},
	"log.unreadable": {"en": "Accounts that could not be read (different password or damaged data): {list}", "it": "Account non leggibili (password diversa o dati rovinati): {list}"},
	"log.signedout": {"en": "Signed out.", "it": "Uscito."},
	"log.error": {"en": "Error: {error}", "it": "Errore: {error}"},
	"log.loggingin": {"en": "Signing in to {service}…", "it": "Login su {service}…"},
	"log.notsaved": {"en": "Account not saved on the server: {error}", "it": "Account non salvato sul server: {error}"},
	"log.loginfailed": {"en": "Sign in failed: {error}", "it": "Login fallito: {error}"},
	"log.loginok": {"en": "Signed in.", "it": "Login riuscito."},
	"log.loadinglibrary": {"en": "Loading the {service} library…", "it": "Carico la libreria di {service}…"},
	"log.libraryfailed": {"en": "Cannot load the library: {error}", "it": "Impossibile caricare la libreria: {error}"},
	"log.books": {"en": "{count} books found.", "it": "Trovati {count} libri."},
	"log.downloading": {"en": "Downloading {title}…", "it": "Scarico {title}…"},
	"log.saved": {"en": "Saved: {path}", "it": "Salvato: {path}"},
	"log.downloaderror": {"en": "Error on {title}: {error}", "it": "Errore su {title}: {error}"},
	"log.done": {"en": "Done: {downloaded} downloaded, {failed} failed.", "it": "Finito: {downloaded} scaricati, {failed} falliti."},
	"status.signingin": {"en": "Signing in…", "it": "Login in corso…"},
	"status.loginfailed": {"en": "Sign in failed", "it": "Login fallito"},
	"status.loadinglibrary": {"en": "Loading the library…", "it": "Carico la libreria…"},
	"status.libraryfailed": {"en": "Library not available", "it": "Libreria non disponibile"},
	"status.books": {"en": "{count} books", "it": "{count} libri"},
	"status.downloadfailed": {"en": "Download failed", "it": "Download fallito"},
	"status.done": {"en": "{downloaded} downloaded, {failed} failed", "it": "{downloaded} scaricati, {failed} falliti"},

	# errors raised by the app
	"error.tokenrejected": {"en": "the service rejected the token it returned", "it": "il servizio ha rifiutato il token ottenuto"},
	"error.badcredentials": {"en": "invalid credentials", "it": "credenziali non valide"},
	"error.tokenexpired": {"en": "token expired, sign in again", "it": "token scaduto, effettua di nuovo il login"},

	# dialogs
	"dialog.needcredential": {"en": "Enter the email and password of the service.", "it": "Inserisci email e password del servizio."},
	"dialog.needbook": {"en": "Select at least one book.", "it": "Seleziona almeno un libro."},
	"dialog.needlibrary": {"en": "Load the library first.", "it": "Carica prima la libreria."},
	"dialog.failedbooks": {"en": "Some books were not downloaded:\n{list}", "it": "Alcuni libri non sono stati scaricati:\n{list}"},
	"dialog.nofilemanager": {"en": "Cannot open the file manager.\n\nThe books are in:\n{folder}", "it": "Non riesco ad aprire il file manager.\n\nI libri sono in:\n{folder}"},

	# messages returned by the server / apiclient, translated when known
	"server.wrongpassword": {"en": "Wrong username or password.", "it": "Username o password sbagliati."},
	"server.taken": {"en": "That username is already taken.", "it": "Questo username è già in uso."},
	"server.shortpassword": {"en": "The password must be at least 6 characters long.", "it": "La password deve avere almeno 6 caratteri."},
	"server.badusername": {"en": "Username: 3-32 characters (letters, digits, . _ -)", "it": "Username: 3-32 caratteri (lettere, cifre, . _ -)"},
	"server.expired": {"en": "Session expired: sign in again.", "it": "Sessione scaduta: accedi di nuovo."},
	"server.noapi": {"en": "This server has no API for the app yet: update scuolagrab on the server.", "it": "Questo server non ha ancora l'API per l'app: aggiorna scuolagrab sul server."},
	"server.unknownservice": {"en": "Unknown service.", "it": "Servizio sconosciuto."},
	"server.emptyservice": {"en": "Sign in to the service first.", "it": "Prima accedi al servizio."},
	"server.unknown": {"en": "The server refused the request.", "it": "Il server ha rifiutato la richiesta."},
}

# exact messages coming from server/app.py or apiclient.py
SERVERMESSAGES = {
	"wrong username or password": "server.wrongpassword",
	"username already taken": "server.taken",
	"password too short (min 6 characters)": "server.shortpassword",
	"username: 3-32 characters (letters, digits, . _ -)": "server.badusername",
	"session expired, restart the app and log in again": "server.expired",
	"this server has no app API yet: update scuolagrab on the server": "server.noapi",
	"unknown service": "server.unknownservice",
	"no saved login for this service": "server.emptyservice",
	"login required": "server.expired",
}

language = DEFAULT

def detect():
	'''Language of the system, italian only when the locale says so'''
	for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
		value = os.environ.get(name, "")
		if value:
			return "it" if value.lower().startswith("it") else "en"
	return DEFAULT

def setlanguage(code):
	global language
	language = code if code in LANGUAGES else DEFAULT
	return language

def t(key, **fields):
	'''Text for key in the current language (english when the key is missing)'''
	table = STRINGS.get(key)
	if not table:
		return key
	text = table.get(language) or table.get(DEFAULT) or key
	if fields:
		try:
			return text.format(**fields)
		except (KeyError, IndexError):
			return text
	return text

def servermessage(text):
	'''Translate the usual errors sent by the server, leave the others alone'''
	text = str(text)
	key = SERVERMESSAGES.get(text)
	if key:
		return t(key)
	if text.startswith("server not reachable ("):
		return t("login.error.unreachable", detail=text[len("server not reachable ("):-1])
	if text.startswith("invalid reply from the server ("):
		return t("login.error.reply", detail=text[len("invalid reply from the server ("):-1])
	if text.startswith("server address must start with"):
		return t("login.error.url")
	return text
