# scuolagrab

**Made by vincyxiroff**

`python` · `pdf` · `schoolbooks` · `italy` · `bsmart` · `mondadori-hub-scuola` · `sanoma-my-place` · `self-hosted` · `cli` · `gui` · `libri-digitali`

Download your Italian digital schoolbooks as PDF, with table of contents and page labels rebuilt. CLI for your PC, Tkinter GUI, and a self-hosted web server you can use from any browser.

Scarica i tuoi libri di testo digitali in PDF, con indice e page label ricostruiti. CLI per il PC, GUI Tkinter e un server web self-hosted utilizzabile da qualsiasi browser.

[English](#english) · [Italiano](#italiano)

---

# English

## Contents

- [What is it](#what-is-it)
- [Supported services](#supported-services)
- [How it works](#how-it-works)
- [Client setup](#client-setup)
  - [Client requirements](#client-requirements)
  - [Windows](#windows)
  - [Linux and macOS](#linux-and-macos)
  - [First run](#first-run)
  - [Local data](#local-data)
  - [Prebuilt apps](#prebuilt-apps)
  - [Build the apps yourself](#build-the-apps-yourself)
- [Server setup](#server-setup)
  - [Server requirements](#server-requirements)
  - [Automatic install script](#automatic-install-script)
  - [Install](#install)
  - [First start](#first-start)
  - [systemd service](#systemd-service)
  - [Backups and security](#backups-and-security)
  - [Update](#update)
- [Browser client](#browser-client)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Service notes](#service-notes)
- [Troubleshooting](#troubleshooting)
- [License and disclaimer](#license-and-disclaimer)

## What is it

`scuolagrab` talks directly to the platforms' APIs and viewer assets instead of driving the web reader. It logs in with your school account, reads your library, downloads the pages and rebuilds a single PDF per book, adding the table of contents and, when the platform provides reliable data, the original page labels.

Three ways to use it:

| mode | command | runs on |
| ---- | ------- | ------- |
| CLI | `python3 main.py` | your PC |
| GUI | `python3 gui.py` | your PC |
| Web server | `python3 server/app.py` | a server, used from a browser |

## Supported services

Only the services tested with a real account are exposed by the program:

| service | code | PDF | table of contents | notes |
| ------- | :--: | :-: | :---------------: | ----- |
| bSmart | `bsm` | yes | yes | full quality, large files (100+ MB) |
| Mondadori HUB Scuola | `hbs` | yes | yes | downloaded one chapter archive at a time |
| Sanoma My Place | `plc` | yes | yes | pages are SVG assets rendered to PDF: slower, text not selectable |

The other modules in `services/` stay in the repository for reference but are not shown in the CLI, the GUI or the server because they have not been tested.

## How it works

1. Log in to the platform account (email/password) and store a token.
2. Read the user's library.
3. Download pages (PDF files, chapter archives or SVG pages) and rebuild the book with PyMuPDF.
4. Build the table of contents from the book data; add page labels when the platform provides them reliably.

## Client setup

### Client requirements

- **Python 3.10 or newer**
- internet connection
- Chromium (installed by the setup, ~130 MB) for the Sanoma My Place login

### Windows

1. Install Python from [python.org](https://www.python.org/downloads/) and **check "Add python to PATH"** during the setup.
2. Download the project: ZIP from GitHub (then extract it) or `git clone`.
3. Open **PowerShell** in the project folder.
4. Start it:

```powershell
py main.py     # CLI
py gui.py      # GUI
```

### Linux and macOS

```bash
# Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip git
# macOS: brew install python3 git

git clone https://github.com/vincyxiroff/scuolagrab.git
cd scuolagrab

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
```

On Linux, if Chromium does not start because system libraries are missing:

```bash
sudo python3 -m playwright install-deps chromium
```

### First run

At startup the program checks its dependencies: if a Python package or Chromium is missing it asks whether to install it, otherwise it prints the manual commands:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

On the first launch a local scuolagrab user is created (username and password stay on your PC), then:

1. `d` — choose the service, enter the platform email and password once.
2. Pick the books: `0`, `0,3`, `2-5`, `all`/`a`; empty input cancels.
3. PDFs are saved in `files/<service>/<id>.pdf`.

The GUI does the same with buttons: choose the service, **Accedi**, **Carica libreria**, select the books and press **Scarica selezionati** (or **Scarica tutti**).

### Local data

```
files/<service>/<id>.pdf        downloaded books
files/<service>/cover-<id>.png  covers (with Cover = yes)
db.json                         local users, tokens and history (do not commit)
config.ini                      local configuration (created from config-default.ini)
```

Platform tokens are stored in plain text in `db.json`: the file is gitignored, do not share it.

### Prebuilt apps

Releases are automatic: every push to `master`/`main` makes GitHub Actions create the next version tag (patch bump of the latest tag, `v1.0.0` the first time), build the four apps and publish one release with the files and the changelog generated from commits and pull requests.

- start from a specific version: Actions → **build apps** → **Run workflow**, with `version = v1.2.3`
- skip the release for a commit: put `[skip ci]` in the commit message
- the tag is created by the workflow, you never push it by hand

| system | file | notes |
| ------ | ---- | ----- |
| Linux x86_64 | `scuolagrab-x86_64.AppImage` | `chmod +x` and run it |
| Windows x64 | `scuolagrab-windows-x64.zip` → `scuolagrab.exe` | unsigned: SmartScreen → "More info" → "Run anyway" |
| macOS arm64/x64 | `scuolagrab-macos-*.zip` → `scuolagrab.app` | unsigned: right click → Open, or `xattr -dr com.apple.quarantine scuolagrab.app` |

The apps keep config, database and PDFs in the user data folder: `~/.local/share/scuolagrab` (Linux), `%APPDATA%\scuolagrab` (Windows), `~/Library/Application Support/scuolagrab` (macOS). On Linux and Windows Chromium is bundled, so the Sanoma login works out of the box; on macOS PyInstaller cannot sign Chrome's nested `.app`, so the app downloads Chromium (~130 MB) on first launch into its data folder. On Linux, if Chromium complains about missing libraries: `sudo apt install libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1`.

### Build the apps yourself

```bash
python3 -m pip install -r requirements.txt pyinstaller
python3 packaging/build.py                 # bundles Chromium (~400 MB)
python3 packaging/build.py --no-browsers   # smaller, Sanoma needs Chromium installed later
```

The files end up in `packaging/dist/` (AppImage on Linux, ZIP with the `.exe` on Windows, ZIP with the `.app` on macOS). PyInstaller does not cross-compile: build on the target system. On macOS Chromium is not bundled by default (codesign fails on Chrome's nested `.app`): pass `--browsers` to force it.

`.github/workflows/build.yml` runs the script on Linux, Windows, macOS arm64 and macOS x64, creates the version tag and then one release with every file attached and the changelog generated automatically.

## Server setup

`server/` is a self-contained web version with no extra framework (standard library only). Users, session cookies and platform logins live in a SQLite database **on the server**; the browser only keeps an `HttpOnly` session cookie.

### Server requirements

- a Linux server (Ubuntu/Debian 22.04+ works fine) with Python 3.10+
- 1 vCPU, 1 GB RAM, ~2 GB disk (Chromium + PDFs)
- port **8749** (configurable with `--port`)

### Automatic install script

`install.sh` does the whole setup on Debian/Ubuntu: system packages, the `scuolagrab` user, the project in `/opt/scuolagrab`, the virtualenv, Chromium, the systemd service and (optionally) the firewall rule. It asks for folder, address and port, and it is safe to run again to repair an installation.

```bash
cd ~
git clone https://github.com/vincyxiroff/scuolagrab.git
sudo bash scuolagrab/install.sh
```

Then open `http://SERVER-IP:8749`. If you prefer to do it by hand, follow the steps below.

### Install

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# dedicated service user without login; the folder is created empty below, so git can clone into it
sudo useradd --system --home-dir /opt/scuolagrab --shell /usr/sbin/nologin scuolagrab
sudo mkdir -p /opt/scuolagrab
sudo chown scuolagrab:scuolagrab /opt/scuolagrab
sudo -u scuolagrab git clone https://github.com/vincyxiroff/scuolagrab.git /opt/scuolagrab

cd /opt/scuolagrab
sudo -u scuolagrab python3 -m venv .venv
sudo -u scuolagrab .venv/bin/pip install -r requirements.txt
sudo -u scuolagrab .venv/bin/python -m playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium
```

### First start

```bash
cd /opt/scuolagrab
sudo -u scuolagrab .venv/bin/python server/app.py --host 0.0.0.0 --port 8749
```

Then open `http://SERVER-IP:8749`: register a user, choose the service, save the platform login, load the library and download the books. PDFs stay on the server and are downloaded from the link in the page.

> The default address in the code is `84.8.252.233:8749`. On any other machine always pass the right one: `--host 0.0.0.0` (all interfaces) or `SBG_HOST`/`SBG_PORT` environment variables. If the IP does not belong to the machine the program says so and exits.

### systemd service

`/etc/systemd/system/scuolagrab.service`:

```ini
[Unit]
Description=scuolagrab server
After=network.target

[Service]
Type=simple
User=scuolagrab
WorkingDirectory=/opt/scuolagrab
Environment=SBG_HOST=0.0.0.0
Environment=SBG_PORT=8749
ExecStart=/opt/scuolagrab/.venv/bin/python server/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now scuolagrab
sudo systemctl status scuolagrab
sudo journalctl -u scuolagrab -f      # logs
```

Firewall: `sudo ufw allow 8749/tcp` so the page is reachable from other machines.

### Backups and security

```
server/data/server.db    users, sessions, platform logins, download history
server/data/server.db-*  SQLite WAL files
files/<service>/*.pdf    downloaded books
```

- Platform tokens are plain text in the database: protect the file (`chmod 600`) and the backups.
- Recommended backup: `server/data/` + `files/` (copy the database while the service is stopped, or with `sqlite3 server.db ".backup backup.db"`).
- Running downloads are kept in memory: restarting the server loses the running jobs, not the completed PDFs.

### Update

```bash
cd /opt/scuolagrab
sudo -u scuolagrab git pull
sudo -u scuolagrab .venv/bin/pip install -r requirements.txt
sudo systemctl restart scuolagrab
```

## Browser client

1. Open `http://SERVER-IP:8749` (or the HTTPS domain).
2. **Register** with a username and password: these are scuolagrab credentials, not the school ones.
3. Choose the service, enter the platform email and password and press **Salva login**: they stay on the server.
4. **Carica libreria**, select one or more books and press **Scarica selezionati** (or **Scarica tutti**).
5. Follow the progress in "Download in corso"; when it is done the PDF appears in "I miei download".

Each server user has their own logins and books, isolated from the others. The browser never stores platform passwords or tokens. The server speaks plain HTTP: use it on a trusted network (home LAN, VPN) or protect it with the firewall, because without TLS anyone on the path could read the traffic.

## Configuration

`config.ini` is created automatically from `config-default.ini` on first run (gitignored). Main options:

| section | option | meaning |
| ------- | ------ | ------- |
| `[DEFAULT]` | `EzSave` | save with PyMuPDF recommended defaults (takes priority) |
| | `Compress`, `Garbage`, `Clean` | compression when `EzSave = no` |
| | `Cover` | download covers |
| | `Author` | author in the PDF metadata (empty = no author) |
| `[pdfgrabber]` | `AskPassword` | ask for the local user password at every start |
| | `ShowBanner` | show the CLI banner |
| `[hbs]` | `Downloader` | `chapters` (default, the only one still served) or `documentengine` with automatic fallback |
| | `ClientVersion` | client version sent to the Mondadori viewer |
| `[plc]` | `Workers` | pages downloaded in parallel (default 6) |
| | `PageLabels` | use the original Sanoma page labels |
| `[bsm]` | `Preactivations` | include preview/preactivated books |

The `[pdfgrabber]` section keeps its historical name for compatibility with existing configurations.

## Project structure

```
main.py              CLI (rich)
gui.py               GUI (Tkinter)
dependencies.py      dependency check and installer at startup
utils.py             services loading, downloads, metadata, local database
lib.py               page label helpers
config.py            config.ini reader
services/            one module per platform (bsm, hbs, plc, ...)
services/oneshot/    one-shot link services (not exposed)
server/app.py        web server (HTTP + API + jobs)
server/db.py         server SQLite layer
server/static/       web interface
config-default.ini   default options
install.sh           guided server installer
paths.py             writable data folder for the packaged app
packaging/           PyInstaller spec + cross-platform build script
.github/workflows/   GitHub Actions build/release workflow
```

## Service notes

**Mondadori HUB Scuola.** The viewer's single-PDF endpoint answers 403/500 server side, so the book is downloaded one chapter archive at a time (`Downloader = chapters`). If Mondadori re-enables it, set `Downloader = documentengine`: scuolagrab tries it first and falls back on its own.

**Sanoma My Place.** The login goes through Auth0 (`login.sanoma.it`) and runs in a headless Chromium managed by playwright. Pages are SVG files with embedded images converted to PDF: slower than the other services, and the text is not selectable. Only fixed-layout books ("My Digital Book") are supported; "Libro liquido" resources are skipped. The token is the `MY_PLACE_SESSION` cookie and expires, so sooner or later the program asks for the password again.

**bSmart.** Downloads the asset packs and decrypts the page PDFs. Files can be large (100+ MB) but the text stays selectable.

## Troubleshooting

| problem | fix |
| ------- | --- |
| `Address already in use` | the port is busy: use `--port 8750` or free it (`ss -ltnp \| grep 8749`) |
| server exits with `Cannot assign requested address` | the default IP is not this machine: use `--host 0.0.0.0` |
| Sanoma login: "Utente non riconosciuto" | wrong email/password, or the account has not been moved from Pearson to Sanoma yet |
| Sanoma login times out | Auth0 is slow or rate limiting: retry after a few minutes |
| "token expired" / library unavailable | log in to the service again (the token is a session) |
| `playwright` cannot find Chromium | `python3 -m playwright install chromium` |
| Chromium fails to start on Linux | `sudo python3 -m playwright install-deps chromium` |
| `pip` refuses to install (PEP 668) | use a virtualenv (`.venv`) as in the guide |
| Sanoma PDF without selectable text | expected: pages are viewer images/vectors |
| Windows warns about an unknown publisher | the exe is unsigned: "More info" → "Run anyway" |
| macOS says the app is damaged or from an unknown developer | right click → Open, or `xattr -dr com.apple.quarantine scuolagrab.app` |
| the AppImage does not start | `chmod +x scuolagrab-x86_64.AppImage`; for the Sanoma login install `libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1` |

## License and disclaimer

Released under the **AGPL-3.0** license (see `LICENSE`).

Provided "as is", without warranty. Use it only for books you are legitimately allowed to access. The author is not responsible for any misuse or damage caused by this tool.

---

# Italiano

## Indice

- [Panoramica](#panoramica)
- [Servizi supportati](#servizi-supportati)
- [Come funziona](#come-funziona)
- [Setup del client](#setup-del-client)
  - [Requisiti del client](#requisiti-del-client)
  - [Windows](#windows-1)
  - [Linux e macOS](#linux-e-macos)
  - [Primo avvio](#primo-avvio)
  - [Dati locali](#dati-locali)
  - [App già pronte](#app-già-pronte)
  - [Compilare le app](#compilare-le-app)
- [Setup del server](#setup-del-server)
  - [Requisiti del server](#requisiti-del-server)
  - [Script di installazione](#script-di-installazione)
  - [Installazione](#installazione)
  - [Primo avvio del server](#primo-avvio-del-server)
  - [Servizio systemd](#servizio-systemd)
  - [Backup e sicurezza](#backup-e-sicurezza)
  - [Aggiornamento](#aggiornamento)
- [Client via browser](#client-via-browser)
- [Configurazione](#configurazione)
- [Struttura del progetto](#struttura-del-progetto)
- [Note per servizio](#note-per-servizio)
- [Problemi comuni](#problemi-comuni)
- [Licenza e disclaimer](#licenza-e-disclaimer)

## Panoramica

`scuolagrab` parla direttamente con le API e con gli asset dei viewer delle piattaforme, senza guidare il lettore web. Fa il login con l'account della scuola, legge la libreria, scarica le pagine e ricostruisce un unico PDF per libro, aggiungendo l'indice e — quando i dati della piattaforma sono affidabili — le page label originali.

Si usa in tre modi:

| modalità | comando | dove gira |
| -------- | ------- | --------- |
| CLI | `python3 main.py` | sul tuo PC |
| GUI | `python3 gui.py` | sul tuo PC |
| Server web | `python3 server/app.py` | su un server, si usa dal browser |

## Servizi supportati

Solo i servizi provati con un account reale sono esposti dal programma:

| servizio | codice | PDF | indice | note |
| -------- | :----: | :-: | :----: | ---- |
| bSmart | `bsm` | sì | sì | qualità piena, file grandi (100+ MB) |
| Mondadori HUB Scuola | `hbs` | sì | sì | scaricato un archivio di capitolo alla volta |
| Sanoma My Place | `plc` | sì | sì | pagine SVG del viewer convertite in PDF: più lento, testo non selezionabile |

Gli altri moduli in `services/` restano nel repository come riferimento ma non compaiono in CLI, GUI o server perché non sono stati testati.

## Come funziona

1. Login all'account della piattaforma (email/password) e salvataggio del token.
2. Lettura della libreria dell'utente.
3. Download delle pagine (file PDF, archivi di capitoli o pagine SVG) e ricostruzione del libro con PyMuPDF.
4. Indice generato dai dati del libro; page label aggiunte quando la piattaforma le fornisce in modo affidabile.

## Setup del client

### Requisiti del client

- **Python 3.10 o superiore**
- connessione a internet
- Chromium (installato dal setup, ~130 MB) per il login Sanoma My Place

### Windows

1. Installa Python da [python.org](https://www.python.org/downloads/) e **spunta "Add python to PATH"** durante l'installazione.
2. Scarica il progetto: ZIP da GitHub (poi scompattalo) oppure `git clone`.
3. Apri **PowerShell** nella cartella del progetto.
4. Avvia:

```powershell
py main.py     # CLI
py gui.py      # GUI
```

### Linux e macOS

```bash
# Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip git
# macOS: brew install python3 git

git clone https://github.com/vincyxiroff/scuolagrab.git
cd scuolagrab

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
```

Su Linux, se Chromium non parte per librerie di sistema mancanti:

```bash
sudo python3 -m playwright install-deps chromium
```

### Primo avvio

All'avvio il programma controlla le dipendenze: se manca un package Python o Chromium chiede se installarlo, altrimenti mostra i comandi da lanciare a mano:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Al primo utilizzo viene creato un utente locale di scuolagrab (username e password restano sul tuo PC), poi:

1. `d` — scegli il servizio, inserisci email e password della piattaforma una sola volta.
2. Scegli i libri: `0`, `0,3`, `2-5`, `all`/`a`, invio vuoto per annullare.
3. I PDF finiscono in `files/<servizio>/<id>.pdf`.

La GUI fa le stesse cose con i pulsanti: scegli il servizio, **Accedi**, **Carica libreria**, seleziona i libri e **Scarica selezionati** (o **Scarica tutti**).

### Dati locali

```
files/<servizio>/<id>.pdf        libri scaricati
files/<servizio>/cover-<id>.png  copertine (con Cover = yes)
db.json                          utenti locali, token e storico (non committare)
config.ini                       configurazione locale (creata da config-default.ini)
```

I token delle piattaforme sono salvati in chiaro in `db.json`: quel file è gitignored, non condividerlo.

### App già pronte

Le release sono automatiche: ogni push su `master`/`main` fa creare a GitHub Actions il tag della versione successiva (patch incrementata rispetto all'ultimo tag, `v1.0.0` la prima volta), compila le quattro app e pubblica un'unica release con i file e il changelog generato da commit e pull request.

- partire da una versione specifica: Actions → **build apps** → **Run workflow**, con `version = v1.2.3`
- saltare la release per un commit: metti `[skip ci]` nel messaggio di commit
- il tag lo crea il workflow, non serve pusharlo a mano

| sistema | file | note |
| ------- | ---- | ----- |
| Linux x86_64 | `scuolagrab-x86_64.AppImage` | `chmod +x` e avviala |
| Windows x64 | `scuolagrab-windows-x64.zip` → `scuolagrab.exe` | non firmata: SmartScreen → "Ulteriori informazioni" → "Esegui comunque" |
| macOS arm64/x64 | `scuolagrab-macos-*.zip` → `scuolagrab.app` | non firmata: tasto destro → Apri, oppure `xattr -dr com.apple.quarantine scuolagrab.app` |

Le app tengono config, database e PDF nella cartella dati dell'utente: `~/.local/share/scuolagrab` (Linux), `%APPDATA%\scuolagrab` (Windows), `~/Library/Application Support/scuolagrab` (macOS). Su Linux e Windows Chromium è incluso, quindi il login Sanoma funziona senza installare altro; su macOS PyInstaller non riesce a firmare l'`.app` annidata di Chrome, quindi l'app scarica Chromium (~130 MB) al primo avvio nella sua cartella dati. Su Linux, se Chromium lamenta librerie mancanti: `sudo apt install libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1`.

### Compilare le app

```bash
python3 -m pip install -r requirements.txt pyinstaller
python3 packaging/build.py                 # include Chromium (~400 MB)
python3 packaging/build.py --no-browsers   # più piccola, Sanoma richiede Chromium a parte
```

I file finiscono in `packaging/dist/` (AppImage su Linux, ZIP con `.exe` su Windows, ZIP con `.app` su macOS). PyInstaller non fa cross-compilazione: compila sul sistema di destinazione. Su macOS Chromium non è incluso di default (codesign fallisce sull'`.app` annidata di Chrome): usa `--browsers` per forzarlo.

`.github/workflows/build.yml` esegue lo script su Linux, Windows, macOS arm64 e macOS x64, crea il tag di versione e poi un'unica release con tutti i file allegati e il changelog generato automaticamente.

## Setup del server

La cartella `server/` contiene una versione web autonoma, senza framework aggiuntivi (solo standard library). Utenti, sessioni e login delle piattaforme stanno in un database SQLite **sul server**; nel browser resta solo un cookie di sessione `HttpOnly`.

### Requisiti del server

- un server Linux (Ubuntu/Debian 22.04+ va benissimo) con Python 3.10+
- 1 vCPU, 1 GB di RAM, ~2 GB di disco (Chromium + i PDF)
- porta **8749** (modificabile con `--port`)

### Script di installazione

`install.sh` fa tutto il setup su Debian/Ubuntu: pacchetti di sistema, utente `scuolagrab`, progetto in `/opt/scuolagrab`, virtualenv, Chromium, servizio systemd e (se vuoi) regola del firewall. Chiede cartella, indirizzo e porta, e si può rieseguire per riparare un'installazione.

```bash
cd ~
git clone https://github.com/vincyxiroff/scuolagrab.git
sudo bash scuolagrab/install.sh
```

Poi apri `http://IP-DEL-SERVER:8749`. Se preferisci farlo a mano, segui i passaggi qui sotto.

### Installazione

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# utente dedicato, senza login; la cartella viene creata qui sotto vuota, così git può clonare dentro
sudo useradd --system --home-dir /opt/scuolagrab --shell /usr/sbin/nologin scuolagrab
sudo mkdir -p /opt/scuolagrab
sudo chown scuolagrab:scuolagrab /opt/scuolagrab
sudo -u scuolagrab git clone https://github.com/vincyxiroff/scuolagrab.git /opt/scuolagrab

cd /opt/scuolagrab
sudo -u scuolagrab python3 -m venv .venv
sudo -u scuolagrab .venv/bin/pip install -r requirements.txt
sudo -u scuolagrab .venv/bin/python -m playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium
```

### Primo avvio del server

```bash
cd /opt/scuolagrab
sudo -u scuolagrab .venv/bin/python server/app.py --host 0.0.0.0 --port 8749
```

Poi apri `http://IP-DEL-SERVER:8749`: registra un utente, scegli il servizio, salva il login della piattaforma, carica la libreria e scarica i libri. I PDF restano sul server e si scaricano dal link nella pagina.

> Il valore predefinito nel codice è `84.8.252.233:8749`. Su un altro server indica sempre l'indirizzo giusto: `--host 0.0.0.0` (tutte le interfacce) oppure le variabili d'ambiente `SBG_HOST`/`SBG_PORT`. Se l'IP non appartiene alla macchina il programma lo dice e si ferma.

### Servizio systemd

`/etc/systemd/system/scuolagrab.service`:

```ini
[Unit]
Description=scuolagrab server
After=network.target

[Service]
Type=simple
User=scuolagrab
WorkingDirectory=/opt/scuolagrab
Environment=SBG_HOST=0.0.0.0
Environment=SBG_PORT=8749
ExecStart=/opt/scuolagrab/.venv/bin/python server/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now scuolagrab
sudo systemctl status scuolagrab
sudo journalctl -u scuolagrab -f      # log
```

Firewall: `sudo ufw allow 8749/tcp` così la pagina è raggiungibile dalle altre macchine.

### Backup e sicurezza

```
server/data/server.db    utenti, sessioni, login delle piattaforme, storico download
server/data/server.db-*  file WAL di SQLite
files/<servizio>/*.pdf   libri scaricati
```

- I token delle piattaforme sono in chiaro nel database: proteggi il file (`chmod 600`) e i backup.
- Backup consigliato: `server/data/` + `files/` (copia il database a servizio fermo, o con `sqlite3 server.db ".backup backup.db"`).
- I download in corso sono tenuti in memoria: riavviando il server si perdono i job attivi, non i PDF già completati.

### Aggiornamento

```bash
cd /opt/scuolagrab
sudo -u scuolagrab git pull
sudo -u scuolagrab .venv/bin/pip install -r requirements.txt
sudo systemctl restart scuolagrab
```

## Client via browser

1. Apri `http://IP-DEL-SERVER:8749` (o il dominio HTTPS).
2. **Registrati** con un username e una password: sono le credenziali di scuolagrab, non quelle della scuola.
3. Scegli il servizio, inserisci email e password della piattaforma e premi **Salva login**: restano sul server.
4. **Carica libreria**, seleziona uno o più libri e premi **Scarica selezionati** (o **Scarica tutti**).
5. Segui il progresso nella scheda "Download in corso"; a fine lavoro il PDF è in "I miei download".

Ogni utente del server ha i suoi login e i suoi libri, isolati dagli altri. Il browser non salva mai password o token delle piattaforme. Il server parla HTTP in chiaro: usalo su una rete fidata (LAN di casa, VPN) o proteggilo col firewall, perché senza TLS chi sta sulla rete può leggere il traffico.

## Configurazione

`config.ini` viene creato automaticamente da `config-default.ini` al primo avvio (gitignored). Le opzioni principali:

| sezione | opzione | significato |
| ------- | ------- | ----------- |
| `[DEFAULT]` | `EzSave` | salvataggio con i default consigliati di PyMuPDF (prioritario) |
| | `Compress`, `Garbage`, `Clean` | compressione quando `EzSave = no` |
| | `Cover` | scarica le copertine |
| | `Author` | autore nei metadati del PDF (vuoto = nessun autore) |
| `[pdfgrabber]` | `AskPassword` | chiede la password dell'utente locale a ogni avvio |
| | `ShowBanner` | banner all'avvio della CLI |
| `[hbs]` | `Downloader` | `chapters` (default, l'unico ancora servito) o `documentengine` con fallback automatico |
| | `ClientVersion` | versione client inviata al viewer Mondadori |
| `[plc]` | `Workers` | pagine scaricate in parallelo (default 6) |
| | `PageLabels` | usa le page label originali Sanoma |
| `[bsm]` | `Preactivations` | include i libri in anteprima/preattivazione |

La sezione `[pdfgrabber]` mantiene il nome storico per compatibilità con le configurazioni esistenti.

## Struttura del progetto

```
main.py              CLI (rich)
gui.py               GUI (Tkinter)
dependencies.py      controllo/installazione dipendenze all'avvio
utils.py             caricamento servizi, download, metadati, database locale
lib.py               helper per le page label
config.py            lettura di config.ini
services/            un modulo per piattaforma (bsm, hbs, plc, ...)
services/oneshot/    servizi da link una-tantum (non esposti)
server/app.py        server web (HTTP + API + job)
server/db.py         livello SQLite del server
server/static/       interfaccia web
config-default.ini   opzioni predefinite
install.sh           installer guidato del server
paths.py             cartella dati scrivibile per l'app pacchettizzata
packaging/           spec PyInstaller + script di build multipiattaforma
.github/workflows/   workflow GitHub Actions di build/release
```

## Note per servizio

**Mondadori HUB Scuola.** L'endpoint PDF singolo del viewer risponde 403/500 lato server, quindi il libro viene scaricato un archivio di capitolo alla volta (`Downloader = chapters`). Se Mondadori lo riattiva, imposta `Downloader = documentengine`: scuolagrab lo prova e torna da solo ai capitoli in caso di errore.

**Sanoma My Place.** Il login passa da Auth0 (`login.sanoma.it`) e avviene in un Chromium headless gestito da playwright. Le pagine sono file SVG con le immagini incorporate, convertite in PDF: più lento degli altri servizi e testo non selezionabile. Sono supportati solo i libri a layout fisso ("My Digital Book"); i "Libro liquido" vengono saltati. Il token è il cookie `MY_PLACE_SESSION` e scade: prima o poi il programma richiede di nuovo la password.

**bSmart.** Scarica i pacchetti di asset e decripta i PDF pagina per pagina. I file possono essere grandi (100+ MB) ma il testo resta selezionabile.

## Problemi comuni

| problema | soluzione |
| -------- | --------- |
| `Address already in use` | la porta è occupata: usa `--port 8750` o liberala (`ss -ltnp \| grep 8749`) |
| il server esce con `Cannot assign requested address` | l'IP predefinito non è della macchina: usa `--host 0.0.0.0` |
| login Sanoma: "Utente non riconosciuto" | email/password errate, o account non ancora trasferito da Pearson a Sanoma |
| login Sanoma in timeout | Auth0 è lento o sta limitando i tentativi: riprova dopo qualche minuto |
| "token scaduto" / libreria non disponibile | rifai il login al servizio (il token è una sessione) |
| `playwright` non trova Chromium | `python3 -m playwright install chromium` |
| Chromium non parte su Linux | `sudo python3 -m playwright install-deps chromium` |
| `pip` rifiuta l'installazione (PEP 668) | usa un virtualenv (`.venv`) come nella guida |
| PDF Sanoma senza testo selezionabile | atteso: le pagine sono immagini/vettori del viewer |
| Windows avvisa di un editore sconosciuto | l'exe non è firmato: "Ulteriori informazioni" → "Esegui comunque" |
| macOS dice che l'app è danneggiata o di uno sviluppatore sconosciuto | tasto destro → Apri, oppure `xattr -dr com.apple.quarantine scuolagrab.app` |
| l'AppImage non parte | `chmod +x scuolagrab-x86_64.AppImage`; per il login Sanoma installa `libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1` |

## Licenza e disclaimer

Distribuito con licenza **AGPL-3.0** (vedi `LICENSE`).

Fornito "così com'è", senza garanzie. Usalo solo per libri a cui hai legittimamente accesso. L'autore non è responsabile per usi impropri o danni derivanti dall'uso del software.
