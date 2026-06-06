# Troubleshooting

Raccolta dei problemi più comuni e delle loro cause note.

---

## Hardlink

### `OSError: [Errno 18] Invalid cross-device link`

`U3DP_MEDIA_ROOT` e `U3DP_SEEDINGS_DIR` sono su filesystem diversi. Verifica:

```bash
df <media> <seedings>
```

Se il numero di device è diverso, sposta `~/seedings/` sotto lo stesso mount dei media o punta `U3DP_SEEDINGS_DIR` a un path valido.

La UI espone `GET /api/settings/fs-check` per fare lo stesso controllo dal browser.

### L'hardlink riesce ma l'upload prende spazio doppio

Non dovrebbe succedere: gli hardlink condividono gli inode. Se vedi `du` raddoppiato, controlla che il FS sia effettivamente lo stesso (`stat -c %i <file_media> <file_seedings>` → stesso inode).

---

## MediaInfo

### `pymediainfo` si installa ma crasha a runtime

Manca `libmediainfo`. Installa il pacchetto di sistema:

- Debian/Ubuntu: `sudo apt install libmediainfo0v5`
- Arch: `sudo pacman -S libmediainfo`
- macOS: `brew install mediainfo`
- Alpine: `apk add mediainfo`

Su Ultra.cc dovrebbe essere già presente; se manca, apri un ticket.

---

## Unit3DWebUp

### Tutte le richieste a webup tornano 500

Tre cause comuni:

1. **`DOCKER` env var impostata** → `config/settings.py` di webup ha `env_file=ENV_FILE if not os.getenv("DOCKER") else None` (truthy check). Qualunque valore non vuoto (incluso `false`) blocca la lettura del `.env` → ogni `TRACKER__/PREFS__` riporta "Field required". **Fix**: rimuovi `DOCKER` dal file unit / shell. Usa `DOCKER=true` SOLO se sei davvero in Docker.
2. **Valori vuoti su campi `str` nel `.env`** → es. `TRACKER__APIKEY=` (vuoto) sui validator pydantic con `empty_to_none` → `None` → `SystemExit(1)` al primo `setenv`. **Fix**: il bridge unit3dprep skippa già i valori vuoti, ma se hai editato `.env` a mano rimuovi le righe `KEY=` vuote.
3. **`PREFS__TORRENT_ARCHIVE_PATH` mancante / vuoto / inesistente** → webup `get_settings()` fallisce. Il bridge mette `.` come fallback, ma se hai editato il `.env` a mano e cancellato la chiave, riapri Settings → Save in UI per riapplicare il fallback.

### Versione webup mostra `Corrente: -` / pulsante Update sempre visibile

La chain di lookup è: HTTP `/setting` → `pip metadata` (venv) → parse `.env`. Se tutti e tre falliscono, la card resta su `-`.

```bash
# Verifica venv corretto
ls "$WEBUP_VENV_BIN/python"   # default ~/dev/Unit3DWebUp/.venv/bin/python
$WEBUP_VENV_BIN/python -c "import importlib.metadata as m; print(m.version('Unit3DwebUp'))"
```

Se errore `PackageNotFoundError`, installa:

```bash
$WEBUP_VENV_BIN/pip install Unit3DwebUp
```

### `/scan` ritorna `0 items`

Tre cause:

1. **ffmpeg mancante** — webup genera screenshot via ffmpeg, fallisce silenziosamente. Verifica `which ffmpeg`.
2. **TMDB/TVDB API key invalide** — webup logga ma `/scan` ritorna comunque `[]`. Controlla `TRACKER__TMDB_APIKEY` / `TRACKER__TVDB_APIKEY` nel `.env`.
3. **Image host non configurato** — webup tenta di uploadare gli screenshot prima di rispondere. Se nessun host ha chiave valida, la pipeline fallisce. Configura almeno un host in **Settings → Image host**.

### `MULTI_TRACKER` o `TAG_POSITION_*` rifiutati da `/setenv`

Webup richiede liste come **JSON arrays** (non CSV). Pydantic-settings v2 esegue `json.loads()` su `os.environ` dopo `/setenv`. Esempio corretto: `TRACKER__MULTI_TRACKER=["itt"]`.

Il bridge unit3dprep serializza già correttamente: se il problema persiste, controlla che non ci siano edit manuali al `.env` con CSV (`itt,ptt`).

### `/upload` ritorna 200 ma il torrent non appare sul tracker — qBit dice "InfoHash not found"

Il sintomo: qBit seedando localmente, `/upload` HTTP risponde 200 OK in pochi ms, `/seed` riesce, ma il tracker non vede l'upload e lo status announce di qBit dice **"InfoHash not found"**. Nessuna riga di log webup tra `POST /upload 200 OK` e `POST /seed`, nessun `posterLogMessage` di upload nella Web UI.

**Causa**: `PREFS__PREFERRED_LANG` è un codice ISO **639-2** (`"ita"`, `"eng"`, `"fre"`) invece di **639-1** (`"it"`, `"en"`, `"fr"`). Webup 0.0.25 in `tags_service.mediainfo_audio` confronta `PREFERRED_LANG` con il campo `language` di ogni traccia audio del mediainfo, che è emesso come codice 2-lettere. Mismatch → `media.can_upload = False` → `UploadUseCase.execute()` filtra fuori il media (`tasks = [... if media.can_upload]`) → ritorna 200 OK con `tasks=[]` → nessuna submission al tracker, nessun WS message.

**Fix**:

```bash
sed -i 's/^PREFS__PREFERRED_LANG=.*/PREFS__PREFERRED_LANG=it/' ~/.config/unit3dprep/.env
systemctl --user restart unit3dwebup
# Rimuovi il .torrent stantio dall'archive (altrimenti webup riusa quello e salta maketorrent):
rm -f "$(grep ^PREFS__TORRENT_ARCHIVE_PATH ~/.config/unit3dprep/.env | cut -d= -f2-)/ITT/<file>.mkv.torrent"
# Rimuovi il torrent da qBit (UI o CLI) per evitare conflitto infohash, poi retry dalla Web UI.
```

Da v0.6.4+ il default in `DEFAULT_CONFIG` è già `"it"`; il problema riguarda solo installazioni esistenti con `.env` migrato dalla v0.6.3.

### Webup `/upload` blocca / nessun progress

Webup emette `posterLogMessage` come `[New torrent] FILE - N%` durante maketorrent, **non** "torrent created/exists". L'orchestrator unit3dprep usa `HTTP 200 = phase complete` + drenaggio log buffered ~1.5–2s. Se vedi blocchi:

- Aumenta `PHASE_TIMEOUT` (default 1800s) in `webup_orchestrator.py`.
- Verifica WebSocket connesso: card Settings → Unit3DWebUp deve mostrare WS `connected`.
- Riavvia il bot: `systemctl --user restart unit3dwebup.service`.

### Redis non spostabile

`Unit3DWebUp` hardcoda Redis a `localhost:6379`. `REDIS_HOST` / `REDIS_PORT` sono ignorate. Se hai un Redis su porta non standard, mettilo anche su 6379 oppure usa redirect `iptables`/`socat`.

### Pulizia stale `job_list_id` Redis

Se `/processall` (batch upload) si comporta in modo strano dopo crash o test ripetuti:

```bash
redis-cli FLUSHDB
```

Cancella tutta la chiave `job_list_id` cached e fa ripartire il bot da zero.

---

## Auto-update

### Update in loop / EventSource riconnette

`EventSource` del browser riconnette automaticamente quando un endpoint SSE chiude la connessione (es. dopo `systemctl restart`). Il modal `UpdateProgressModal` deve chiamare `closeSSE()` su `done`/`error`. Se vedi un loop, è regression: il fix è già in v0.6.x — verifica di non avere installazioni miste con stale frontend.

### Versione e bottone Update stantii dopo reload

`/api/version/info` cache TTL = 10 min. Dopo un update riuscito, l'endpoint `update/{webup,app}/stream` deve azzerare `_cache` PRIMA di emettere `done`. Se vedi versione vecchia + bottone update visibile dopo reload:

1. Force refresh: bottone "Controlla aggiornamenti" → `POST /api/version/refresh`.
2. Se persiste: hard reload del browser (`Ctrl+Shift+R`).
3. Se persiste ancora: verifica che `_cache["data"] = None` sia chiamato in `update_unit3dup` / `_update_app_from_pip` / `_update_app_from_git` PRIMA di `yield _sse("done", ...)`.

### `can_update_app: false` perpetuo

Tre cause:

1. `systemctl` non è nel PATH del processo.
2. `U3DP_SYSTEMD_UNIT` punta a una unit che non esiste. **Fix**: imposta `U3DP_SYSTEMD_UNIT=unit3dprep-web.service` in `[Service] Environment=...` (o salvalo da Settings → App Auto-Update).
3. La unit esiste ma non è accessibile da `systemctl --user cat`. Verifica con `systemctl --user cat <unit>` dalla shell del processo.

### `status=203/EXEC` su `systemctl status`

Path in `ExecStart` non esiste (NON è un errore Python). Verifica:

```bash
ls -la $(grep -oP 'ExecStart=\K\S+' ~/.config/systemd/user/<unit>.service)
which unit3dprep-web
```

### Update webup fallisce con "Could not open requirements file"

Stai usando un'installazione vecchia che fa `pip install -r requirements.txt`. Webup `0.0.x` non distribuisce più `requirements.txt`. Il fix è già in v0.6+: controlla di avere l'app aggiornata.

---

## Web UI / FastAPI

### `AssertionError: SessionMiddleware must be installed`

Ordine dei middleware sbagliato. `SessionMiddleware` deve essere aggiunto **dopo** il middleware auth (FastAPI applica i middleware in LIFO → l'ultimo aggiunto è il più esterno). Se auth tenta di leggere `request.session` prima che SessionMiddleware sia installato, crash.

Se lo vedi dopo aver toccato `unit3dprep/web/app.py`, ripristina l'ordine `add_middleware(auth)` **prima** di `add_middleware(SessionMiddleware, ...)`.

### Login 401 senza errori a startup

Hash bcrypt mutilato. Il file `.env` o l'`Environment=` di systemd ha `U3DP_PASSWORD_HASH="$2b$12$..."` con apici doppi: bash espande `$2b`/`$12` come variabili vuote → hash troncato → login fallisce silenziosamente.

**Fix**: usa apici singoli o escape:

```bash
U3DP_PASSWORD_HASH='$2b$12$...'    # apici singoli
# OPPURE
U3DP_PASSWORD_HASH=\$2b\$12\$...   # escape
```

### 404 su tutte le route sotto `/unit3dprep`

Disallineamento tra `U3DP_ROOT_PATH` e il comportamento dell'nginx davanti. Due combinazioni valide:

| nginx `proxy_pass` | `U3DP_ROOT_PATH` |
|---|---|
| `http://127.0.0.1:8765` (senza slash finale) | `/unit3dprep` |
| `http://127.0.0.1:8765/` (con slash finale) | `""` |

Se sei su Ultra.cc, vai con la prima. `app-nginx restart` dopo ogni modifica.

### Pagina bianca con asset 404

Il frontend richiede asset su `{ROOT_PATH}/assets/...`. L'app li monta in `app.mount(f"{ROOT_PATH}/assets", ...)`. Se vedi 404 sugli asset:

1. Verifica che `unit3dprep/web/dist/` contenga `index.html` + `assets/`.
2. Verifica che `index.html` contenga `window.__ROOT_PATH__ = "/unit3dprep"` (iniettato a serve-time).
3. Riavvia il service dopo aver cambiato `U3DP_ROOT_PATH`.

### Cookie di sessione non persistente dietro HTTPS

Imposta `U3DP_HTTPS_ONLY=1` e verifica che nginx stia forwardando `X-Forwarded-Proto: https`. Altrimenti Starlette imposta `Secure` sul cookie ma il browser vede HTTP → cookie droppato.

### SSE (Server-Sent Events) si chiude subito

Problema tipico con nginx: buffering. Aggiungi nel server block:

```nginx
proxy_buffering off;
proxy_read_timeout 1h;
```

Su Ultra.cc questo è già consigliato nella [guida nginx](deploy-ultracc.md#8-nginx-user-proxy).

---

## Bridge unit3dprep ↔ webup

### Card Settings → Unit3DWebUp **rossa** (offline)

Verifica nell'ordine:

1. Bot in esecuzione? `systemctl --user status unit3dwebup.service` o `curl http://127.0.0.1:8000/setting -X POST -d '{}' -H 'Content-Type: application/json'`.
2. `WEBUP_URL` punta al posto giusto? `echo $WEBUP_URL` (default `http://127.0.0.1:8000`).
3. Redis attivo? `redis-cli ping` → `PONG`.
4. Logs: `journalctl --user -u unit3dwebup -f` mostra errori a startup?

### Settings UI Save non aggiorna webup

Ogni `PUT /api/settings` triggera `webup_client.setenv(key, value)` per ogni chiave canonica modificata. Se il `setenv` fallisce, il save UI riesce comunque (atomic write su `.env` + propagazione best-effort).

Verifica:

1. Card Health verde — webup raggiungibile?
2. Logs tab → filtro source `webup` — vedi errori `setenv: ...`?
3. Bottone **"Spingi config"** in Settings forza un `POST /api/webup/sync` (push completo del `.env` mappato). Usalo dopo restore backup o se sospetti drift.

### Wizard upload "no Media for X (0 items)" o "(got N items)" con il tuo file mancante

Il bridge crea per ogni upload una sandbox dedicata `<seedings>/.unit3dprep/<jobid>/` e usa quella come `SCAN_PATH`, così webup vede solo l'item target. Vedi [Integrazione Unit3DWebUp › sandbox per-upload](integrazione-webup.md#semantica-scan_path-sandbox-per-upload).

Se vedi comunque l'errore:

- **ffmpeg mancante** → webup `/scan` fallisce silenziosamente sui screenshot. `which ffmpeg`.
- **TMDB/TVDB API key invalide o vuote** → webup logga `[ERROR] AsyncHttpClient: ... value should be str, int or float, got None`. Settala in **Settings → Metadata** (sia `TMDB_APIKEY` per webup, sia `TMDB_API_KEY` env per unit3dprep — stesso valore).
- **Image host non configurato** → webup tenta upload screenshot prima di rispondere. Configura almeno una chiave in **Settings → Image host**.
- **Layout legacy in `~/seedings/<file>.mkv` (flat, no sandbox)** → installazione pre-sandbox layout. Re-uploada da UI per generare la sandbox, oppure sposta a mano in `<seedings>/.unit3dprep/<random>/<file>.mkv`.
- **Race condition con altre sandbox attive** → `app.state.webup_scan_lock` serializza gli upload nel processo unit3dprep. Se hai più istanze unit3dprep che parlano allo stesso webup, sospendine una.

---

## TMDB

### `TMDB API error: 401 Unauthorized`

`TMDB_API_KEY` mancante o errato. Controlla su <https://www.themoviedb.org/settings/api>.

La CLI prompt-a su ogni lancio. La Web UI usa sia `TMDB_API_KEY` (env unit3dprep) sia `TRACKER__TMDB_APIKEY` (chiave webup nel `.env` condiviso) — entrambi devono avere lo stesso valore valido.

### Ricerca TMDB restituisce zero risultati

Verifica `U3DP_TMDB_LANG`. Se è `it-IT` e il titolo non esiste in italiano, prova `en-US`.

---

## CHANGELOG legacy

### Record `pending` bloccati

Il record rimane `pending` se l'endpoint non ha chiamato `update_exit_code`. Casi noti:

- `quickupload.py` deve chiamare `await update_exit_code(state["path"], code)` sull'evento `done`.
- `wizard.py` → `wizard_finish` deve chiamare `await update_exit_code(seeding_path, 0)` (lo stato in memoria non basta).

Se succede post-aggiornamento, verifica che queste chiamate esistano ancora nel codice. È un regression marker: mai rimuoverle.

---

## Sviluppo / Windows

### Env var `U3DP_ROOT_PATH=/unit3dprep` si trasforma in un path Windows

MSYS2 / Git Bash su Windows convertono automaticamente le stringhe che iniziano con `/`. Per bypassare:

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  env U3DP_ROOT_PATH=/unit3dprep python -m uvicorn unit3dprep.web.app:app
```

Oppure usa PowerShell (`$env:U3DP_ROOT_PATH = "/unit3dprep"`).

### WSL dev: `pip install` errore `externally-managed-environment`

Stai eseguendo uvicorn con `/usr/bin/python3` invece del venv. L'auto-update fa `sys.executable -m pip` → PEP 668 blocca. **Fix**: avvia uvicorn con `.venv/bin/uvicorn` (o con venv attivo).

### WSL dev: `systemd unit not available`

Normale in WSL dev. Il flow di update richiede systemd `--user`. Testa l'update flow solo su Ultra.cc o un VPS reale.

### Build backend fallisce su Python 3.14

Usa `setuptools.build_meta`, non `setuptools.backends.legacy` (già corretto in `pyproject.toml`).

### `ENVPATH` leakka cross-shell

`ENVPATH` è una convenzione documentata da webup upstream e si propaga facilmente tra shell. Nei comandi di manutenzione usa il prefisso esplicito:

```bash
U3DP_ENV_PATH=$HOME/.config/unit3dprep/.env python -c "from unit3dprep.web import config; config.save(config.load())"
```

altrimenti `config_path()` può risolvere a `$ENVPATH/.env` (es. `/home/<user>/.env`) e scrivere nel posto sbagliato.

---

## Storico JSON

### Il file diventa grande

`~/.unit3dprep_db.json` cresce linearmente con gli upload. Se ti preoccupa:

```bash
jq '.[:1000]' ~/.unit3dprep_db.json > ~/.unit3dprep_db.json.trim
mv ~/.unit3dprep_db.json.trim ~/.unit3dprep_db.json
```

Backup prima sempre.

### `_sqlite3` rotto su pyenv 3.13 / Ultra.cc

Noto. Il progetto **non usa** SQLite proprio per questo motivo: storico + cache sono file JSON. Se vedi errori `_sqlite3 undefined symbol`, provengono da un'altra libreria. Installa Python 3.12 via pyenv (minimo richiesto da Unit3DWebUp 0.0.25) e punta il venv a quello.

---

## Se nulla funziona

1. `journalctl --user -u unit3dprep-web -u unit3dwebup -f` (Ultra.cc) o `journalctl -u unit3dprep-web -u unit3dwebup -f` (VPS).
2. Logs live nella Web UI → pannello Logs (filtra per source `webup` per i problemi del bot).
3. Apri un issue: <https://github.com/davidesidoti/unit3dprep/issues> con:
   - Versione Python (`python3 --version`)
   - Output di `pip show unit3dprep` e `pip show Unit3DwebUp`
   - Variabili d'ambiente rilevanti (senza secret)
   - Ultimi ~50 righe di `journalctl` per entrambe le unit
   - Output di `GET /api/settings/fs-check` e `GET /api/webup/health`
