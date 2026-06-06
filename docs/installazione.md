# Installazione

Questa guida copre l'installazione su sistema Linux/macOS/WSL con Python 3.12+, sia di `unit3dprep` (Web UI + CLI) sia del backend di upload `Unit3DWebUp`. Per il deploy in produzione vedi [VPS](deploy-vps.md) o [Ultra.cc](deploy-ultracc.md).

## Prerequisiti

| Requisito | Note |
|---|---|
| **Python 3.12+** | **Richiesto da Unit3DWebUp 0.0.25** (`requires_python >=3.12`): su 3.10/3.11 il `pip install Unit3DwebUp` del passo 2 fallisce con errore *Requires-Python*. `unit3dprep` da solo gira anche su 3.10, ma per lo stack completo serve 3.12+. 3.13 ok (il progetto usa JSON, non `_sqlite3`). |
| **libmediainfo** | Libreria di sistema richiesta da `pymediainfo`. Debian/Ubuntu: `sudo apt install libmediainfo0v5`. macOS: `brew install mediainfo`. |
| **ffmpeg** | Richiesto da Unit3DWebUp per generare gli screenshot. Senza, `/scan` ritorna 0 item silenziosamente. Debian/Ubuntu: `sudo apt install ffmpeg`. |
| **Redis** | Richiesto da Unit3DWebUp. Hardcoded a `127.0.0.1:6379` (le env vars `REDIS_HOST`/`REDIS_PORT` sono ignorate da webup). Debian/Ubuntu: `sudo apt install redis-server && sudo systemctl enable --now redis-server`. |
| **TMDB API key** | Crea un account su <https://www.themoviedb.org/> e richiedi una chiave v3 dalle impostazioni. Stesso valore va passato sia a unit3dprep (`TMDB_API_KEY`) sia a Unit3DWebUp (`TMDB_APIKEY` nel `.env` condiviso). |
| **Filesystem condiviso** | `U3DP_MEDIA_ROOT` e `U3DP_SEEDINGS_DIR` devono stare sullo **stesso filesystem** per consentire gli hardlink. |
| **Node.js** | *Solo* se vuoi ricompilare il frontend. Il pacchetto include già la build. |

## 1 — Clona unit3dprep e installa

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Entry points registrati:

- `unit3dprep` → CLI interattiva
- `unit3dprep-web` → server Web UI

## 2 — Installa Unit3DWebUp

`Unit3DWebUp` è il backend HTTP che fa l'upload effettivo al tracker. Installalo da PyPI nello stesso venv (più semplice) o in un venv dedicato:

!!! danger "Serve Python 3.12+"
    `Unit3DwebUp` 0.0.25 dichiara `requires_python >=3.12`: se il venv del passo 1 è su Python 3.10/3.11, `pip install Unit3DwebUp` fallisce con `ERROR: ... requires a different Python`. Verifica con `python3 --version` e, se serve, ricrea il venv con un interprete 3.12+.

```bash
# Stesso venv (semplice)
pip install Unit3DwebUp

# Oppure venv dedicato
mkdir -p ~/dev/Unit3DWebUp && cd ~/dev/Unit3DWebUp
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install Unit3DwebUp
.venv/bin/python -c "import unit3dwup.start; print(unit3dwup.start.app)"
```

!!! warning "Niente `requirements.txt`"
    Il branch `0.0.x` di `Unit3DWebUp` **non distribuisce più `requirements.txt`**. L'install canonico è via PyPI come sopra. L'auto-update integrato in `unit3dprep` esegue `pip install --upgrade Unit3DwebUp` (NON `-r requirements.txt`).

## 3 — Genera hash password e secret

```bash
python generate_hash.py
```

Ti chiede una password (doppia conferma) e stampa le righe da esportare:

```bash
export U3DP_PASSWORD_HASH='$2b$12$...'      # apici SINGOLI obbligatori
export U3DP_SECRET="..."
export TMDB_API_KEY="<la_tua_chiave_tmdb>"
export U3DP_PORT="8765"
export U3DP_HTTPS_ONLY="1"
export ENVPATH="$HOME/.config/unit3dprep"   # directory del .env condiviso
```

Copiale in `~/.bashrc` (o `~/.profile` / `~/.zshrc`) e ricarica con `source ~/.bashrc`.

!!! danger "Apici singoli sull'hash bcrypt"
    `U3DP_PASSWORD_HASH` contiene il carattere `$` (es. `$2b$12$...`). In bash con apici doppi i `$2b` e `$12` vengono espansi come variabili vuote → hash mutilato → login 401 senza errori al startup. Usa **sempre** apici singoli, o il carattere di escape, anche dentro i file `.env` di systemd.

!!! warning "Secret obbligatori"
    Senza `U3DP_PASSWORD_HASH` e `U3DP_SECRET` la Web UI non parte. Il secret firma i cookie di sessione: non condividerlo mai e non committarlo.

## 4 — Prepara le cartelle

Struttura attesa di default:

```
~/
├── media/
│   ├── movies/
│   │   └── <titolo film>/file.mkv
│   ├── series/
│   │   └── <titolo serie>/Season 01/S01E01.mkv
│   └── anime/
└── seedings/          # deve stare sullo stesso FS di ~/media
```

Le categorie vengono **auto-scoperte** come sottocartelle di `~/media/`. Puoi chiamarle come vuoi (`movies`, `film`, `anime`, `documentari`, ...) e aggiungerne di nuove senza toccare il codice.

### Verifica filesystem condiviso

Gli hardlink funzionano solo all'interno dello stesso filesystem. Controlla:

```bash
df ~/media ~/seedings
```

Entrambi i path devono elencare lo **stesso device**. Se differiscono, sposta `~/seedings/` su un altro punto dell'FS dei media oppure usa `U3DP_SEEDINGS_DIR` per puntarlo altrove (vedi [Configurazione](configurazione.md)).

L'endpoint `GET /api/settings/fs-check` fa lo stesso controllo via Web UI.

## 5 — (Opzionale) Ricompila il frontend

Il frontend React è pre-buildato in `unit3dprep/web/dist/` e committato nel repo. Ricompilalo solo se hai modificato il codice in `frontend/`:

```bash
cd frontend
npm install
npm run build
```

La build popola `unit3dprep/web/dist/`. `MANIFEST.in` la include nel wheel, quindi chi installa via pip non ha bisogno di Node.

## 6 — Avvia Unit3DWebUp

Il bot deve girare prima di `unit3dprep-web` (l'app può avviarsi anche senza, ma il wizard upload fallirà alla prima richiesta). Avvialo manualmente:

```bash
ENVPATH=$HOME/.config/unit3dprep \
  uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000
```

Per renderlo persistente vedi i template in [`deploy/systemd/`](https://github.com/davidesidoti/unit3dprep/tree/main/deploy/systemd) (sezione `unit3dwebup.service`) o le guide [VPS](deploy-vps.md) / [Ultra.cc](deploy-ultracc.md).

Verifica:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Deve rispondere con un JSON `{"userPreferences": {...}}`. Se vedi `500` su tutto, leggi [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup).

## 7 — Avvia unit3dprep

```bash
unit3dprep-web
```

Apri <http://127.0.0.1:8765>. Login con la password scelta in `generate_hash.py`. Vai in **Settings** e completa:

- **Tracker** — URL + API key + PID per ITT (e opzionalmente PTT, SIS).
- **Torrent client** — qBittorrent host/port/credenziali.
- **Image host** — almeno una chiave configurata, ordinata in `IMAGE_HOST_ORDER`.
- **Metadata** — TMDB key (stesso valore di `TMDB_API_KEY`), opzionalmente TVDB e IGDB.

Le impostazioni vengono salvate atomicamente in `$ENVPATH/.env` con la nomenclatura canonica (`TRACKER__*`, `TORRENT__*`, `PREFS__*`) e sincronizzate a Unit3DWebUp via `POST /setenv` senza riavvio.

Per la CLI:

```bash
unit3dprep -u /path/al/film.mkv
unit3dprep -f /path/alla/stagione
```

Vedi [Uso › CLI](uso-cli.md) e [Uso › Web UI](uso-web.md).

## Migration da `Unit3Dbot.json` legacy

Se in passato hai usato `unit3dup` direttamente, esiste probabilmente un `~/Unit3Dup_config/Unit3Dbot.json` con la tua config storica. Al primo `load()` di `unit3dprep`:

1. il file viene letto;
2. riscritto come `.env` in `$ENVPATH/.env` con la nomenclatura canonica;
3. rinominato in `Unit3Dbot.json.migrated-bak` (mai cancellato — l'utente decide).

L'operazione è idempotente: se il `.migrated-bak` esiste già, non viene rifatta. Per puntare a un percorso non standard usa `UNIT3DUP_CONFIG=/path/al/Unit3Dbot.json`.

## Problemi comuni

- **`ModuleNotFoundError: No module named 'pymediainfo'`** → `pip install -e .` non è andato a buon fine, riprova.
- **`pymediainfo` installato ma errori di libreria** → manca `libmediainfo`. Installa il pacchetto di sistema.
- **Tutte le operazioni di hardlink falliscono** → filesystem diverso tra media e seedings. Vedi [Troubleshooting](troubleshooting.md).
- **Login 401 senza messaggi a startup** → hash bcrypt mutilato. Apici singoli su `U3DP_PASSWORD_HASH`.
- **Webup ritorna 500 ovunque** → in genere `.env` con valori vuoti o `DOCKER` impostato. Vedi [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup).
