# Integrazione Unit3DWebUp

Tutta la fase di upload al tracker è delegata a [`Unit3DWebUp`](https://pypi.org/project/Unit3DwebUp/) — un secondo servizio FastAPI che `unit3dprep` orchestra via HTTP + WebSocket. Questa pagina spiega l'architettura del bridge, il flusso di upload, la sincronizzazione della config e le limitazioni note.

---

## Architettura

```
┌────────────────────┐                        ┌──────────────────────┐
│   unit3dprep       │   HTTP /setenv /scan   │   Unit3DWebUp        │
│   (FastAPI + UI)   │ ─────────────────────> │   (FastAPI bot)      │
│                    │   /maketorrent /upload │                      │
│                    │   /seed /filter        │                      │
│                    │ <───────────────────── │                      │
│                    │   WebSocket events     │                      │
└────────┬───────────┘   (job_id channels)    └──────────┬───────────┘
         │                                                │
         │                                                │
         │  ─── shared .env ($ENVPATH/.env) ──────────────│
         │                                                │
         ▼                                                ▼
   ~/seedings/                              tracker (HTTPS) + qBittorrent + Redis
```

**Componenti chiave** (lato unit3dprep):

- `unit3dprep/web/webup_client.py` — singleton `httpx.AsyncClient` con tutti gli endpoint del bot.
- `unit3dprep/web/webup_ws.py` — `WebupWSManager`: WS persistent, demultiplex per `job_id`, queue async per consumer.
- `unit3dprep/web/webup_orchestrator.py` — `stream_webup()` async generator: il pipeline completo di un upload.
- `unit3dprep/web/webup_logclass.py` — `classify_msg()` / `is_terminal_success()` / `is_terminal_failure()`.
- `unit3dprep/web/api/webup.py` — router FastAPI: `/api/webup/{health,sync,setting,filter}`.
- `unit3dprep/web/api/version.py` — auto-update SSE per webup (`/api/version/update/webup/stream`).

**Singleton + scan-lock**:

- `WebupClient` è singleton-cached per (host, port). Una sola TCP keep-alive.
- `app.state.webup_scan_lock = asyncio.Lock()` serializza gli upload concorrenti — `SCAN_PATH` è uno stato globale dell'app webup, due `setenv` paralleli si pestano i piedi.

---

## Flusso upload (singolo job)

`stream_webup(seeding_path, kind, tmdb_id)` esegue 6 fasi con weight assegnati per la progress bar UI.

| # | Fase | Endpoint webup | Weight | Scopo |
|---|---|---|---:|---|
| 1 | `setenv` | `POST /setenv {PREFS__SCAN_PATH: <parent>}` | 3% | Imposta il path che `/scan` userà. Film: parent(file). Serie: parent(folder). |
| 2 | `scan` | `POST /scan` | 27% | Webup scansiona, esegue lookup TMDB/TVDB, genera screenshot via ffmpeg, uploada agli image host. |
| 3 | `settmdbid` | `POST /settmdbid` *(opzionale)* | — | Solo se l'ID che abbiamo passato differisce da quello risolto dal bot. |
| 4 | `maketorrent` | `POST /maketorrent` | 45% | Webup costruisce il `.torrent`. WS emette `[New torrent] FILE - N%` per il progress sub-fase. HTTP 200 = phase done. |
| 5 | `upload` | `POST /upload` | 15% | Webup fa l'upload al tracker (skip se `U3DP_DRY_RUN_TRACKER=1`). HTTP 200 + drenaggio log 2s. |
| 6 | `seed` | `POST /seed` | 10% | Webup aggiunge il torrent a qBittorrent. 200=ok, 503/409/404 = warning, altri = warning. |

**Eventi yield-ati dal generator**:

```python
{"type": "log",      "data": str, "kind": str, "event": str}
{"type": "progress", "phase": str, "label": str, "pct": float, "sub_pct": float}
{"type": "error",    "data": str}
{"type": "done",     "exit_code": int}
```

Consumati da:

- Wizard SSE (`/wizard/{token}/stream` + `/upload/{job}/stream`) → frontend con barra grafica.
- CLI `run_webup_sync()` → stdout testuale.

### Semantica `SCAN_PATH` + sandbox per-upload

Webup `/scan` processa **tutto** il contenuto di `SCAN_PATH` (lookup TMDB/TVDB, screenshot ffmpeg, upload image host) per ogni file/subfolder. Se SCAN_PATH punta a una directory affollata (es. `~/seedings` con 200 hardlink), webup scansiona tutti gli item in parallelo, esaurisce risorse (`[Errno 11] Resource temporarily unavailable`, `cannot reshape array of size 0`), e il file target viene perso.

Per evitarlo, il bridge crea una **sandbox dedicata per ogni upload** sotto `<seedings>/.unit3dprep/<jobid>/`. Il `<jobid>` è uno sha256 8-char del nome finale, deterministico → re-upload dello stesso item sovrascrive la stessa sandbox.

Layout su disco:

```
~/seedings/
├── .unit3dprep/
│   ├── 1a2b3c4d/                            # film
│   │   └── Philadelphia (1993) ... .mkv
│   ├── 5e6f7a8b/                            # serie
│   │   └── Severance (2022) S02/
│   │       ├── S02E01.mkv
│   │       └── …
│   └── …
```

Webup riconosce per subfolder dentro `SCAN_PATH`:

- **Film**: `SCAN_PATH = <seedings>/.unit3dprep/<jobid>/`, contenente UN solo file → `Media` per il singolo file.
- **Serie**: `SCAN_PATH = <seedings>/.unit3dprep/<jobid>/`, contenente UNA sola sottocartella → `Media` (pack) per la serie.

Niente race condition con altri file, scan veloce e affidabile. Gli hardlink condividono l'inode con il file originale in `media_root`, quindi la Media Library continua a marcare gli item come "caricati" via inode-fallback senza modifiche.

qBittorrent dopo `/seed` riceve il path sandbox come location del torrent: il file deve restare lì per il seeding. Le sandbox sono **permanenti** — non eliminarle a mano se vuoi continuare a seedare. Per ripulire torrent rimossi, cancella prima dal client torrent, poi la cartella.

### `job_id` deterministico

Webup calcola `job_id = sha256(str(normpath(folder/subfolder)))`. Il bridge calcola lo stesso valore con `webup_client.compute_job_id(match_path)` per pre-iscriversi al canale WS prima ancora di fare `/scan`, evitando la race "scan completa → bot inizia a emettere → noi ci abboniamo dopo → eventi persi".

### Gestione log streaming

`maketorrent` e `upload` ritornano HTTP 200 quando hanno finito (sincroni nel processo webup). Mentre la richiesta è in corso, il bot pubblica eventi sul WS. L'orchestrator drena il WS in due modalità:

- **Concorrente (maketorrent)**: il task HTTP corre, mentre un loop legge dalla queue WS e calcola la sub-percentuale dal regex `[New torrent] FILE - N`.
- **Post-200 (upload)**: subito dopo HTTP 200 vengono drenati per ~2s gli eventi finali (success/failure detection con `is_terminal_success` / `is_terminal_failure`).

---

## Config bridge: short ↔ canonical

Lo storage su disco è un singolo `.env` condiviso. Per non rompere la API storica unit3dprep, `unit3dprep/web/config.py` mantiene una traduzione bidirezionale:

```python
WEBUP_KEY_MAP = {
    "ITT_APIKEY": "TRACKER__APIKEYS",
    "ITT_URL": "TRACKER__URLS",
    "QBIT_HOST": "TORRENT__QBIT_HOST",
    "MULTI_TRACKER": "TRACKER__MULTI_TRACKER",
    "TAG_ORDER_MOVIE": "PREFS__TAG_POSITION_MOVIE",
    # ...
}
_WEBUP_TO_SHORT = {v: k for k, v in WEBUP_KEY_MAP.items()}
```

- **In memoria / API `/api/settings`**: nomi corti (`ITT_APIKEY`, `QBIT_HOST`, ...).
- **Su disco / `.env` / push a webup**: nomi canonici (`TRACKER__APIKEYS=["..."]`, ...).
- Liste come `MULTI_TRACKER` sono serializzate come **JSON arrays** (richiesto da pydantic-settings v2 di webup), non CSV.

### Skip rules

`_to_webup_env_payload(state)` filtra prima del push verso webup:

| Valore | Skip? | Motivo |
|---|---|---|
| `""` (stringa vuota) | Sì | Webup `empty_to_none` valida → `None` su `str` field → `SystemExit` |
| `None` | Sì | Idem |
| `"no_key"`, `"no_pass"`, `"no_path"`, `"no_comment"` | Sì | Placeholder senza valore reale |
| Tutto il resto | No | Pushed a webup |

**Eccezioni** (sempre pushed con fallback `.` se vuoti): `PREFS__TORRENT_ARCHIVE_PATH`, `PREFS__WATCHER_PATH`, `PREFS__WATCHER_DESTINATION_PATH`, `PREFS__SCAN_PATH`. Webup richiede questi come `Path`-able esistenti.

### IMAGE_HOST_ORDER → priorità numeriche

Unit3dprep tiene un'unica lista ordinata `IMAGE_HOST_ORDER=["IMGFI","PTSCREENS","IMGBB"]`. Webup invece usa priorità numeriche per host (`PREFS__IMGFI_PRIORITY=1`, `PREFS__PTSCREENS_PRIORITY=2`, ...). La proiezione assegna `1, 2, 3, ...` alla lista, e `99` agli host non in lista — così webup non tenta upload verso host senza chiave.

### Mascheramento secret

Tutti i secret (vedi lista `MASKED_KEYS` in `unit3dprep/web/config.py`) vengono restituiti come `"__SET__"` da `GET /api/settings`. In `PUT`, `"__SET__"` significa "non toccare il valore esistente". Questo evita leak in browser DevTools / response cache.

---

## Health check

Endpoint: `GET /api/webup/health`. Cache 5s.

```json
{
  "online": true,
  "version": "0.0.25",
  "latency_ms": 12.4,
  "ws_connected": true,
  "url": "http://127.0.0.1:8000",
  "envpath_dir": "/home/user/.config/unit3dprep"
}
```

Lookup versione (chain): HTTP `/setting` → `pip metadata` (subprocess `<WEBUP_VENV_BIN>/python -c "import importlib.metadata; print(importlib.metadata.version('Unit3DwebUp'))"`) → parse `.env`. Se tutti e tre falliscono → `null`.

Render UI: card "Unit3DWebUp" in Settings con badge online/offline + version + ms latency + indicatore WebSocket.

### Push manuale config

`POST /api/webup/sync`: rimanda l'intero payload `.env` corrente al bot via batch di `setenv`. Utile dopo:

- Restore di un backup.
- Sospetta drift tra il `.env` su disco e lo stato in memoria del bot.
- Riavvio webup senza riavvio app (di solito non serve, ma se persistono problemi).

UI: bottone **"Spingi config"** sulla card webup.

---

## Auto-update SSE

Due flussi SSE separati:

- `GET /api/version/update/webup/stream` — esegue `pip install --upgrade Unit3DwebUp` nel venv di webup, riavvia `WEBUP_SYSTEMD_UNIT` in scope transient.
- `GET /api/version/update/app/stream` — `git pull + pip install -e .` (modalità git) o `pip install --upgrade --force-reinstall git+URL@vX` (modalità pip), riavvia `U3DP_SYSTEMD_UNIT`.

Entrambi:

1. Streamano `pip` / `git` log line-by-line.
2. Su `done`: azzerano `_cache["data"] = None; _cache["at"] = 0.0` PRIMA di emettere l'evento finale (altrimenti la versione mostrata in UI dopo reload è stantia per 10 min).
3. Schedulano restart in `systemd-run --user --on-active=3s` come scope transient → sopravvive al SIGTERM del processo padre quando systemd ferma il service.
4. Frontend: countdown 5s + reload del browser; popup post-reload con il body della release GitHub salvato in `localStorage["unit3dprep.pendingChangelog"]`.

!!! warning "Mai dimenticare il flush cache"
    Tutti e 3 i generator (webup, app/git, app/pip) DEVONO fare `_cache["data"]=None; _cache["at"]=0.0` prima di `yield _sse("done", ...)`. Omettere causa versione + bottone update stantii dopo reload.

---

## Dry-run mode

`U3DP_DRY_RUN_TRACKER=1` (o `true`/`yes`) salta `/upload` ma esegue tutto il resto:

- `setenv → scan → maketorrent → seed` ✅
- `upload` ❌ (skipped, log warning emesso con `event=upload.dryrun`)

Il `.torrent` finisce comunque in qBit. Utile per:

- Testing in WSL/dev.
- Debugging del pre-flight unit3dprep + bridge senza polluire il tracker live.
- Verifica che il pipeline funzioni end-to-end prima di abilitare l'upload reale.

Anche il batch upload (`stream_webup_batch`) rispetta il flag: in dry-run esegue `maketorrent + seed` per ogni job, salta `processall`.

---

## Limitazioni note

| Limitazione | Causa | Workaround |
|---|---|---|
| `DUPLICATE_ON` / `SKIP_DUPLICATE` non funzionano | Webup ha `# Todo Not yet implemented` in `config/settings.py` | Il bridge li scrive comunque nel `.env` (per future versioni); attualmente il bot li ignora. |
| Redis non spostabile da `127.0.0.1:6379` | Webup hardcoded | Run Redis sulla porta default. `REDIS_HOST/PORT` ignorate. |
| ffmpeg fallisce silenziosamente | Webup screenshot generation | Verifica `which ffmpeg` prima del primo upload. Se manca, `/scan` ritorna `[]`. |
| `DOCKER` env truthy check rotto | Webup `config/settings.py`: `if not os.getenv("DOCKER")` | Mai impostare `DOCKER` a meno di non essere in Docker (e in quel caso, `DOCKER=true`). |
| Liste in `setenv` come JSON | Pydantic-settings v2 fa `json.loads()` | Il bridge serializza già JSON. Edit manuali al `.env` con CSV rompono il bot al primo `setenv`. |
| Empty values su `str` rompono webup | `empty_to_none` validator | Il bridge skippa già; per `.env` editati a mano, rimuovi le righe `KEY=` vuote. |

---

## Comandi utili di debug

```bash
# Bot è up?
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200

# Versione webup installata
$WEBUP_VENV_BIN/python -c "import importlib.metadata as m; print(m.version('Unit3DwebUp'))"

# Health da unit3dprep
curl -s http://127.0.0.1:8765/api/webup/health  # se loggato in browser, ricava cookie

# Reset Redis (cancella job_list_id stale)
redis-cli FLUSHDB

# Forza re-sync intera config a webup
# (dalla UI: Settings → bottone "Spingi config"; oppure POST /api/webup/sync con cookie sessione)
```

Per problemi specifici vedi [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup) e [Troubleshooting › Bridge](troubleshooting.md#bridge-unit3dprep-webup).
