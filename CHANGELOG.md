# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.5] - 2026-06-07

### Added
- Aggiornamenti di app e Unit3DWebUp lanciabili dal bottone in UI (Impostazioni → Versione)
  anche nelle installazioni Docker: l'update è applicato in-place nel container e poi il
  container si riavvia da solo. È temporaneo — al successivo `docker compose pull` si torna
  alla versione dell'immagine, che resta il metodo di aggiornamento canonico.

### Fixed
- La Libreria si aggiorna automaticamente al termine del wizard (upload completato o
  solo-hardlink): l'elemento appena caricato viene segnato subito come "caricato"
  senza dover lanciare manualmente la scansione.

### Changed
- `docker-compose.yml` usa ora l'immagine pubblicata su Docker Hub per default
  (`hashdeveloper512/unit3dprep:latest`): `docker compose up -d` scarica l'immagine senza
  richiedere alcuna build locale. Per buildare in locale basta decommentare `build: .`.
- Guida Docker: §3 semplificato (rimosso `docker compose build`), §6 aggiornamento usa
  `docker compose pull`. Badge PyPI/Docker Hub nel README; tip installazione via `pip install
  unit3dprep` e immagine pubblicata.

## [1.0.4] - 2026-06-06

Release: **distribuzione ufficiale su PyPI e Docker Hub**. Ora `unit3dprep` si installa con `pip install unit3dprep` e l'immagine all-in-one con `docker pull hashdeveloper512/unit3dprep`. Inclusi i fix doc della guida Docker (Compose v2 richiesto).

### Added
- **Pubblicazione automatica su PyPI e Docker Hub**: a ogni `git tag vX.Y.Z` due workflow GitHub
  Actions pubblicano il pacchetto su PyPI (`pip install unit3dprep`) e l'immagine all-in-one su
  Docker Hub (`docker pull <utente>/unit3dprep`, tag `X.Y.Z`/`X.Y`/`latest`). Metadati `pyproject`
  completati (descrizione, README, licenza GPLv3, classifiers, link) per una pagina PyPI leggibile.

### Changed
- Auto-update in-app (modalità pip) ora si aggiorna da **PyPI**
  (`pip install --upgrade unit3dprep==X`) invece che dal tag GitHub.
- Guida Docker: **Compose v2 ora richiesto esplicitamente**. La vecchia `docker-compose` v1
  (1.29.2) è incompatibile con Docker Engine 25+ e fa crashare `docker compose up` con
  `KeyError: 'ContainerConfig'`; la guida ora lo segnala con un callout prominente, le istruzioni
  per installare il plugin v2 (binario CLI utente, valido anche senza il repo APT Docker) e una
  riga di troubleshooting dedicata.

## [1.0.3] - 2026-06-06

Release patch: setup **Docker all-in-one** ufficiale (Redis + Unit3DWebUp + unit3dprep in un singolo container, con `PUID`/`PGID`, pre-seed delle chiavi e Redis senza persistenza) e allineamento della documentazione al codice.

### Added
- **Setup Docker all-in-one ufficiale**: `Dockerfile`, `docker-compose.yml`, `config.env.example`
  e `.dockerignore` nel repo. Un singolo container avvia Redis + Unit3DWebUp + unit3dprep
  (entrypoint dedicato), con un solo volume `/data` che tiene config, media e seedings sullo
  stesso filesystem (hardlink funzionanti). `git clone && docker compose up -d` e l'interfaccia
  è raggiungibile su `http://127.0.0.1:8765`.
- **Nuova pagina di documentazione [Deploy › Docker](docs/docker.md)** (+ mirror inglese):
  guida passo-passo (clone, generazione hash, avvio), qBittorrent esterno con allineamento dei
  path, reverse proxy TLS e troubleshooting.
- **Supporto `PUID`/`PGID` nel container Docker**: lo stack fa drop dei privilegi all'utente
  indicato (default `1000:1000`), così i file scritti nel volume `./data` (config, db, torrent,
  hardlink) appartengono all'utente host e i media si gestiscono senza `sudo`. Impostabili in
  `config.env`; `PUID=0` mantiene l'esecuzione come root.
- **Pre-seed delle chiavi via env al primo boot Docker**: `TMDB_API_KEY` e, opzionali,
  `ITT_APIKEY`/`ITT_PID`/`TVDB_APIKEY`/`QBIT_*` impostate in `config.env` vengono scritte nella
  `.env` condivisa alla prima creazione, così Unit3DWebUp le legge subito (niente più warning
  `*_APIKEY not set`). Lette solo se la `.env` non esiste ancora: in seguito si configura tutto
  dalla web UI. Abilita il setup headless senza passare dall'interfaccia.

### Changed
- **Redis nel container Docker gira senza persistenza** (`--save "" --appendonly no`): è solo
  il job-store transitorio di webup, quindi nessun background-save (il warning del kernel
  "Memory overcommit must be enabled" diventa irrilevante) e nessun `dump.rdb` nel volume `./data`.

### Fixed
- **La "Variante Docker" documentata non era avviabile**: faceva riferimento a un `Dockerfile`
  mai incluso nel repo (`build: .` → errore `lstat Dockerfile: no such file`) e, anche
  correggendolo, non avrebbe funzionato (Redis come servizio separato irraggiungibile da webup,
  `media`/`seedings` su bind mount separati → hardlink falliti, `U3DP_HOST` su loopback,
  `U3DP_HTTPS_ONLY=1` su HTTP puro → login 401). Sostituita con l'immagine all-in-one funzionante.
- **Documentazione allineata al codice**: corretto il requisito Python (le guide indicavano
  3.10/3.11 ma `Unit3DwebUp 0.0.25` richiede **3.12+**, altrimenti `pip install` fallisce);
  i nomi canonici `.env` (`TRACKER__ITT_APIKEY`/`ITT_URL`/`ITT_PID`, non `TRACKER__APIKEYS`);
  il default di `U3DP_SYSTEMD_UNIT` (`unit3dprep-web.service`); i path SSE di wizard e quick-upload
  (`/api/wizard/{tok}/upload`, `/api/upload/{job}/stream`); e le righe di log attese nel setup Docker.

## [1.0.2] - 2026-06-01

Release patch: il numero di stagione (`S01`, `S02`, …) ora compare nel nome inviato al tracker per i pacchetti stagione delle serie.

### Fixed
- **Il numero di stagione (`S01`) spariva dal nome sul tracker** per i pacchetti stagione, pur essendo corretto nella rinomina locale. Unit3DWebUp componeva il titolo dall'ordine dei tag delle serie (`TAG_ORDER_SERIE`), che non includeva `season`, e lo legge una sola volta all'avvio. Ora il bridge inserisce l'etichetta di stagione direttamente nel nome inviato al tracker subito dopo lo scan: funziona senza dover riavviare Unit3DWebUp. Aggiunto inoltre `season` all'ordine di default delle serie e riparate automaticamente le configurazioni esistenti.

## [1.0.1] - 2026-05-31

Release patch dedicata a un bug di Unit3DwebUp 0.0.25 che impediva l'upload di tutti i media il cui *primo* audio track non è nella lingua preferita. Nessuna altra modifica funzionale rispetto a 1.0.0.

### Fixed
- **Upload silenzioso "InfoHash not found" su file con audio italiano NON come prima traccia**.
  Bug upstream in Unit3DwebUp 0.0.25 ([`services/tags_service.py:281`](https://github.com/31December99/Unit3DWebUp/blob/master/services/tags_service.py)):
  l'audio-language gate viene rivalutato a ogni iterazione del loop sulle tracce ma
  `media.can_upload` viene SOLO impostato a False, mai a True. Risultato: un file con
  audio `[eng, ita]` e `PREFERRED_LANG=it` veniva silenziosamente rifiutato perché alla
  prima iterazione (eng) il check fallisce. Il bridge ora applica una patch post-`/scan`
  via `unit3dprep/web/webup_job_fix.py::maybe_force_can_upload`: legge il record Media da
  Redis, verifica che la lingua preferita sia effettivamente presente in *qualche* traccia
  audio (tutti i codici ISO 639-1/2 + i nomi text-form di mediainfo), e in tal caso forza
  `can_upload=True` riscrivendo il job. Best-effort: errori Redis o JSON malformati non
  bloccano l'upload, vengono solo loggati come warning.

### Added
- Nuova dipendenza `redis>=5.0` (già installata transitivamente via `Unit3DwebUp`; ora dichiarata esplicitamente perché il fix sopra usa direttamente il client Redis async).

## [1.0.0] - 2026-05-26

Rilascio "1.0" che consolida la migrazione completa del backend di upload da `unit3dup` CLI (subprocess + parsing PTY) a `Unit3DwebUp` 0.0.25 (servizio FastAPI accoppiato via HTTP API + WebSocket). Architettura, configurazione, UI e documentazione sono state riscritte per riflettere questo nuovo modello. Vedi sotto per i dettagli e per i passaggi di migrazione consigliati.

### Added
- **Duplicate check pre-upload sul tracker ITT**. Prima del passo `hardlink` il wizard interroga `GET /api/torrents/filter?tmdbId=<id>` su `ITT_URL` e confronta il `size` in byte di ogni risultato con la dimensione del file locale. Se trova match esatto, mostra un nuovo step "Possibile duplicato" con i dettagli del torrent già presente (nome, tipo, risoluzione, uploader, attività, link al tracker) e due bottoni: "Carica comunque" / "Annulla". Replica il comportamento del vecchio `unit3dup` CLI (Unit3DwebUp 0.0.25 non implementa duplicate detection — `DUPLICATE_ON`/`SKIP_DUPLICATE` sono `# Todo Not yet implemented` upstream). Controllato dal nuovo runtime setting `W_DUPLICATE_CHECK` (default ON), editabile da **Settings → Default wizard**. Si applica a `kind=movie` e `kind=episode`; i season pack saltano il check (size aggregato non corrisponde a nessun torrent ITT). Best-effort: se l'API ITT è irraggiungibile o ritorna errore, il check viene saltato silenziosamente.
- **"Duplicato skippato" tracciato nella cronologia upload**. Quando l'utente clicca "Annulla" sul modal duplicato, il bridge registra una nuova entry nel DB con `duplicate_skipped=true` e `duplicate_info={…}` (snapshot dei dettagli del torrent esistente sul tracker), legata al `source_path` originale. Effetti:
  - L'item viene **nascosto dalla Media Library** (filtro `W_HIDE_UPLOADED` keya su `source_path`) — non più visibile come "da uploadare".
  - **Cronologia upload (`UploadedView`)** mostra un nuovo stato `⏭ duplicato skippato` (giallo) e una nuova stat card "Duplicati skippati" accanto a Totali/Completati/Falliti/Hardlink-only.
  - Niente hardlink creato — il wizard termina al passo del modal.

### Fixed
- **`PREFERRED_LANG` default `"ita"` faceva fallire ogni upload su Unit3DwebUp 0.0.25**. Webup confronta `PREFS__PREFERRED_LANG` con il campo `language` (ISO 639-1, es. `"it"`) di ciascuna traccia audio del mediainfo; usando il codice ISO 639-2 `"ita"` nessun match → `media.can_upload = False` → `UploadUseCase.execute()` saltava silenziosamente la submission al tracker (200 OK senza WS message, nessun POST a `/api/torrents/upload`, qBit seedava ma il tracker rispondeva "InfoHash not found"). Default cambiato a `"it"`; utenti esistenti devono aggiornare il valore da Settings UI o eseguire `sed -i 's/^PREFS__PREFERRED_LANG=.*/PREFS__PREFERRED_LANG=it/' ~/.config/unit3dprep/.env` + restart `unit3dwebup`.
- **Upload al tracker silenziosamente ignorato** (`PREFS__TORRENT_ARCHIVE_PATH=.`): quando `TORRENT_ARCHIVE_PATH` non era configurato dall'utente, `config.py` scriveva `PREFS__TORRENT_ARCHIVE_PATH=.` nel `.env` condiviso. Webup ricostruisce il path del `.torrent` tramite `Media.from_dict()` usando questo valore come radice, producendo un path relativo (`ITT/titolo.torrent`) il cui `Path.exists()` dipendeva dalla CWD del processo. Con CWD ≠ home il file risultava "non trovato", l'upload al tracker non veniva mai tentato, e lo status Redis restava a 3 senza alcun errore visibile. Fix: il fallback per le chiavi path obbligatorie usa ora `str(Path.home())` al posto di `"."`.
- **WebSocket drain `/upload`: nessun messaggio ricevuto**. Il drain post-HTTP di `/upload` aspettava solo 2 s e trattava la mancanza di `posterLogMessage` come errore fatale. Aumentato il timeout a 8 s e cambiato il fallback: se nessun messaggio WS arriva entro 8 s (race condition o glitch di connessione), il workflow prosegue al `/seed` con un warning (anziché bloccarsi con `exit_code=1`). Aggiunto logging diagnostico: stato WS e `queue.qsize()` prima e dopo il drain, più un INFO log in `_dispatch()` ogni volta che un `posterLogMessage` raggiunge le queue dei subscriber — così i log di uvicorn mostrano chiaramente se webup ha inviato il messaggio e quante queue lo hanno ricevuto.
- `/upload` al tracker: la risposta HTTP di webup (che incapsula la risposta dell'API del tracker) veniva scartata silenziosamente. Ora viene loggata nel flusso SSE (`webup: /upload tracker response → …`) e un eventuale status `!= 200` produce un evento `error` visibile in UI con il payload di rifiuto del tracker (es. errori di validazione).

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
- **Default `PREFERRED_LANG` cambiato da `"all"` a `"ita"`**. Webup `tags_service.mediainfo_audio` mette `media.can_upload=False` se `PREFERRED_LANG` non matcha nessuna traccia audio. Il valore letterale `"all"` non corrisponde ad alcun codice ISO, quindi webup rifiutava silenziosamente ogni upload (`tasks = [... if media.can_upload]` filtra a vuoto, `/upload` ritorna 200 senza chiamare il tracker, il torrent appare in qBit ma non sul sito). `"ita"` è il default corretto per ItaTorrents. Bug confuso da diagnosticare perché webup completa tutta la pipeline senza errori visibili.
- **Workaround upstream Unit3DWebUp: announce URL con `//announce/` nel `.torrent`**. Webup `unit3dwup/config/api_data.py` costruisce l'announce con `f"{settings.tracker.ITT_URL}/announce/{settings.tracker.ITT_PID}"`. Pydantic-settings normalizza `HttpUrl` aggiungendo automaticamente un trailing slash, producendo `https://itatorrents.xyz//announce/<pid>` che il tracker rifiuta con 404. Senza fix, qBittorrent non riesce a registrare il torrent e l'upload appare completato ma è invisibile sul sito. Aggiunto `_normalize_announce_in_torrent()` in `webup_orchestrator.py` che dopo `/maketorrent` legge il `.torrent`, sostituisce `//announce/` con `/announce/` in `announce` e `announce-list`, preserva l'info dict bytes verbatim per non alterare l'infohash. Bug upstream tracciato per PR a `31December99/Unit3DWebUp`.
- **Tracker URL doppio slash → torrent caricato non visibile sul sito**. Se l'URL del tracker era salvato con trailing slash (`https://itatorrents.xyz/`) la concatenazione webup `<url>/announce/<pid>` produceva `https://itatorrents.xyz//announce/<pid>` che il tracker rifiutava con 404. Webup completava `/upload` con HTTP 200 ma il torrent non si registrava sul tracker, qBittorrent mostrava "not found" sull'announce e l'utente vedeva un upload "completato" assente da ItaTorrents. Fix: `_normalize_tracker_urls()` strippa il trailing slash da `ITT_URL`/`PTT_URL`/`SIS_URL` sia in `load()` (per .env esistenti) che in `save()` (prima di scrivere). Default `PTT_URL` ora senza trailing slash.
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