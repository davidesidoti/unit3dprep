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

## `unit3dup`

### `unit3dup: command not found`

Non è nel PATH del processo che ha lanciato la CLI/Web. Verifica:

```bash
which unit3dup
```

Se lo trovi ma il service systemd no, aggiungi al file `.service`:

```ini
Environment=PATH=%h/.venvs/unit3dprep/bin:/usr/local/bin:/usr/bin:/bin
```

### Exit code ≠ 0 rimane nello storico

Hai trovato un bug di `unit3dup`? Il codice di uscita viene fedelmente registrato in `U3DP_DB_PATH`. Apri il log dell'upload dal pannello Uploaded della Web UI per l'output completo.

### Record "pending" bloccati

Il record rimane `pending` se l'endpoint non ha chiamato `update_exit_code`. Casi noti:

- `quickupload.py` deve chiamare `await update_exit_code(state["path"], code)` sull'evento `done`.
- `wizard.py` → `wizard_finish` deve chiamare `await update_exit_code(seeding_path, 0)` (lo stato in memoria non basta).

Se succede post-aggiornamento, verifica che queste chiamate esistano ancora nel codice. È un regression marker: mai rimuoverle.

---

## Web UI / FastAPI

### `AssertionError: SessionMiddleware must be installed`

Ordine dei middleware sbagliato. `SessionMiddleware` deve essere aggiunto **dopo** il middleware auth (FastAPI applica i middleware in LIFO → l'ultimo aggiunto è il più esterno). Se auth tenta di leggere `request.session` prima che SessionMiddleware sia installato, crash.

Se lo vedi dopo aver toccato `unit3dprep/web/app.py`, ripristina l'ordine `add_middleware(auth)` **prima** di `add_middleware(SessionMiddleware, ...)`.

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

Su Ultra.cc questo è già consigliato nella [guida nginx](deploy-ultracc.md#6-nginx-user-proxy).

---

## TMDB

### `TMDB API error: 401 Unauthorized`

`TMDB_API_KEY` mancante o errato. Controlla su <https://www.themoviedb.org/settings/api>.

La CLI prompt-a su ogni lancio; la Web UI usa sia `TMDB_API_KEY` sia `TMDB_APIKEY` dentro `Unit3Dbot.json`.

### Ricerca TMDB restituisce zero risultati

Verifica `U3DP_TMDB_LANG`. Se è `it-IT` e il titolo non esiste in italiano, prova `en-US`.

---

## Sviluppo / Windows

### Env var `U3DP_ROOT_PATH=/unit3dprep` si trasforma in un path Windows

MSYS2 / Git Bash su Windows convertono automaticamente le stringhe che iniziano con `/`. Per bypassare:

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  env U3DP_ROOT_PATH=/unit3dprep python -m uvicorn unit3dprep.web.app:app
```

Oppure usa PowerShell (`$env:U3DP_ROOT_PATH = "/unit3dprep"`).

### Build backend fallisce su Python 3.14

Usa `setuptools.build_meta`, non `setuptools.backends.legacy` (già corretto in `pyproject.toml`).

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

Noto. Il progetto **non usa** SQLite proprio per questo motivo: storico + cache sono file JSON. Se vedi errori `_sqlite3 undefined symbol`, provengono da un'altra libreria (es. qualcosa che chiama `sqlite3` per caching). Installa Python 3.11 via pyenv e punta il venv a quello.

---

## Se nulla funziona

1. `journalctl --user -u unit3dprep-web -f` (Ultra.cc) o `journalctl -u unit3dprep-web -f` (VPS).
2. Logs live nella Web UI → pannello Logs.
3. Apri un issue: <https://github.com/davidesidoti/unit3dprep/issues> con:
   - Versione Python (`python3 --version`)
   - Output di `pip show unit3dprep`
   - Variabili d'ambiente rilevanti (senza secret)
   - Ultimi ~50 righe di `journalctl`
   - Output di `GET /api/settings/fs-check`
