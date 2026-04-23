# Installazione

Questa guida copre l'installazione su un sistema Linux/macOS/WSL con Python 3.10+. Per il deploy in produzione vedi [VPS](deploy-vps.md) o [Ultra.cc](deploy-ultracc.md).

## Prerequisiti

| Requisito | Note |
|---|---|
| **Python 3.10+** | 3.11 consigliato. 3.13 funziona ma ha problemi con `_sqlite3` su pyenv — non bloccante perché il progetto usa JSON. |
| **libmediainfo** | Libreria di sistema richiesta da `pymediainfo`. Su Debian/Ubuntu: `sudo apt install libmediainfo0v5`. Su macOS: `brew install mediainfo`. |
| **`unit3dup` nel PATH** | Uploader ufficiale. Installabile con `pip install unit3dup`. |
| **TMDB API key** | Crea un account su <https://www.themoviedb.org/> e richiedi una chiave v3 dalle impostazioni. |
| **Filesystem condiviso** | La sorgente dei media e la cartella `~/seedings/` devono stare sullo **stesso filesystem** per consentire gli hardlink. |
| **Node.js** | *Solo* se vuoi ricompilare il frontend. Il pacchetto include già la build. |

## 1 — Clona e installa

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
pip install -e .
```

L'installazione editabile ti permette di fare `git pull` e ricevere gli aggiornamenti senza reinstallare. Entry points registrati:

- `unit3dprep` → CLI interattiva
- `unit3dprep-web` → server Web UI

## 2 — Genera hash password e secret

```bash
python generate_hash.py
```

Ti chiede una password (doppia conferma) e stampa le righe da esportare:

```bash
export U3DP_PASSWORD_HASH="$2b$12$..."
export U3DP_SECRET="..."
export TMDB_API_KEY="<la_tua_chiave_tmdb>"
export U3DP_PORT="8765"
export U3DP_HTTPS_ONLY="1"
```

Copiale in `~/.bashrc` (o `~/.profile` / `~/.zshrc`) e ricarica con `source ~/.bashrc`.

!!! warning "Secret obbligatori"
    Senza `U3DP_PASSWORD_HASH` e `U3DP_SECRET` la Web UI non parte. Il secret firma i cookie di sessione: non condividerlo mai e non committarlo.

## 3 — Prepara le cartelle

Struttura di default attesa:

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

## 4 — (Opzionale) Ricompila il frontend

Il frontend React è pre-buildato in `unit3dprep/web/dist/` e committato nel repo. Ricostruiscilo solo se hai modificato il codice in `frontend/`:

```bash
cd frontend
npm install
npm run build
```

La build popola `unit3dprep/web/dist/`. `MANIFEST.in` include quella cartella nel wheel, quindi chi installa via pip non ha bisogno di Node.

## 5 — Avvia

```bash
unit3dprep-web
```

Apri <http://127.0.0.1:8765>. Login con la password scelta in `generate_hash.py`.

Per la CLI:

```bash
unit3dprep -u /path/al/film.mkv
unit3dprep -f /path/alla/stagione
```

Vedi [Uso › CLI](uso-cli.md) e [Uso › Web UI](uso-web.md).

## Problemi comuni

- **`ModuleNotFoundError: No module named 'pymediainfo'`** → `pip install -e .` non è andato a buon fine, riprova.
- **`pymediainfo` installato ma errori di libreria** → manca `libmediainfo`. Installa il pacchetto di sistema.
- **`unit3dup: command not found`** → non è nel PATH. Verifica con `which unit3dup`; se necessario aggiungi `~/.local/bin` al PATH.
- **Tutte le operazioni di hardlink falliscono** → filesystem diverso tra media e seedings. Vedi [Troubleshooting](troubleshooting.md).
