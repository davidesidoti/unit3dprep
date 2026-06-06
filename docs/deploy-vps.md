# Deploy › VPS (sudo / Docker)

Guida per VPS Linux generico con privilegi `sudo`: Debian/Ubuntu/Arch/qualsiasi distro con `systemd`. Se sei su **Ultra.cc** vai invece alla [guida Ultra.cc](deploy-ultracc.md): niente sudo e nginx user-proxy.

Architettura target: due servizi systemd separati che condividono lo stesso `.env`.

```
unit3dprep-web.service   ─┐                ┌─> tracker (HTTPS)
                          │                │
   (FastAPI + UI)         │  HTTP+WS       │
                          ├──────────────> unit3dwebup.service ─┘
                          │  (port 8000)   │
                          │                ├─> qBittorrent (host:port)
                          │                │
                          │                └─> Redis 127.0.0.1:6379
                          │
                          └── shared .env in $ENVPATH/.env
```

Copriamo due scenari:

1. **Nativo con systemd + nginx + Let's Encrypt** (consigliato — meno overhead, più controllo).
2. **Docker / docker-compose** (se preferisci container).

---

## 1 — Prerequisiti di sistema

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    libmediainfo0v5 ffmpeg redis-server \
                    nginx git \
                    certbot python3-certbot-nginx
sudo systemctl enable --now redis-server
```

`ffmpeg` e `redis-server` sono richiesti da `Unit3DWebUp`. Redis deve restare su `127.0.0.1:6379` (webup hardcoded, le env `REDIS_HOST/PORT` non funzionano).

Crea un utente dedicato (evita di far girare servizi come `root`):

```bash
sudo adduser --system --group --shell /bin/bash --home /opt/unit3dprep unit3dprep
sudo -u unit3dprep -i
```

Tutti i passi successivi come utente `unit3dprep` se non specificato altrimenti.

---

## 2 — Installa unit3dprep + Unit3DWebUp

Stesso venv (più semplice da mantenere — un solo `pip install --upgrade` aggiorna entrambi):

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install Unit3DwebUp
```

In alternativa, due venv separati (utile se vuoi aggiornare i due pacchetti indipendentemente):

```bash
python3 -m venv ~/.venvs/unit3dprep && ~/.venvs/unit3dprep/bin/pip install -e ~/unit3dprep
python3 -m venv ~/.venvs/unit3dwebup && ~/.venvs/unit3dwebup/bin/pip install Unit3DwebUp
```

Genera hash password e secret:

```bash
python generate_hash.py
```

Copia l'output in un file env che systemd leggerà (vedi step 4).

Crea le cartelle dei media:

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings ~/.config/unit3dprep
df ~/media ~/seedings   # verifica stesso filesystem
```

---

## 3 — `.env` condiviso iniziale

Inizializza il `.env` condiviso con i secret minimi. Le credenziali tracker/qBit le aggiungerai dopo dalla Web UI:

```bash
cat > ~/.config/unit3dprep/.env <<'EOF'
# Auth
U3DP_PASSWORD_HASH='$2b$12$...'
U3DP_SECRET=hex-secret
TMDB_API_KEY=la-tua-chiave-tmdb

# Web UI
U3DP_HOST=127.0.0.1
U3DP_PORT=8765
U3DP_HTTPS_ONLY=1

# Bridge webup (default — modifica solo se necessario)
WEBUP_URL=http://127.0.0.1:8000
EOF
chmod 600 ~/.config/unit3dprep/.env
```

!!! danger "Apici singoli su `U3DP_PASSWORD_HASH`"
    L'hash bcrypt contiene `$`. Senza apici singoli bash espande `$2b`/`$12` come variabili vuote → hash mutilato → login 401 silenzioso.

---

## 4 — Systemd unit (sistema)

### `unit3dwebup.service`

Crea `/etc/systemd/system/unit3dwebup.service`:

```ini
[Unit]
Description=Unit3DWebUp FastAPI bot
After=network-online.target redis.service
Wants=network-online.target
Requires=redis.service

[Service]
Type=simple
User=unit3dprep
Group=unit3dprep
WorkingDirectory=/opt/unit3dprep/unit3dprep
# DO NOT set DOCKER here — webup's settings.py uses bare-truthy check.
Environment=PYTHONUNBUFFERED=1
Environment=ENVPATH=/opt/unit3dprep/.config/unit3dprep
ExecStart=/opt/unit3dprep/unit3dprep/.venv/bin/uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `unit3dprep-web.service`

Crea `/etc/systemd/system/unit3dprep-web.service`:

```ini
[Unit]
Description=unit3dprep web UI
After=network-online.target unit3dwebup.service
Wants=network-online.target
Requires=unit3dwebup.service

[Service]
Type=exec
User=unit3dprep
Group=unit3dprep
WorkingDirectory=/opt/unit3dprep/unit3dprep
EnvironmentFile=/opt/unit3dprep/.config/unit3dprep/.env
Environment=ENVPATH=/opt/unit3dprep/.config/unit3dprep
Environment=U3DP_SYSTEMD_UNIT=unit3dprep-web.service
Environment=WEBUP_SYSTEMD_UNIT=unit3dwebup.service
Environment=WEBUP_VENV_BIN=/opt/unit3dprep/unit3dprep/.venv/bin
ExecStart=/opt/unit3dprep/unit3dprep/.venv/bin/unit3dprep-web
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/unit3dprep

[Install]
WantedBy=multi-user.target
```

!!! warning "Mai impostare `DOCKER`"
    Webup `config/settings.py` ha `env_file=ENV_FILE if not os.getenv("DOCKER") else None`. È un truthy check su stringa: `DOCKER=false` → `not "false"` → `False` → `env_file=None` → pydantic-settings ignora il `.env` → ogni campo `TRACKER__/PREFS__` riporta "Field required". Imposta `DOCKER=true` SOLO quando sei davvero in Docker; altrimenti omettilo.

Abilita e avvia (l'ordine `Requires` garantisce che webup parta prima):

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now unit3dwebup.service
sudo systemctl enable --now unit3dprep-web.service
sudo systemctl status unit3dwebup.service unit3dprep-web.service
journalctl -u unit3dprep-web.service -f
```

Smoke test del bot:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Deve rispondere con `{"userPreferences": ...}`.

---

## 5 — Nginx reverse proxy + HTTPS

Solo `unit3dprep-web` viene esposto pubblicamente. `unit3dwebup` resta in `127.0.0.1:8000`.

`/etc/nginx/sites-available/unit3dprep.conf`:

```nginx
server {
    listen 80;
    server_name unit3dprep.example.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name unit3dprep.example.com;

    # Certificati popolati da certbot
    ssl_certificate     /etc/letsencrypt/live/unit3dprep.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/unit3dprep.example.com/privkey.pem;

    # SSE-friendly timeouts e buffering
    proxy_buffering off;
    proxy_read_timeout 1h;

    # Upload grandi consentiti
    client_max_body_size 4g;

    location / {
        proxy_pass         http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Forwarded-Host  $host;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   Connection        "";    # SSE / keep-alive
    }
}
```

Abilita + ottieni il certificato:

```bash
sudo ln -s /etc/nginx/sites-available/unit3dprep.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d unit3dprep.example.com
```

!!! note "Sottopath vs root"
    L'esempio serve sotto la root del dominio. Se vuoi un sottopath (es. `unit3dprep.example.com/unit3dprep/`), aggiungi uno slash al `proxy_pass` (`proxy_pass http://127.0.0.1:8765/;`) così nginx **strippa** il prefisso → lascia `U3DP_ROOT_PATH=""`. Oppure mantieni nginx che non strippa (senza slash finale) e imposta `U3DP_ROOT_PATH=/unit3dprep`.

---

## 6 — Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Lascia chiuse le porte `8765` e `8000`: i servizi ascoltano solo su `127.0.0.1`.

---

## 7 — Configurazione iniziale via Web UI

1. Apri `https://unit3dprep.example.com`, login.
2. Vai in **Settings → Tracker** e inserisci URL/API key/PID per ITT (e PTT/SIS se li usi).
3. **Torrent client** → host/port/credenziali qBittorrent (o Transmission/rTorrent).
4. **Image host** → almeno una chiave (PTSCREENS, IMGBB, IMGFI, ecc.) e ordina la lista in `IMAGE_HOST_ORDER`.
5. **Metadata** → conferma `TMDB_APIKEY`, opzionalmente TVDB.
6. Save → ogni chiave viene scritta in `$ENVPATH/.env` con nomenclatura canonica e propagata a `unit3dwebup` via `POST /setenv` (no restart).

Verifica la card **Unit3DWebUp** in Settings: deve essere verde con versione e latenza ms.

---

## 8 — Backup

File da backuppare periodicamente:

```
~/.config/unit3dprep/.env       # secret + tutta la config
~/.unit3dprep_db.json           # storico upload
~/.unit3dprep_tmdb_cache.json   # rigenerabile
~/.unit3dprep_lang_cache.json   # rigenerabile
```

Esempio con `rsync` + cron:

```bash
0 3 * * * rsync -a --delete /opt/unit3dprep/ user@backup:/backups/unit3dprep/
```

---

## 9 — Aggiornamenti

### Via Web UI (consigliato)

In **Settings → Versione** premi **Installa aggiornamento** sulla card App o sulla card Unit3DWebUp. Vedi [Uso › Web UI](uso-web.md#versione-e-auto-update).

### Manuale

```bash
sudo -u unit3dprep -i
cd ~/unit3dprep
git pull
source .venv/bin/activate
pip install -e .
pip install --upgrade Unit3DwebUp
exit
sudo systemctl restart unit3dwebup.service
sudo systemctl restart unit3dprep-web.service
```

Se hai toccato il frontend, ricompilalo (richiede Node):

```bash
cd frontend
npm install
npm run build
```

---

## Variante Docker

Il repo include un'immagine **all-in-one** pronta all'uso (Redis + Unit3DWebUp + unit3dprep
in un singolo container) con `Dockerfile` e `docker-compose.yml`. La guida completa — clone,
generazione hash, qBittorrent esterno, reverse proxy TLS e troubleshooting — è nella pagina
dedicata: **[Deploy › Docker](docker.md)**.

In sintesi:

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
cp config.env.example config.env   # poi compila U3DP_PASSWORD_HASH / U3DP_SECRET / TMDB_API_KEY
docker compose build
docker compose up -d
# apri http://127.0.0.1:8765
```

---

## Checklist post-deploy

- [ ] `systemctl status unit3dwebup.service` → `active (running)`
- [ ] `systemctl status unit3dprep-web.service` → `active (running)`
- [ ] `curl -X POST http://127.0.0.1:8000/setting -d '{}' -H 'Content-Type: application/json'` → JSON con `userPreferences`
- [ ] `https://unit3dprep.example.com` risponde, login funziona
- [ ] `journalctl -u unit3dprep-web -u unit3dwebup -f` → nessun errore
- [ ] Settings → card Unit3DWebUp **verde** (online)
- [ ] `GET /api/settings/fs-check` → `same_fs: true`
- [ ] Un upload di test completa end-to-end (oppure `U3DP_DRY_RUN_TRACKER=1` per dry-run)
- [ ] Backup automatico configurato
- [ ] `certbot renew --dry-run` → successo
