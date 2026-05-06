# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Documentation
- **Riscritta documentazione completa** (`README.md`, `docs/*.md`, `docs/*.en.md`, mkdocs nav) per riflettere lo stato post-migrazione `api-migration`: bridge HTTP a Unit3DWebUp, `.env` condiviso (`ENVPATH`/`U3DP_ENV_PATH`), endpoint `/api/webup/*` e `/api/version/*`, auto-update SSE per app + Unit3DWebUp, install via PyPI `pip install Unit3DwebUp` (niente più `requirements.txt`), unit systemd separate `unit3dprep-web.service` + `unit3dwebup.service`, flag `U3DP_DRY_RUN_TRACKER` per dev/WSL.
- **Nuova pagina `docs/integrazione-webup.md`** (+ mirror `.en.md`): architettura del bridge (singleton client, scan-lock asyncio, WebSocket demux per `job_id`), flusso completo `setenv → scan → maketorrent → upload → seed`, mappatura short ↔ canonical `WEBUP_KEY_MAP`, skip rules per valori vuoti, IMAGE_HOST_ORDER → priorità numeriche, health check, dry-run mode, limitazioni note (Redis hardcoded, ffmpeg richiesto, `DOCKER` truthy check).
- **Consolidato `itatorrents-nomenclatura.md` in `docs/nomenclatura.md`** (+ `.en.md`): file alla radice rimosso, `MANIFEST.in` aggiornato, riferimento aggiornato in `docs/nomenclatura.md`.
- **Troubleshooting espanso** con sezioni dedicate Unit3DWebUp (500 ovunque, version stantia, `/scan` 0 items, JSON liste, `DOCKER` truthy check), bridge unit3dprep ↔ webup, auto-update edge cases (cache flush, `can_update_app:false`, `203/EXEC`).
- **Deploy guides** aggiornate con due unit systemd, `Requires=` ordering, avvertenze `DOCKER` env var, configurazione iniziale via Settings UI con sync live a webup, checklist post-deploy estesa.
- **`uso-cli.md` / `uso-web.md`** allineati al nuovo backend HTTP: niente più subprocess `unit3dup`, sezione Versione con due card (App + Unit3DWebUp), card Health Unit3DWebUp con bottoni "Spingi config" e "Aggiorna", phase weights del wizard (setenv 3% / scan 27% / maketorrent 45% / upload 15% / seed 10%).

### Changed
- **Storage impostazioni unificato in un singolo file `.env`** (compatibile con `Unit3DWebUp` 0.0.20+). Le impostazioni dell'app e quelle del bot vivono ora nello stesso file, eliminando il vecchio `Unit3Dbot.json`. Default: `~/.config/unit3dprep/.env`. Override: `U3DP_ENV_PATH=<file>` o `ENVPATH=<directory>` (la stessa variabile usata da `Unit3DWebUp`, così il valore può essere riutilizzato nel suo systemd/docker-compose). Migration automatica al primo avvio: se esiste `~/Unit3Dup_config/Unit3Dbot.json` (o quanto puntato da `$UNIT3DUP_CONFIG`) viene letto, riscritto come `.env` con la nomenclatura canonica `TRACKER__*` / `TORRENT__*` / `PREFS__*`, e rinominato in `Unit3Dbot.json.migrated-bak` (mai cancellato — l'utente decide quando eliminarlo). Nessun cambio per l'utente che usa la UI: la API `/api/settings` mantiene lo stesso shape (chiavi corte storiche), e `webup_envpath_dir` viene esposto nel payload per ricordare quale path passare a webup.
- **Migrazione bot: da `unit3dup` CLI a `Unit3DWebUp` FastAPI**. L'app ora invoca il nuovo bot via HTTP API anziché spawnare il CLI come subprocess. Il pre-flight (audio check + nomenclatura ItaTorrents + hardlink in `~/seedings/`) resta invariato; cambia solo l'ultimo step (upload) che ora chiama `/setenv`+`/scan`+`/maketorrent`+`/upload`+`/seed` su `Unit3DWebUp` e ascolta i progressi via WebSocket. Niente più PTY streaming né parsing regex degli stdout.
- **Configurazione condivisa**: salvando da Settings UI, l'app sincronizza automaticamente le chiavi rilevanti di `Unit3Dbot.json` (tracker, qBittorrent, image hosts, preferences) verso il `.env` di `Unit3DWebUp` via `POST /setenv`. Single source of truth: la nostra UI.
- **Settings UI**: nuova card "Unit3DWebUp" con stato online/offline, versione, latenza, indicatore WebSocket, pulsanti "Aggiorna" e "Spingi config".
- **Versione**: la sezione che prima mostrava `unit3dup` (PyPI) ora mostra `Unit3DWebUp` (GitHub). Update flow via `git pull` + `pip install --upgrade Unit3DwebUp` (PyPI) + `systemctl --user restart unit3dwebup.service`.

### Added
- Nuovi endpoint `/api/webup/health`, `/api/webup/sync`, `/api/webup/setting`, `/api/webup/filter` per integrarsi con il nuovo bot.
- Unit systemd `deploy/systemd/unit3dwebup.service` + README di installazione.
- Nuovo log source `webup` (rimpiazza `unit3dup`) nel filtro Logs.

### Removed
- Subprocess invocation di `unit3dup` CLI (`stream_unit3dup`, `run_unit3dup`).
- Endpoint stdin del wizard/quickupload e UI per i prompt interattivi (TMDB ID, duplicate C/S/Q): non più necessari, il nuovo bot risolve TMDB/TVDB internamente al `/scan` e accetta override via `/settmdbid`.
- Endpoint `/api/version/update/unit3dup/stream` (rimpiazzato da `/api/version/update/webup/stream`).

### Changed
- **Layout hardlink: sandbox per-upload sotto `<seedings>/.unit3dprep/<jobid>/`**. Ogni film o pack di serie ora vive in una sotto-cartella dedicata (sha256 8-char del nome finale, deterministico). Il bridge punta `SCAN_PATH` alla sandbox specifica → webup processa solo l'item target invece di scansionare tutta `~/seedings`. Risolve `[Errno 11] Resource temporarily unavailable` e `cannot reshape array of size 0 into shape (...)` su seedings affollati. Hardlink condividono inode con il file originale → Media Library inode-fallback continua a funzionare. **Breaking**: nuovi upload finiscono in `<seedings>/.unit3dprep/<jobid>/...` invece che `<seedings>/<name>.mkv`. File legacy in seedings root vanno migrati a mano (o re-uploadati da UI per generare la sandbox).

### Fixed
- **Auto-update Unit3DWebUp: bottone disabilitato anche con installazione PyPI canonica**. `_webup_can_update()` richiedeva `<WEBUP_REPO_PATH>/.git`, residuo di quando webup veniva clonato. Webup `0.0.x` viene distribuito da PyPI: il git clone non serve. Ora il check verifica solo `<webup_python>` esistente E systemd unit accessibile. `update_webup()` salta i `git fetch/pull` se `WEBUP_REPO_PATH/.git` non esiste e procede direttamente con `pip install --upgrade Unit3DwebUp`.
- **Versione Unit3DWebUp non rilevata se installato nello stesso venv di unit3dprep**. `_webup_python()` aveva default `<WEBUP_REPO_PATH>/.venv/bin/python`, path inesistente nell'install PyPI canonico (entrambi i pacchetti nello stesso venv). Ora se `WEBUP_VENV_BIN` non è settata, prova prima il path legacy, poi cade su `sys.executable` (stesso interprete di unit3dprep). La card "Settings → Versione → Unit3DWebUp" mostra correttamente la versione corrente quando i due pacchetti condividono il venv.
- **Deploy templates** (`deploy/systemd/unit3dwebup.service`, docs deploy-vps/deploy-ultracc): `ExecStart` ora punta al venv condiviso `~/.venvs/unit3dprep/bin/uvicorn`. Aggiunto `Environment=WEBUP_VENV_BIN=...` esplicito nel file unit `unit3dprep-web.service` per forzare il path corretto a runtime.
- **Update Unit3DWebUp: `requirements.txt` non esiste più**. Il branch `0.0.x` di `Unit3DWebUp` non distribuisce più `requirements.txt`; l'install canonico è via PyPI (`pip install Unit3DwebUp`). Il pulsante "Installa aggiornamento" falliva con `Could not open requirements file`. Ora l'update esegue `pip install --upgrade Unit3DwebUp` invece di `pip install -r requirements.txt`.
- **Settings → Versione: card Unit3DWebUp mostrava "Corrente: -" anche con webup installato**. Il fallback leggeva `UNIT3DWEBUP__VERSION` da `/setting` o dal `.env`, ma webup 0.0.x non espone più quel campo. Aggiunta lettura della versione installata via `importlib.metadata.version('Unit3DwebUp')` eseguita nel Python del venv di webup. Ora la card mostra correttamente la versione corrente e nasconde il bottone "Installa aggiornamento" quando già aggiornato.
- **Bridge config: chiavi vuote rompevano webup**. La sync verso `Unit3DWebUp` `.env` pushava valori vuoti per chiavi tipo `TORRENT__SHARED_QBIT_PATH=`, `PREFS__RELEASER_SIGN=`, ecc. Il validator Pydantic di webup (`empty_to_none`) le convertiva in `None`, faceva fallire la validazione `str` e `get_settings()` chiamava `SystemExit(1)` → tutte le richieste successive (incluso `setenv` chiamato dal wizard upload) ritornavano 500. Ora `_to_webup_env_payload` salta valori vuoti, `None`, `no_key`/`no_pass`/`no_path`/`no_comment`: webup mantiene i suoi default.
- **Wizard upload bloccato sul maketorrent**. L'orchestrator aspettava un `posterLogMessage` testuale "torrent created/exists" che webup non manda mai (manda invece `[New torrent] FILE - 100.0`). Refactor: HTTP 200 di `/maketorrent` = completion; drena log buffered per ~1.5s e prosegue. Stesso pattern per `/upload` con detection di terminal success/failure dai log post-call.
- **Wizard upload: `no Media for ... (0 items)`**. Per le serie passavamo `SCAN_PATH = <folder serie>` → webup vedeva singoli episodi non il pack. Fix: per `kind=series`, `SCAN_PATH=parent(seeding_path)`, match_path = la folder. Webup riconosce le subfolders come Media-pack.
- **Config bridge: chiavi mancanti**. Aggiunte al `WEBUP_KEY_MAP`: `MULTI_TRACKER → TRACKER__MULTI_TRACKER`, `IMGFI_KEY → TRACKER__IMGFI_KEY`, `SHARED_TRASM_PATH`, `SHARED_RTORR_PATH`, `TAG_ORDER_MOVIE → PREFS__TAG_POSITION_MOVIE`, `TAG_ORDER_SERIE → PREFS__TAG_POSITION_SERIE`. Liste serializzate come CSV (compatibile con i validator `parse_multi_tracker` e `parse_tag_position` di webup).
- **Image host order propagation**. La `IMAGE_HOST_ORDER` (lista nostra) ora viene proiettata sulle priorità numeriche di webup (`PREFS__<HOST>_PRIORITY`) — gli host non in lista vanno a priorità 99, evitando che webup tenti host senza chiave.

---

## [0.6.4] - 2026-04-25

### Added
- **Impostazioni — sezione "Versione"**: mostra la versione corrente e l'ultima disponibile di app e unit3dup in due card separate. Ogni card ha un pulsante "Controlla aggiornamenti" per forzare il check senza aspettare i 10 minuti del polling automatico, un pulsante "Installa aggiornamento" (visibile solo se disponibile) e un accordion **Changelog** che mostra le release notes da GitHub (app) o un link a PyPI (unit3dup). La card unit3dup appare anche quando il pacchetto non è installato localmente, mostrando l'ultima versione disponibile e un pulsante di installazione.

---

## [0.6.3] - 2026-04-24

### Changed
- **Media Library — Pannello dettaglio serie: stagioni come accordion + episodi in lista**. Le stagioni ora sono collassabili (prima stagione non caricata aperta di default) e gli episodi, invece che piccoli badge troncati, appaiono in una lista verticale con il numero episodio (`E01`) prima del titolo, pulito da prefisso serie ed etichette di release (`1080p`, codec, gruppo, ecc.). Il nome completo resta leggibile; hover+click sulla riga avvia comunque il wizard upload, il chip "Segna come caricato" funziona senza chiudere la sezione.

### Fixed
- **Media Library: film non nascosto dopo upload con skip duplicato**. Se il record in upload history aveva `source_path` vuoto (per upsert su record stantio), il film restava visibile anche con "nascondi caricati" attivo. Doppia correzione: (1) l'upsert in DB ora aggiorna `source_path` (e altri campi arricchiti) se il nuovo valore è non vuoto; (2) la Media Library usa un fallback inode-based — se un video file dell'item condivide l'inode con un file in seedings nel DB, l'item viene marcato come caricato anche quando `source_path` è vuoto.

---

## [0.6.2] - 2026-04-24

### Fixed
- **Auto-update: versione e bottone "aggiorna" stantii dopo il reload**. Dopo un update riuscito in pip mode, la TopBar continuava a mostrare la versione precedente e il bottone restava visibile finché l'utente non cliccava di nuovo. Causa: cache in-memory di `/api/version/info` (TTL 10 min) non invalidata dopo `_update_app_from_pip`/`_update_app_from_git`, combinata con il race tra restart systemd e reload frontend. Ora la cache viene azzerata a fine install (entrambi i path) e il frontend forza un `POST /api/version/refresh` al primo fetch dopo un reload post-update (quando presente `unit3dprep.pendingChangelog`).

### Changed
- Documentazione (`uso-web.md` IT+EN): aggiunte sezioni per UI bilingue IT/EN (v0.6.0) e selezione multipla / bulk mark-uploaded in Media Library (v0.6.1). README aggiornato con menzione lingua. Descrizione GitHub aggiornata per riflettere supporto multi-tracker Unit3D.

---

## [0.6.1] - 2026-04-24

### Added
- **Media Library — Selezione multipla per marcare film come caricati manualmente**: il pulsante "Selezione multipla" appare nella toolbar della Libreria quando almeno un film non ancora caricato è visibile (qualsiasi categoria, incluse quelle miste come `anime` con serie + film). In modalità bulk **solo i file singoli (`kind === 'movie'`) sono selezionabili** — le serie restano visibili ma disabilitate. Action bar con "Seleziona tutti / Deseleziona / Segna come caricati" e feedback `Marcati X/Y`.

---

## [0.6.0] - 2026-04-24

### Added
- **Supporto multilingua UI (IT / EN)**: switcher rapido `IT|EN` nella topbar (sempre visibile) e nuova sezione **Interface** in Impostazioni. La preferenza è persistita in `Unit3Dbot.json` (`U3DP_LANG`) e in `localStorage` (`u3d_lang`), sopravvive a refresh e restart del service.
- **API backend localizzata**: i messaggi d'errore delle route `/api/*` ora rispettano la lingua della richiesta. Il frontend invia l'header `X-U3DP-Lang: it|en` su ogni chiamata; il backend, in assenza di header, ricade sul setting runtime `U3DP_LANG` (default `it`).
- Tutte le viste e i modali ora completamente tradotti: Libreria Media, Coda Torrent, Cronologia Upload, Ricerca, Upload Rapido (UploadModal), Log, Impostazioni (nav sezioni + pulsanti salva), Wizard upload (tutti e 5 gli step), tutte le descrizioni e i toggle delle sezioni Impostazioni.

### Changed
- Default lingua: **italiano** (invariato per gli utenti esistenti). Nuove installazioni partono in IT; lo switch a EN è manuale dalla UI.

---

## [0.5.1] - 2026-04-24

### Added
- **Media Library — Mark as uploaded manually per le serie**: il pulsante, finora presente solo per i film, è ora disponibile a tre livelli per le serie TV — intera serie (detail panel), singola stagione (accanto a "Bulk upload season") e singolo episodio (mini chip `✓` accanto a ogni episodio). Utile per ripulire la libreria da contenuti già caricati fuori dall'app.

### Fixed
- `GET /api/version/info` ora segue i redirect di GitHub: quando un repo viene rinominato, `latest` non è più `null` (polling trasparente verso il nuovo slug).
- Marcare un'intera serie come caricata manualmente ora propaga correttamente lo stato a tutte le stagioni: la serie viene filtrata da "Hide already uploaded" e mostra il badge uploaded, non solo nella Upload History.

---

## [0.5.0] - 2026-04-23

Release di rebranding. Il progetto cambia nome da `itatorrents` a **`unit3dprep`** per riflettere il supporto multi-tracker Unit3D (non più solo ItaTorrents). Pairing esplicito con `unit3dup`. Nessun intervento manuale richiesto per gli utenti esistenti: env vars legacy, dotfile e chiavi di configurazione migrano automaticamente.

### Changed
- **Package Python**: `itatorrents` → `unit3dprep`. Import path, CLI entrypoints (`unit3dprep`, `unit3dprep-web`), directory del pacchetto.
- **Env var prefix**: `ITA_*` → `U3DP_*` (es. `U3DP_MEDIA_ROOT`, `U3DP_SECRET`, `U3DP_PORT`, `U3DP_SYSTEMD_UNIT`, ecc.).
- **Systemd unit**: default `unit3dprep-web.service` (era `itatorrents-web.service`).
- **Dotfile DB/cache**: `.itatorrents_*.json` → `.unit3dprep_*.json`.
- **Repo GitHub**: `davidesidoti/unit3dprep` (redirect automatico dal vecchio nome).
- **Documentazione**: `https://davidesidoti.github.io/unit3dprep/`.
- **Frontend localStorage**: chiavi `itatorrents.*` → `unit3dprep.*` (pendingChangelog + logs filters).

### Added
- **Fallback env vars legacy**: le vecchie `ITA_*` sono ancora lette al primo avvio; helper `_env()` logga un warning "Using legacy env var ITA_X; rename to U3DP_X" e continua a funzionare.
- **Auto-migrate dotfile**: all'avvio, se un `.itatorrents_*.json` esiste e il nuovo `.unit3dprep_*.json` no, viene rinominato automaticamente.
- **Auto-upgrade config JSON**: `Unit3Dbot.json` con chiavi legacy `ITA_*` viene riscritto transparentemente con le nuove chiavi al primo load/save.
- **Cleanup metadata doppio**: il flow di auto-update pulisce sia `itatorrents.egg-info` sia `unit3dprep.egg-info`, sia i `dist-info` orfani di entrambi i nomi, per supportare gli upgrade cross-rename senza residui.

### Deprecated
- **`ITA_*` env vars**: ancora funzionanti come fallback, ma producono warning nei log. Rinomina in `U3DP_*` alla prima occasione — verranno rimosse in una release futura.

### Upgrade notes
Nessuna azione manuale richiesta per gli utenti esistenti: fallback env + auto-rename dotfile coprono il caso comune. Per un cleanup completo su VPS/Ultra.cc:
```
# 1. Aggiorna il pacchetto
pip install --upgrade "git+https://github.com/davidesidoti/unit3dprep.git@v0.5.0"

# 2. (opzionale) Rinomina env vars in ~/.bashrc o nel file unit systemd
#    ITA_*  →  U3DP_*

# 3. (opzionale) Rinomina systemd unit
mv ~/.config/systemd/user/itatorrents-web.service ~/.config/systemd/user/unit3dprep-web.service
systemctl --user daemon-reload
systemctl --user disable --now itatorrents-web.service 2>/dev/null || true
systemctl --user enable --now unit3dprep-web.service
```
Finché non rinomini env + systemd unit, il service continuerà a funzionare con le chiavi legacy (warning nei log ma zero breaking).

---

## [0.4.1] - 2026-04-23

Release di hotfix sul flow di auto-update: il restart del service non avveniva realmente e la versione mostrata nella UI restava indietro. Dopo questa release il pulsante "Update app" e "Update unit3dup" funzionano end-to-end senza intervento manuale.

### Fixed
- **Auto-update unit3dup: pulsante restava visibile dopo l'update**. Il `_cache` di `/api/version/info` (TTL 10min) non veniva invalidato al termine dell'install, quindi la UI continuava a vedere `{newer: true}` fino alla scadenza naturale. Ora il cache viene azzerato sull'evento `done` dell'endpoint SSE `update/unit3dup/stream`.
- **Auto-update: service non veniva realmente riavviato su systemd user services**. Il `systemctl --user restart` spawnato come figlio detached restava nel cgroup del service genitore e veniva ucciso da systemd prima di poter eseguire. Ora il restart viene schedulato via `systemd-run --user --on-active=3s` in uno scope transient fuori dal cgroup del service, garantendo che il restart avvenga davvero. Fallback al metodo precedente se `systemd-run` non è disponibile.
- **Auto-update: versione mostrata in UI non si aggiornava dopo `git pull`**. `importlib.metadata.version()` poteva ritornare valori stantii per via di `itatorrents.egg-info/` nella source dir o `dist-info` orfani nei site-packages. In git mode il backend ora legge la versione direttamente da `pyproject.toml` (fonte autorevole, aggiornata atomicamente da `git pull`).
- **Auto-update git mode**: pre-pulizia di `itatorrents.egg-info`, `itatorrents-*.dist-info` orfani e `__editable__.itatorrents-*.pth` residui prima di `pip install -e .`, più loop di `pip uninstall` finché "not installed". Elimina il problema delle metadata stantie che pip non rimuove completamente.

### Upgrade notes
Il fix al restart risolve il problema andando avanti, ma il codice attualmente in esecuzione sul VPS ha ancora il bug del detached Popen — quindi cliccando "Update app" da v0.4.0 il service non si riavvierà. Bootstrap una tantum:
```
cd <repo>
git pull --ff-only origin main
<python> -m pip install -e .
rm -rf itatorrents.egg-info    # solo se presente
systemctl --user restart itatorrents-web.service
```
Dalla v0.4.1 in poi il pulsante funziona senza restart manuali.

---

## [0.4.0] - 2026-04-23

Nuove funzionalità per la Media Library e per la gestione runtime del service systemd, più un fix al flow di auto-update.

### Added
- Nuova checkbox **"Only with Italian audio"** nella Media Library: filtra i media il cui audio è già stato scansionato ma non contiene una traccia ITA (gli item non ancora scansionati restano visibili). Default configurabile da **Settings › Wizard Defaults** tramite la nuova chiave `W_HIDE_NO_ITALIAN`.
- `ITA_SYSTEMD_UNIT` è ora editabile da **Settings › App Auto-Update** e persiste in `Unit3Dbot.json`. La chiave viene letta runtime (non solo all'import) così il bottone "Update app" rileva subito il cambio di nome della unit senza dover riavviare il service.
- Documentazione aggiornata (`docs/configurazione.md`, `docs/uso-web.md`, `docs/deploy-ultracc.md` + mirror inglesi) con una sezione dedicata all'auto-update in-app, ai pre-requisiti systemd e alla gestione di `ITA_SYSTEMD_UNIT` / `WorkingDirectory` su Ultra.cc.
- README: menzione del sistema di auto-update nella descrizione del progetto.

### Fixed
- **UpdateProgressModal entrava in loop infinito dopo il restart del service**: l'`EventSource` riconnetteva automaticamente quando il service veniva riavviato e il backend rieseguiva l'update da capo. Ora la connessione SSE viene chiusa esplicitamente alla ricezione dell'evento `done` e `onError` non riattiva lo stream se l'update è già concluso.

---

## [0.3.1] - 2026-04-23

Primo rilascio funzionante del sistema di auto-update introdotto in v0.3.0.

### Fixed
- **Update app non funzionava su installazioni pip-from-git**: il flow assumeva un git checkout ma `pip install git+URL@tag` non lascia la cartella `.git`. Aggiunto rilevamento automatico della modalità di installazione (`git` vs `pip`) con flow dedicato per pip: `pip install --upgrade --force-reinstall git+URL@vX`.
- **Check systemd troppo stretto**: `systemctl --user is-enabled` restituisce rc≠0 per unit in stato `linked` (symlink, comune su Ultra.cc) o `static` → pulsante "Update app" erroneamente disabilitato con `systemd unit not available in this environment`. Passato a `systemctl --user cat UNIT` che ritorna 0 iff il file unit esiste, indipendentemente dallo stato di abilitazione.

### Upgrade notes
Se stai aggiornando da v0.3.0, il codice attualmente installato contiene i bug sopra quindi non può aggiornarsi autonomamente. Fai il bootstrap una volta manualmente:
```
~/.venvs/itatorrents/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/itatorrents-seeding.git@v0.3.1"
systemctl --user restart itatorrents.service
```
Dalla v0.3.1 in poi il pulsante "Update app" funziona dall'UI.

---

## [0.3.0] - 2026-04-23

### Added
- Web UI React SPA (Vite + TypeScript) con FastAPI backend, servita via systemd user service su Ultra.cc
- Wizard multi-step: audio check → TMDB lookup → rinomina → hardlink → unit3dup PTY stream
- Quick Upload modal per power users (senza wizard)
- Libreria media con categorie dinamiche da `W_MEDIA_ROOT`
- Queue torrent via qBittorrent client con filtro per nome
- Upload History con stati e exit code
- Logs tab con filtri source/kind persistiti in localStorage; classificazione automatica log unit3dup
- Settings runtime `ITA_*` / `W_*` via env o `Unit3Dbot.json` (no restart necessario)
- Auth con sessione + bcrypt; OpenAPI/Swagger protetto
- Mobile responsive: sidebar drawer, overlay panel dettaglio, layout a 1 colonna
- Runtime-configurable media root e seedings dir
- Documentazione MkDocs su GitHub Pages
- Check compatibilità filesystem per hardlink
- Tracker sidebar con badge Online/Offline/Not set (inclusi tracker non configurati)