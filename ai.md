# scuolagrab — note di lavoro

Il progetto deriva da pdfgrabber ed è stato rinominato in **scuolagrab** il 2026-10-20: aggiornati CLI, GUI, server, UI web e README. La sezione `[pdfgrabber]` di `config.ini` mantiene il nome storico per compatibilità.

Data: 2026-10-20

## Cos'è il progetto

`scuolagrab` è un tool in Python (CLI, GUI e server web) che scarica i PDF dei libri di testo (e le copertine) dai portali scolastici italiani, aggirando i viewer web e ricostruendo il libro con indice e (dove possibile) page label.

Struttura:

- `main.py` — interfaccia CLI (rich): login utente pdfgrabber, scelta servizio, lista libri, download, token, riepilogo.
- `utils.py` — orchestrazione: import dinamico dei servizi, salvataggio PDF, metadati, database TinyDB (`db.json`).
- `services/<codice>.py` — un modulo per piattaforma (`hbs`, `bsm`, `znc`, `myl`, `prs`, `psp`, `sbk`, `ees`, `mcm`, `blk`, `hoe`, `dbk`, `olb`, `rfl`, `cmb`, `plc`), più `services/oneshot/` per i link una-tantum.
- `lib.py` — generazione regole per le page label (numeri romani, prefissi, ecc.).
- `config-default.ini` — opzioni globali e per servizio; al primo avvio viene copiato in `config.ini` (gitignored).
- `server/` — versione web: `app.py` (HTTP server stdlib), `db.py` (SQLite), `static/` (UI), DB in `server/data/server.db` (gitignored). Cookie `Secure` attivabile con `SBG_SECURE=1`; IP/porta con `--host/--port` o `SBG_HOST`/`SBG_PORT`.
- `files/<servizio>/<id>.pdf` — output dei download.
- `db.json` — utenti, token e libri scaricati (gitignored).

Ogni servizio espone di norma: `login`, `checktoken`, `library`, `downloadbook`, `cover`, a volte `refreshtoken`.

## Cosa ho fatto oggi

### 1. Riparazione Mondadori HUB Scuola (`services/hbs.py`)

Il comando dell'utente falliva con `JSONDecodeError` dentro `getauth`. Diagnosi con richieste reali alle API:

- `POST ms-pdf.hubscuola.it/i/d/<id>/auth` rispondeva **412**: il servizio Document Engine rifiuta il vecchio header `PSPDFKit-Version` (`client=2020.6.0`). Aggiornato a una versione accettata (`client=2024.1.0`, con lista di fallback e opzione `ClientVersion`). Ora l'auth risponde `200`.
- Il download del PDF singolo però è **rotto lato server**: `/i/d/<id>/h/<layer>/pdf` risponde `403 Forbidden` (rotta non più instradata dall'ALB) e `/i/d/<id>/h/<layer>/pdf/` risponde `500` per tutti i libri provati. Non esiste un nuovo endpoint PDF utilizzabile.
- La via ancora funzionante è quella dei **capitoli**: `https://ms-mms.hubscuola.it/public/<libro>/<capitolo>.zip?tokenId=<token>&app=v2`, che contiene i PDF delle singole pagine. Il downloader è stato riscritto su questa via.
- Corretto il downloader "legacy" che non passava la piattaforma a `getbookinfo` e non gestiva l'indice annidato (prima ricostruiva 0 pagine).
- TOC ora ricorsivo, con deduplica delle voci duplicate (es. capitolo e sottocapitolo con lo stesso nome).
- Pagine lette nell'ordine di `pagesId`, mappate al capitolo corretto; pagine mancanti dallo zip gestite senza crash.
- Page label troncate al numero reale di pagine.
- Corretto `getbooktitle` (usava una variabile del loop esterno), cover assente dalla libreria, errori HTTP/JSON ora messaggi chiari (`HBSError`) invece di traceback.
- Nuove opzioni `[hbs] Downloader = chapters|documentengine` e `ClientVersion`; il downloader "documentengine" fa fallback automatico a `chapters` se fallisce. Retrocompatibilità con la vecchia `UseLegacy`.

### 1b. Nuovo servizio Sanoma My Place (`services/plc.py`)

Aggiunto il supporto a `https://place.sanoma.it` (My Place, ex Pearson/Sanoma). Il flusso è stato ricostruito con login reale:

- **Login**: il sito rimanda ad Auth0 (`login.sanoma.it`), form in due passaggi email → password. Il login è fatto in un Chromium headless via playwright e il token salvato è il solo cookie `MY_PLACE_SESSION` (JSON), non la password e nessun altro cookie (quelli di analytics contengono l'email).
- **Libreria**: la pagina `/prodotti_digitali` contiene già tutti i prodotti e le risorse serializzate; vengono estratte le risorse `LIBROMEDIA` non reflowable (`My Digital Book`), mentre i "Libro liquido" sono saltati perché usano un altro viewer.
- **Apertura libro**: la pagina `libromedia/<id>` fa un 302 a `ebook.sanoma.it/open-book?ktoken=...`; il viewer chiama `display-books`, che restituisce il vero `gedi` del prodotto e i cookie CloudFront firmati. Questi vengono letti dal browser (playwright) una volta per libro.
- **Contenuti**: `master.json` + i file `assets/book/pages/<n>/<n>.svg` con le immagini in `pages/<n>/img/*`; le immagini vengono incorporate come data URI e ogni SVG è convertito in una pagina PDF con PyMuPDF. Download in parallelo (`Workers`, default 6) e inserimento ordinato.
- **TOC**: costruito dai capitoli presenti in `master.json` (unità di primo livello + capitoli), con numeri di pagina reali.
- Nuove opzioni `[plc] Workers` e `PageLabels`; voce aggiunta a `utils.services` e al README.
- Attenzione: il token è una sessione, quindi scade; in quel caso il CLI richiede di nuovo la password. Le credenziali non sono mai scritte nel repo.

### 2. Bug generali

- PyMuPDF 2.0: `fitz.utils.get_pdf_now()` non esiste più (crash dopo il download) → `pymupdf.get_pdf_now()`; `import pymupdf as fitz` in tutti i servizi (via il `FutureWarning`).
- `utils.py`: l'`author` configurato non finiva nei metadati (era scritto `'none'`); `EzSave` ora ha la priorità dichiarata dalla documentazione.
- TinyDB: `(Query()... ) and (Query()...)` valutava solo la seconda query → `&`. Ora libri dello stesso servizio non si sovrascrivono più.
- Cover: un errore di download non blocca più la libreria; file chiuso correttamente.
- Regex con escape non valide (prs, sbk, znc, cmb) rese raw: niente `SyntaxWarning`.
- `main.py`: banner raw (niente warning), controllo versione Python corretto (`< (3,10)`), `center()` senza crash se non c'è un terminale.

### 3. UI/UX della CLI (`main.py`)

- Menu principale in tabella con descrizioni, default `d`, opzioni non più tutte stampate nel prompt.
- Login automatico se c'è un solo utente e `AskPassword = no`; messaggio "Logged in as ...".
- Tabella servizi e tabella libri più leggibili; indicazione della cartella di output.
- Selezione libri con `0`, `0,3`, `2-5`, `all`/`a`; input vuoto annulla; selezione non valida richiesta di nuovo senza uscire.
- Progress bar con descrizione, percentuale, tempo trascorso; riepilogo finale con download riusciti/falliti (un libro fallito non interrompe gli altri).
- Gestione token: nomi servizi leggibili, conferma prima di cancellare, messaggio se non ci sono token.
- Registrazione: impedisce username duplicati; se non esistono utenti, la creazione viene proposta al login.
- Vista libri scaricati con messaggio dedicato se vuota.

### 4b. Avvio, servizi esposti e GUI

- `dependencies.py`: all'avvio controlla i package Python (`pymupdf`, `rich`, `requests`, `pycryptodome`, `u-msgpack-python`, `tinydb`, `playwright`) e il Chromium di playwright; se manca qualcosa chiede se installarlo (`pip install -r requirements.txt`, `playwright install chromium`). Usato da `main.py` e `gui.py` prima degli altri import, così un ambiente incompleto non produce traceback.
- Servizi esposti ridotti a quelli testati: **bSmart (`bsm`)**, **Mondadori HUB Scuola (`hbs`)**, **Sanoma My Place (`plc`)**. I moduli degli altri servizi restano nel repo ma non compaiono più nel CLI/GUI; i one-shot sono disabilitati e la voce è nascosta dal menu. Sezioni di configurazione inutili rimosse da `config-default.ini`.
- `gui.py`: interfaccia Tkinter (stdlib) con scelta servizio, login email/password, riuso del token salvato, tabella libri multi-selezione, download in thread con barra di progresso, log attività, "Scarica tutti" e "Apri cartella".
- `README.md` riscritto: "Made by vincyxiroff", solo i servizi testati, installazione automatica, sezione GUI, note per servizio.

### 4c. Versione server (`server/`)

Server web autonomo, senza framework aggiuntivi (solo stdlib: `ThreadingHTTPServer` + `sqlite3`):

- **Dati sul server**: utenti (PBKDF2-SHA256, 200k iterazioni, salt), sessioni e login delle piattaforme stanno in `server/data/server.db`. Il browser riceve solo un cookie `sbg_session` (HttpOnly, SameSite=Lax, 7 giorni); nessuna password o token di piattaforma resta nel browser né sul PC dell'utente.
- **API**: `POST /api/register`, `/api/login`, `/api/logout`; `GET /api/me`, `/api/services`, `/api/tokens`, `/api/library?service=`, `/api/books`, `/api/file/<id>`, `/api/downloads/<job>`; `POST /api/tokens` (login alla piattaforma), `POST /api/downloads`; `DELETE /api/tokens/<service>`.
- **Download**: job in thread con avanzamento per libro (percentuale + messaggio), più libri in coda, salvataggio in `files/<servizio>/`, riga in tabella `books` e PDF scaricabile con nome leggibile. I job in corso vivono in memoria (persistono i PDF e lo storico, non il job).
- **UI** (`server/static/`): login/registrazione, scelta servizio, stato login, form credenziali piattaforma, tabella libri con checkbox, "Scarica selezionati"/"Scarica tutti", barre di progresso live e sezione "I miei download".
- **Avvio**: default `84.8.252.233:8749` (`--host`, `--port`, o `SBG_HOST`/`SBG_PORT`); porta 8749 verificata libera su questa macchina. Se l'IP non è locale il bind fallisce con un messaggio che suggerisce `--host 0.0.0.0`.
- **Sicurezza minima**: isolamento per utente (libri, token, job), niente path traversal su `/static/`, body limitato a 1 MB, messaggi di errore senza stack trace. Il server è pensato per HTTP in chiaro (l'utente non vuole HTTPS): resta disponibile `SBG_SECURE=1` per il flag `Secure` sul cookie se un giorno lo mette dietro TLS, ma non è più documentato nel README.
- **`install.sh`**: installer guidato per Debian/Ubuntu. Chiede cartella (default `/opt/scuolagrab`), indirizzo (default `0.0.0.0`) e porta (default `8749`), installa i pacchetti di sistema, crea l'utente `scuolagrab`, copia il progetto, crea il venv, installa requirements + Chromium (`install-deps` come root), scrive e avvia l'unit systemd, apre la porta in ufw se attivo. Opzioni `--dry-run`, `--no-service`, `--help`; validazione di porta e cartella (assoluta, fuori dal source tree) e idempotenza su reinstallazione. Verificato con `bash -n` e `--dry-run` (con stub di `apt-get` su una macchina non Debian): exit 0, piano corretto, nessuna modifica al sistema.

### 4d. Dettagli server

- `GET /api/me` risponde `200 {"username": null}` quando non c'è sessione, così la pagina non riempie la console del browser con un 401 all'avvio.
- Il controllo dipendenze del server non fa domande: se manca qualcosa stampa i due comandi `pip install`/`playwright install` ed esce (un servizio non deve restare in attesa di input).

### 4e. App desktop pacchettizzate (`packaging/`)

- **`paths.py`**: quando il programma gira dal sorgente non cambia niente (cwd = cartella del progetto). Nei bundle PyInstaller (`sys.frozen`) config, `db.json`, `files/` e cache dei browser vanno nella cartella dati utente: `~/.local/share/scuolagrab` (Linux), `%APPDATA%\\scuolagrab` (Windows), `~/Library/Application Support/scuolagrab` (macOS). Imposta anche `PLAYWRIGHT_BROWSERS_PATH` alla cartella `browsers/` inclusa nel bundle. Usato da `config.py`, `utils.py` e `gui.py` (prima di importare le dipendenze).
- **`dependencies.py`**: in modalità frozen non tenta `pip install` (build incompleta = errore chiaro) e installa Chromium con il driver playwright incluso (`playwright.__main__`), non con un sottoprocesso `python -m`.
- **`gui.py`**: entry point dei bundle, con `--selftest` che costruisce la finestra, stampa titolo e numero servizi ed esce con 0 (usato per verificare l'app compilata).
- **`packaging/scuolagrab.spec`**: onefile solo su Windows; onedir su Linux/macOS (BUNDLE `.app` su macOS); `collect_all("playwright")` per il driver node, hiddenimports `services.bsm/hbs/plc` (import dinamici), esclusi pandas/numpy/botocore/openpyxl/ecc. che entravano dall'analisi ma non servono.
- **`packaging/build.py`**: scarica Chromium in `packaging/build/browsers` e lo passa allo spec (`SCUOLAGRAB_BROWSERS`), lancia PyInstaller e produce: AppImage su Linux (AppDir + AppRun + .desktop + icona generata con PyMuPDF, `appimagetool` scaricato e usato con `APPIMAGE_EXTRACT_AND_RUN=1`), ZIP con `.exe` su Windows, ZIP con `.app` su macOS (`ditto`). `--no-browsers` per build leggere.
- **`.github/workflows/build.yml`**: tre job su push a `master`/`main` (o `workflow_dispatch`): `version` calcola e pusha il tag (patch bump dell'ultimo `v*`, `v1.0.0` se non ce ne sono; input `version` per forzarne uno; rifiuta formati non `vX.Y.Z` e tag già esistenti), `build` (matrix Ubuntu 22.04 / Windows / macOS 14 arm64 / macOS 13 x64, checkout del tag) e `release` (scarica gli artifact, crea **una** release con `generate_release_notes: true` e allega i file). `[skip ci]` nel commit salta tutto. Nomi file distinti per arch: `scuolagrab-macos-arm64.zip`, `scuolagrab-macos-x64.zip`, `scuolagrab-windows-x64.zip`, `scuolagrab-x86_64.AppImage`. Verificata la logica bash di bump con un repo git temporaneo (no tag → v1.0.0; v1.4.2 → v1.4.3; `v2.0.0` custom; input invalido e tag esistente → exit 1); i runner macOS non sono testabili da qui.
- **macOS senza Chromium nel bundle**: PyInstaller fallisce il codesign dell'`.app` annidata di Chrome (`bundle format unrecognized`). Quindi `build.py` su darwin non include i browser (solo con `--browsers`), e `paths.browsersdir()` in frozen usa `datadir()/browsers` (scrivibile) quando il bundle non ne ha: l'app li scarica al primo avvio con il proprio driver Playwright. Su Linux/Windows restano inclusi.
- **Estensioni per il bundle**: `gui.py` accetta `--selftest` (costruisce la finestra e stampa titolo/servizi) e `--checkbrowser` (lancia Chromium dal driver incluso) e installa un `sys.excepthook` che scrive `error.log` nella cartella dati e mostra un messagebox (sull'exe non c'è terminale). `dependencies.ensure(interactive=False)` non chiede né scarica nulla nei self test; `rich` è controllato solo fuori dal bundle (la GUI non lo usa).

### 4f. Account dell'app e vault cifrato

Requisito: all'apertura l'app deve chiedere login/registrazione sul sito, e gli account delle piattaforme salvati sul server devono essere cifrati e decifrati dall'app.

- **`vault.py`** (nuovo): chiave = PBKDF2-HMAC-SHA256(password, salt dell'utente, 300 000 iterazioni, 32 byte); payload = `{"username", "password"}` in JSON cifrato con **AES-256-GCM** (nonce 12 byte, tag 16), AAD `scuolagrab-vault|<userid>|<service>` così un blob non si può spostare su un altro utente o servizio. Blob scambiato col server = `{nonce, data}` in base64. `VaultError` per salt non valido, blob rovinato, password sbagliata.
- **`apiclient.py`** (nuovo): client `requests` con timeout 20 s; `ServerError` (messaggio dal server o "server not reachable"), `SessionExpired` su 401; metodi `register`, `login`, `logout`, `saveaccount`, `deleteaccount`.
- **Server, schema**: `users.vault_salt` (migrazione `ALTER TABLE` per i DB esistenti) creata al primo accesso dall'app con `db.ensurevaultsalt`; nuova tabella `vault (user_id, service, nonce, data, updated)` con PK `(user_id, service)`.
- **Server, API app** (stessa tabella `users`, quindi lo stesso account vale per sito e app): `POST /api/app/register`, `POST /api/app/login` (risposta: `username`, `userid`, `salt`, `token`, `vault`), `POST /api/app/logout`, `GET /api/app/vault`, `PUT /api/app/vault/<service>` (max 64 char di nonce, 16 KB di dati), `DELETE /api/app/vault/<service>`. Autenticazione bearer: `session()` accetta `Authorization: Bearer <token>` oltre al cookie. Il server non riceve mai la chiave: salva solo `nonce` + ciphertext.
- **GUI**: `LoginPage` (frame nella finestra principale, non una seconda finestra) mostrata all'avvio: campi server (default `[app] Server` o `SBG_SERVER`), username (ricordato in `db.json` tabella `settings`), password, "Ripeti password" solo in registrazione; `Accedi` / `Crea un account`; errori del server mostrati nella pagina (password errata non chiude nulla); dopo l'accesso la stessa finestra passa al layout completo (1000x720), `Esci` torna alla pagina di accesso senza chiudere il programma.
- **GUI, dati**: al login la chiave viene derivata in memoria e i blob ricevuti vengono decifrati in un thread; `self.accounts` contiene gli account in chiaro solo in RAM. `refreshaccount()` precompila email/password del servizio selezionato e mostra "Account salvato sul server ✓". Dopo un login di piattaforma riuscito `saveaccount()` cifra e invia al server (token locale in `db.json` invariato) e un errore di rete non blocca il download.
- **GUI, account locale**: l'id usato per i token locali ora è l'utente del server (`utils.new_login(username, "", False)`), non più l'utente fittizio "locale"; `--selftest` usa `App(auth=False)` e resta senza server.
- **Bug trovati e corretti durante i test**: `poll()` si rischedulava dopo la distruzione della finestra ("invalid command name ...poll") → id salvato e `after_cancel` nella distruzione; "Apri cartella" non faceva nulla quando `xdg-open` usciva con errore → `subprocess.run` controllato e messagebox col percorso; percorso relativo `Path("files")` → `paths.datadir()/files/<servizio>` assoluto.
- **Bug "l'AppImage non si apre" (KDE/Wayland)**: la finestra di accesso era un `Toplevel` con `transient()` di una root `withdraw`; kwin non mappa mai un transient di una finestra non mappata, quindi il processo restava vivo senza mostrare nulla (verificato con `XQueryTree`/`XGetWindowAttributes` su `:0`: le finestre esistevano ma con `map_state = IsUnmapped`, 1x1 e 469x274). I test precedenti "passavano" perché pilotavano i widget per codice senza controllare che fossero visibili. Ora l'accesso è una pagina dentro la finestra principale (`LoginPage`), che è sempre mappata: nessuna seconda finestra, nessun grab. Test di regressione che verifica `map_state` reale della finestra.
- **GUI, posizione dei download**: entry readonly "Salvataggio in" con il percorso assoluto della cartella del servizio, aggiornata al cambio servizio; log con percorso assoluto per ogni PDF salvato; "Apri cartella" spostato accanto al percorso.

### 4. Documentazione

- `README.md`: bilingue (inglese + italiano) con indice, keyword, setup client e server, `install.sh`, configurazione, troubleshooting; rimosse le sezioni nginx/HTTPS su richiesta. Aggiunte le sezioni account/cifratura, API dell'app e **log del server** (`journalctl -u scuolagrab`, persistenza del journal, `--vacuum-size`). 67 heading, 58 link interni, 0 rotti, code fence bilanciate.
- `config-default.ini`: nuove opzioni `[hbs]` e `[plc]` con commenti.
- `config.ini` locale rigenerato dal nuovo default.

## Verifiche fatte

- `python3 -W error::SyntaxWarning -m compileall` su tutto il progetto: OK.
- Import di tutti i 15 servizi + 2 oneshot: OK.
- Download reale dal CLI del libro `5891045` ("Noi c'eravamo 1"): **866 pagine, 128 voci di indice**, ~157 MB, ~26 s, exit code 0, nessun warning/traceback.
- Download reale del secondo libro `7915794` ("Emozioni Visive - Poster"): 25 pagine, DB con due righe distinte.
- Testato il percorso `Downloader = documentengine`: auth `200`, PDF `403`, fallback automatico ai capitoli, stesso risultato.
- Testati annullamento selezione, vista libri e parsing delle selezioni (`0,3`, `2-5`, `all`, input invalidi).
- `parsebooks` verificato con casi limite.
- Login reale Sanoma My Place con Auth0: OK (salvato solo `MY_PLACE_SESSION`, `checktoken` true); verificato che quel solo cookie basti per libreria, `display-books` e `master.json`.
- Libreria Sanoma: 3 libri digitali trovati (concetti base, occasioni della letteratura, abitare la storia).
- Download Sanoma `I concetti base della letteratura 2`: **162 pagine, 71 voci di indice, 16 MB**, ~79 s, exit code 0.
- Download Sanoma dal CLI con token salvato (`d` → `plc` → libro): riuscito, riepilogo ✓.
- bSmart: `checktoken` ok, libreria con 19 libri; download di `Emozioni Visive - Poster` (9389): **25 pagine, 24 voci di indice, 11 MB**, ~7 s; download di `Curiosity A` (10057): **299 pagine, 109 voci di indice, 50 MB**, ~75 s, testo selezionabile.
- GUI: avvio e caricamento libreria Sanoma (3 libri) ok; cambio servizio bSmart (19 libri) e download dalla GUI di `9389` riuscito ("1 scaricati, 0 falliti").
- `dependencies.ensure()`: nessun package mancante, Chromium presente → ok senza prompt.
- Libro Sanoma grande (898 pagine, "Le occasioni della letteratura 2"): **898 pagine, 382 voci di indice, 160,2 MB, 699 s**; pagine campione (1, 101, 451, 898) con immagini e vettori, formato 844x1125, testo non selezionabile (atteso: SVG convertiti).
- Bug trovato con quel download: con `EzSave = no` il salvataggio falliva (`FzErrorArgument: Linearisation is no longer supported`) perché PyMuPDF 2.0 ha rimosso la linearizzazione → rimosso `linear=True` e l'opzione `Linearize` (era in `config-default.ini`). Verificato un salvataggio con `garbage=2, clean=True` sulla stessa logica.
- Metadati: `Author` vuoto in config ora produce davvero un autore vuoto (prima veniva scritto `none`).
- Token Sanoma salvato ora contiene **solo** `MY_PLACE_SESSION` (verificato che basti per libreria, `display-books` e `master.json`); rifatto il login per sostituire il vecchio cookie jar che conteneva l'email nei cookie di analytics.
- Login Sanoma reso più robusto: timeout Auth0 più ampi e un secondo tentativo, perché un caricamento lento veniva scambiato per password errata (errore visto nella prima prova via server). `checktoken` ora restituisce `False` sui timeout di rete invece di lanciare un traceback.
- **Build desktop (Linux, Python 3.14, PyInstaller 6.22)**: `python3 packaging/build.py --no-browsers` → onedir + **AppImage 120 MB** in `packaging/dist/`; `--selftest` exit 0 su entrambi; cartella dati creata in `~/.local/share/scuolagrab` con `config.ini` + `db.json`; `--checkbrowser` con i browser del sistema linkati nel bundle → `chromium ok: 156.0.8078.4` (driver node incluso funzionante). Non testati Windows/macOS (servono i runner CI) né la build con Chromium incluso (~400 MB in più).
- **Server**: avvio con dipendenze presenti; `GET /` e statici 200, path traversal 404; registrazione/login/logout e cookie HttpOnly verificati; libreria Sanoma (3 libri) e bSmart (19 libri) dal server; download Sanoma (162 pagine, 16 MB) e bSmart (25 pagine) via API con progress; `/api/books` e `/api/file/<id>` (Content-Type/Content-Length/nome file corretti, PDF aperto con 162 pagine/71 voci); isolamento tra utenti (file e job di un altro utente 404); token eliminabile; sessione valida dopo riavvio del server (dati in SQLite); UI web provata in Chromium headless (login, tre servizi, stati vuoti e "login richiesto", nessun errore in console).

## Cose da fare / limiti noti

- **Endpoint PDF singolo Mondadori**: morto lato server. Se torna disponibile, impostare `Downloader = documentengine` in `[hbs]`; il fallback è automatico.
- **Altri servizi non testati** con account reali: verificati solo sintassi/import (servono token/credenziali).
- **Sanoma My Place**: supportati solo i libri "My Digital Book" (fixed layout); i "Libro liquido" (reflowable) sono saltati. Il login richiede playwright + Chromium e il testo nel PDF non è selezionabile (le pagine sono SVG convertiti). Il token è una sessione e scade, quindi va rifatto il login.
- **PageLabels HBS** ancora disabilitate di default per il vecchio bug PyMuPDF che corrompeva i PDF: da riprovare con PyMuPDF 2.0 prima di attivarle.
- **Cover HBS**: il percorso è stato sistemato ma non provato (opzione disattivata di default).
- **Test automatici assenti**: il progetto non ha test; i controlli sono manuali (script one-off usati oggi).
- **requirements.txt non pinnato**: PyMuPDF 2.0 ha cambiato API, un range di versione eviterebbe sorprese future.
- TODO storici del README ancora aperti: utente anonimo, "perfect token checks", warning non critici per TOC/page label.
- I token sono salvati in chiaro in `db.json` (gitignored) e in `server/data/server.db` (gitignored): non committarli e proteggere i file.
- **Vault cifrato**: il server vede la password al login (come ogni form) ma non può decifrare gli account salvati; se l'utente dimentica la password i login salvati sono persi (non c'è cambio password né reset). Non c'è ancora un pulsante per rimuovere un account dalla GUI, anche se l'API `DELETE /api/app/vault/<service>` esiste.
- **Limiti del server**: HTTP in chiaro (serve un reverse proxy TLS), niente CSRF token (mitigato da `SameSite=Lax` e API JSON), job in memoria (si perdono al riavvio), nessun limite di download simultanei per utente, un solo login per servizio e per utente.

## Comandi utili

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
python3 main.py                      # CLI
python3 gui.py                       # GUI Tkinter
python3 server/app.py                # server web su 84.8.252.233:8749
python3 server/app.py --host 0.0.0.0 --port 8749
SBG_SECURE=1 python3 server/app.py   # cookie Secure, dietro reverse proxy HTTPS
```

Nel menu: `d` → servizio → indice/i libro → download. Output in `files/<servizio>/<id>.pdf`. La versione server salva utenti, sessioni e login in `server/data/server.db` e i PDF nella stessa cartella `files/`.
