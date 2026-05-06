# Deploy › Ultra.cc

Guida specifica per **[Ultra.cc](https://ultra.cc)**. Ultra.cc è un seedbox managed: niente `sudo`, niente Docker, Python da `pyenv` come utente non privilegiato, nginx in modalità "user-proxy" configurato via file in `~/.apps/nginx/proxy.d/`.

L'app gira come due servizi **systemd user**: `unit3dprep-web.service` (Web UI) e `unit3dwebup.service` (bot upload). L'URL pubblico finale ha la forma `https://<user>.<host>.usbx.me/unit3dprep`.

Link ufficiali Ultra.cc su cui si basa questa guida:

- **Porte assegnate**: <https://docs.ultra.cc/unofficial-ssh-utilities/assigned-ports-command>
- **Generic software install + nginx user-proxy**: <https://docs.ultra.cc/unofficial-application-installers/generic-software-installation>

---

## 1 — SSH e porta riservata

Collegati in SSH alla tua macchina Ultra.cc. Elenca le porte libere del tuo range:

```bash
app-ports free
```

Scegli una porta **all'interno del range assegnato** (es. `45678`) per la Web UI e annotala come `U3DP_PORT`. Usare porte fuori range viola la Fair Usage Policy.

```bash
app-ports show
```

!!! info "Solo una porta riservata"
    `Unit3DWebUp` resta su `127.0.0.1:8000` (loopback non riservato) — webup parla solo con la Web UI tramite localhost, non viene esposto pubblicamente. Sia Redis (`127.0.0.1:6379`) sia webup non richiedono riserva di porta.

---

## 2 — Verifica Redis

Ultra.cc preinstalla Redis in user mode su `127.0.0.1:6379`. Verifica:

```bash
redis-cli ping
```

Risposta attesa: `PONG`. Se non risponde, contatta il supporto.

!!! warning "Redis non spostabile"
    Webup hardcoda Redis a `localhost:6379`. Le env vars `REDIS_HOST` / `REDIS_PORT` sono ignorate. Niente riserva di porta richiesta.

---

## 3 — ffmpeg

Verifica che ffmpeg sia disponibile:

```bash
which ffmpeg
ffmpeg -version | head -1
```

Se manca, contatta il supporto: webup lo richiede silenziosamente per generare gli screenshot, e senza il `/scan` ritorna 0 item.

---

## 4 — Installa unit3dprep + Unit3DWebUp

Ultra.cc ha Python via `pyenv`. Verifica:

```bash
python3 --version
which python3
```

Su Ultra.cc il Python default è spesso 3.13 in pyenv, che ha `_sqlite3` rotto (`undefined symbol: sqlite3_deserialize`). **Non è un problema** per questo progetto: l'app usa storico JSON, non SQLite. Se altri tool ti danno errori `_sqlite3`, installa Python 3.11 con `pyenv install 3.11` e fai `pyenv local 3.11.X`.

Stesso venv per entrambi i pacchetti (semplice):

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv ~/.venvs/unit3dprep
source ~/.venvs/unit3dprep/bin/activate
pip install --upgrade pip
pip install -e .
pip install Unit3DwebUp
```

Verifica entrambi gli entry point:

```bash
which unit3dprep-web
~/.venvs/unit3dprep/bin/python -c "import unit3dwup.start; print(unit3dwup.start.app)"
```

!!! tip "Niente `requirements.txt` per webup"
    Il branch `0.0.x` di `Unit3DWebUp` non distribuisce `requirements.txt`. L'auto-update integrato fa `pip install --upgrade Unit3DwebUp` (NON `pip install -r requirements.txt`).

---

## 5 — Genera secret e prepara `.env`

```bash
python generate_hash.py
```

Crea il `.env` condiviso:

```bash
mkdir -p ~/.config/unit3dprep
cat > ~/.config/unit3dprep/.env <<'EOF'
# Auth
U3DP_PASSWORD_HASH='$2b$12$...'
U3DP_SECRET=hex-secret
TMDB_API_KEY=la-tua-chiave-tmdb

# Web UI
U3DP_HOST=127.0.0.1
U3DP_PORT=45678
U3DP_ROOT_PATH=/unit3dprep
U3DP_HTTPS_ONLY=1

# Bridge
WEBUP_URL=http://127.0.0.1:8000
EOF
chmod 600 ~/.config/unit3dprep/.env
```

!!! danger "Apici singoli sull'hash bcrypt"
    L'hash contiene `$`. Senza apici singoli bash espande `$2b`/`$12` come variabili vuote → login 401 silenzioso.

!!! note "Perché `U3DP_ROOT_PATH=/unit3dprep`"
    L'nginx di Ultra.cc **non** strippa il prefisso `/unit3dprep` quando forwarda al backend. Quindi l'app FastAPI registra le route *con* quel prefisso (lo legge da `U3DP_ROOT_PATH`). Con `U3DP_ROOT_PATH=""` le route non matchano e vedi solo 404.

---

## 6 — Prepara cartelle media

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # stesso filesystem?
```

Su Ultra.cc tipicamente `$HOME` è tutto sullo stesso device, quindi nessun problema. Se usi `~/files/` o path custom, verifica.

---

## 7 — Systemd user units

```bash
mkdir -p ~/.config/systemd/user
```

### `unit3dwebup.service`

Il template è già nel repo: [`deploy/systemd/unit3dwebup.service`](https://github.com/davidesidoti/unit3dprep/blob/main/deploy/systemd/unit3dwebup.service). Adattalo al tuo venv:

```bash
cat > ~/.config/systemd/user/unit3dwebup.service <<'EOF'
[Unit]
Description=Unit3DWebUp FastAPI bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h
# DO NOT set DOCKER here — webup uses a bare truthy check.
Environment=PYTHONUNBUFFERED=1
Environment=ENVPATH=%h/.config/unit3dprep
ExecStart=%h/.venvs/unit3dprep/bin/uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

### `unit3dprep-web.service`

```bash
cat > ~/.config/systemd/user/unit3dprep-web.service <<'EOF'
[Unit]
Description=unit3dprep web UI
After=network-online.target unit3dwebup.service
Wants=network-online.target unit3dwebup.service

[Service]
Type=exec
EnvironmentFile=%h/.config/unit3dprep/.env
Environment=ENVPATH=%h/.config/unit3dprep
Environment=U3DP_SYSTEMD_UNIT=unit3dprep-web.service
Environment=WEBUP_SYSTEMD_UNIT=unit3dwebup.service
Environment=WEBUP_VENV_BIN=%h/.venvs/unit3dprep/bin
ExecStart=%h/.venvs/unit3dprep/bin/unit3dprep-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

!!! note "`WEBUP_VENV_BIN` quando webup vive nello stesso venv"
    `WEBUP_VENV_BIN` dice al lookup versione (e all'auto-update) dove trovare il `python` con `Unit3DwebUp` installato. Default legacy `~/dev/Unit3DWebUp/.venv/bin` non esiste se hai seguito la guida (webup nello stesso venv di unit3dprep). Senza questa env la card "Versione → Unit3DWebUp" mostra "Corrente: -" e il bottone update è disabilitato.

!!! warning "Mai impostare `DOCKER`"
    Webup `config/settings.py` usa `env_file=ENV_FILE if not os.getenv("DOCKER") else None` (truthy check). `DOCKER=false` (stringa) → `env_file=None` → webup ignora il `.env` → ogni richiesta 500 con "Field required". Omettilo dal file unit.

!!! note "`U3DP_SYSTEMD_UNIT=unit3dprep-web.service` è obbligatorio su Ultra.cc"
    Il bottone "Update app" usa `systemctl --user cat <unit>` per validare la unit. Default è `unit3dprep.service`; senza l'override `can_update_app` resta `false` e il bottone è disabilitato.

Abilita e avvia (l'ordine importa — webup deve essere up prima dell'app):

```bash
systemctl --user daemon-reload
systemctl --user enable --now unit3dwebup.service
systemctl --user enable --now unit3dprep-web.service
systemctl --user status unit3dwebup.service unit3dprep-web.service
journalctl --user -u unit3dwebup.service -u unit3dprep-web.service -f
```

Smoke test del bot:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Risposta: `{"userPreferences": ...}`.

!!! tip "Linger"
    Ultra.cc abilita `loginctl enable-linger` automaticamente, quindi i servizi partono anche senza sessione SSH attiva. Verifica:
    ```bash
    loginctl show-user $(whoami) | grep -i linger
    ```
    Se `Linger=no`, contatta il supporto.

---

## 8 — Nginx user-proxy

Crea (o modifica) `~/.apps/nginx/proxy.d/unit3dprep.conf`:

```nginx
location /unit3dprep/ {
    proxy_pass              http://127.0.0.1:45678;
    proxy_http_version      1.1;
    proxy_set_header        Host              $host;
    proxy_set_header        X-Forwarded-Host  $http_host;
    proxy_set_header        X-Forwarded-Proto https;
    proxy_set_header        X-Real-IP         $remote_addr;
    proxy_set_header        Connection        "";
    proxy_buffering         off;
    proxy_read_timeout      1h;
    client_max_body_size    4g;
}
```

!!! warning "Niente slash finale in `proxy_pass`"
    `proxy_pass http://127.0.0.1:45678;` (senza slash finale) → nginx **non strippa** `/unit3dprep` → l'app lo riceve. Abbinato a `U3DP_ROOT_PATH=/unit3dprep`. Con uno slash finale (`http://127.0.0.1:45678/;`) nginx strippa, e devi resettare `U3DP_ROOT_PATH=""`.

Ricarica nginx:

```bash
app-nginx restart
```

(oppure dal pannello UCP → Nginx → Restart).

---

## 9 — Verifica end-to-end

Apri nel browser:

```
https://<user>.<host>.usbx.me/unit3dprep
```

Login con la password. Se vedi 404 o pagina bianca:

1. `journalctl --user -u unit3dprep-web -f` — il server è up?
2. `journalctl --user -u unit3dwebup -f` — il bot è up?
3. `curl -I http://127.0.0.1:45678/unit3dprep/` dalla shell — risponde 200?
4. `curl -X POST http://127.0.0.1:8000/setting -d '{}' -H 'Content-Type: application/json'` — webup risponde JSON?
5. Il file `~/.apps/nginx/proxy.d/unit3dprep.conf` è stato caricato? `app-nginx restart` fatto?
6. `U3DP_ROOT_PATH` combacia tra `.env` e `proxy_pass`?

---

## 10 — Configurazione iniziale (Web UI)

1. Login → **Settings → Tracker** → URL/API key/PID per ITT (e PTT/SIS).
2. **Torrent client** → host/port/credenziali qBittorrent (porta tipicamente assegnata da Ultra.cc nel pannello).
3. **Image host** → almeno una chiave configurata, ordinata in `IMAGE_HOST_ORDER`.
4. **Metadata** → conferma `TMDB_APIKEY`.
5. Save → ogni chiave viene scritta in `~/.config/unit3dprep/.env` con nomenclatura canonica e propagata a `unit3dwebup` via `POST /setenv` (no restart).
6. Verifica la card **Unit3DWebUp** in Settings: deve essere verde con versione e latenza ms.

---

## 11 — Upload di test

1. Metti un `.mkv` con audio italiano in `~/media/movies/<Titolo>/`.
2. Apri la Web UI → Library → seleziona `movies` → l'item appare.
3. Click → Upload Wizard → segui i passi.
4. Verifica nello Storico che l'exit code diventi `0`.
5. In Queue dovrebbe comparire il torrent seedato dal tuo qBit.

Se vuoi testare la pipeline senza polluire il tracker, imposta `U3DP_DRY_RUN_TRACKER=1` in `.env` e ripeti il test: il wizard salta `/upload` ma esegue `setenv → scan → maketorrent → seed`.

---

## 12 — Aggiornamenti

### Via Web UI (consigliato)

In **Settings → Versione** ci sono due card (App + Unit3DWebUp). Click su "Installa aggiornamento" → modal SSE con log live → restart systemd transient → reload del browser → popup changelog. Vedi [Uso › Web UI](uso-web.md#versione-e-auto-update).

Pre-requisiti già garantiti dai due `Environment=` nelle unit:

- `U3DP_SYSTEMD_UNIT=unit3dprep-web.service`
- `WEBUP_SYSTEMD_UNIT=unit3dwebup.service`

### Manuale

```bash
# App in modalità editable (.git presente):
cd ~/unit3dprep
git pull --ff-only origin main
~/.venvs/unit3dprep/bin/pip install -e .

# App via pip-from-git (no checkout .git):
~/.venvs/unit3dprep/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/unit3dprep.git@vX.Y.Z"

# Webup (sempre via PyPI):
~/.venvs/unit3dprep/bin/pip install --upgrade Unit3DwebUp

systemctl --user restart unit3dwebup.service
systemctl --user restart unit3dprep-web.service
```

Frontend: il pacchetto pubblicato include già la `dist/` buildata, no Node su Ultra.cc.

!!! note "Cleanup `dist-info` orfani"
    Dopo rename del pacchetto o reinstall ripetuti può restare un `<oldname>-<ver>.dist-info` orfano in `site-packages` che `pip uninstall` non rimuove ("Can't uninstall — No files were found"). Pulisci a mano:
    ```bash
    find ~/.venvs ~/.local -name "unit3dprep-*.dist-info" -o -name "itatorrents-*.dist-info"
    rm -rf <ogni dist-info orfana>
    ```

---

## Troubleshooting specifico Ultra.cc

| Problema | Causa | Fix |
|---|---|---|
| 404 su `/unit3dprep` | nginx non ricaricato | `app-nginx restart` |
| Pagina bianca, 200 OK | `U3DP_ROOT_PATH` e `proxy_pass` disallineati | Senza slash → `U3DP_ROOT_PATH=/unit3dprep` |
| Cookie non persistenti | mancanza `U3DP_HTTPS_ONLY=1` o mismatch protocollo | Imposta + restart |
| Service non parte dopo logout | linger disabilitato | `loginctl show-user` / ticket supporto |
| `OSError: Invalid cross-device link` | `seedings` su FS diverso | Sposta `~/seedings` sotto `$HOME` |
| Webup `500` dovunque | `DOCKER` env settato o `.env` con valori vuoti | Rimuovi `DOCKER`; usa Settings UI per scrivere il `.env` |
| Card Versione `Corrente: -` | `Unit3DwebUp` non installato nel venv letto da `WEBUP_VENV_BIN` | `~/.venvs/unit3dprep/bin/pip install Unit3DwebUp` |
| `can_update_app: false` | `U3DP_SYSTEMD_UNIT` non override-ato | Aggiungi `Environment=U3DP_SYSTEMD_UNIT=unit3dprep-web.service` al file unit |
| `status=203/EXEC` su systemctl | path in `ExecStart` non esiste | `ls -la <path>` — verifica `which unit3dprep-web` |

Vedi anche [Troubleshooting generale](troubleshooting.md).
