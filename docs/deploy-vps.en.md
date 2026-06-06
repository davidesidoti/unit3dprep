# Deployment › VPS (sudo / Docker)

Guide for a generic Linux VPS with `sudo` privileges: Debian/Ubuntu/Arch/any `systemd`-based distro. If you are on **Ultra.cc** go to the [Ultra.cc guide](deploy-ultracc.md) instead: no sudo and nginx user-proxy.

Target architecture: two systemd services sharing the same `.env`.

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

Two scenarios:

1. **Native with systemd + nginx + Let's Encrypt** (recommended — less overhead, more control).
2. **Docker / docker-compose** (if you prefer containers).

---

## 1 — System prerequisites

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    libmediainfo0v5 ffmpeg redis-server \
                    nginx git \
                    certbot python3-certbot-nginx
sudo systemctl enable --now redis-server
```

`ffmpeg` and `redis-server` are required by `Unit3DWebUp`. Redis must stay on `127.0.0.1:6379` (webup hardcodes it; `REDIS_HOST/PORT` env vars are ignored).

Create a dedicated user (do not run services as `root`):

```bash
sudo adduser --system --group --shell /bin/bash --home /opt/unit3dprep unit3dprep
sudo -u unit3dprep -i
```

All subsequent steps run as `unit3dprep` unless stated otherwise.

---

## 2 — Install unit3dprep + Unit3DWebUp

Same venv (simpler to maintain — one `pip install --upgrade` updates both):

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install Unit3DwebUp
```

Or two separate venvs (handy if you want to update the two packages independently):

```bash
python3 -m venv ~/.venvs/unit3dprep && ~/.venvs/unit3dprep/bin/pip install -e ~/unit3dprep
python3 -m venv ~/.venvs/unit3dwebup && ~/.venvs/unit3dwebup/bin/pip install Unit3DwebUp
```

Generate password hash and secret:

```bash
python generate_hash.py
```

Copy the output into an env file systemd will load (step 4).

Create the media folders:

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings ~/.config/unit3dprep
df ~/media ~/seedings   # verify same filesystem
```

---

## 3 — Initial shared `.env`

Bootstrap the shared `.env` with minimal secrets. You'll add tracker/qBit credentials later via the Web UI:

```bash
cat > ~/.config/unit3dprep/.env <<'EOF'
# Auth
U3DP_PASSWORD_HASH='$2b$12$...'
U3DP_SECRET=hex-secret
TMDB_API_KEY=your-tmdb-key

# Web UI
U3DP_HOST=127.0.0.1
U3DP_PORT=8765
U3DP_HTTPS_ONLY=1

# Webup bridge (defaults — change only if needed)
WEBUP_URL=http://127.0.0.1:8000
EOF
chmod 600 ~/.config/unit3dprep/.env
```

!!! danger "Single quotes around `U3DP_PASSWORD_HASH`"
    The bcrypt hash contains `$`. Without single quotes bash expands `$2b`/`$12` as empty variables → mutilated hash → silent 401 login.

---

## 4 — Systemd units (system)

### `unit3dwebup.service`

Create `/etc/systemd/system/unit3dwebup.service`:

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
# DO NOT set DOCKER here — webup's settings.py uses a bare-truthy check.
Environment=PYTHONUNBUFFERED=1
Environment=ENVPATH=/opt/unit3dprep/.config/unit3dprep
ExecStart=/opt/unit3dprep/unit3dprep/.venv/bin/uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `unit3dprep-web.service`

Create `/etc/systemd/system/unit3dprep-web.service`:

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

!!! warning "Never set `DOCKER`"
    Webup `config/settings.py` does `env_file=ENV_FILE if not os.getenv("DOCKER") else None`. That's a bare truthy check on string: `DOCKER=false` → `not "false"` → `False` → `env_file=None` → pydantic-settings ignores the `.env` → every `TRACKER__/PREFS__` field reports "Field required". Only set `DOCKER=true` when you really are in Docker; otherwise omit it.

Enable and start (the `Requires` ordering ensures webup starts first):

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now unit3dwebup.service
sudo systemctl enable --now unit3dprep-web.service
sudo systemctl status unit3dwebup.service unit3dprep-web.service
journalctl -u unit3dprep-web.service -f
```

Bot smoke test:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Must return `{"userPreferences": ...}`.

---

## 5 — Nginx reverse proxy + HTTPS

Only `unit3dprep-web` is publicly exposed. `unit3dwebup` stays on `127.0.0.1:8000`.

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

    # Certificates populated by certbot
    ssl_certificate     /etc/letsencrypt/live/unit3dprep.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/unit3dprep.example.com/privkey.pem;

    # SSE-friendly timeouts and buffering
    proxy_buffering off;
    proxy_read_timeout 1h;

    # Allow large uploads
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

Enable + obtain the certificate:

```bash
sudo ln -s /etc/nginx/sites-available/unit3dprep.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d unit3dprep.example.com
```

!!! note "Subpath vs root"
    The example serves at the domain root. If you want a subpath (e.g. `unit3dprep.example.com/unit3dprep/`), add a trailing slash to `proxy_pass` (`proxy_pass http://127.0.0.1:8765/;`) so nginx **strips** the prefix → leave `U3DP_ROOT_PATH=""`. Or keep nginx non-stripping (no trailing slash) and set `U3DP_ROOT_PATH=/unit3dprep`.

---

## 6 — Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Keep ports `8765` and `8000` closed: services listen only on `127.0.0.1`.

---

## 7 — Initial configuration via Web UI

1. Open `https://unit3dprep.example.com`, log in.
2. Go to **Settings → Trackers** and enter URL/API key/PID for ITT (and PTT/SIS if used).
3. **Torrent client** → host/port/credentials for qBittorrent (or Transmission/rTorrent).
4. **Image hosts** → at least one key (PTSCREENS, IMGBB, IMGFI, etc.) and order the list in `IMAGE_HOST_ORDER`.
5. **Metadata** → confirm `TMDB_APIKEY`, optionally TVDB.
6. Save → each key is written to `$ENVPATH/.env` with canonical naming and propagated to `unit3dwebup` via `POST /setenv` (no restart).

Verify the **Unit3DWebUp** card in Settings: must be green with version and ms latency.

---

## 8 — Backups

Files to back up periodically:

```
~/.config/unit3dprep/.env       # secrets + full config
~/.unit3dprep_db.json           # upload history
~/.unit3dprep_tmdb_cache.json   # regeneratable
~/.unit3dprep_lang_cache.json   # regeneratable
```

Example with `rsync` + cron:

```bash
0 3 * * * rsync -a --delete /opt/unit3dprep/ user@backup:/backups/unit3dprep/
```

---

## 9 — Updates

### Via Web UI (recommended)

In **Settings → Version** click **Install update** on the App card or the Unit3DWebUp card. See [Usage › Web UI](uso-web.md#version-and-auto-update).

### Manual

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

If you touched the frontend, rebuild it (requires Node):

```bash
cd frontend
npm install
npm run build
```

---

## Docker variant

The repo ships a ready-to-use **all-in-one** image (Redis + Unit3DWebUp + unit3dprep in a
single container) with a `Dockerfile` and `docker-compose.yml`. The full guide — clone, hash
generation, external qBittorrent, TLS reverse proxy and troubleshooting — lives on its own
page: **[Deploy › Docker](docker.md)**.

In short:

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
cp config.env.example config.env   # then fill in U3DP_PASSWORD_HASH / U3DP_SECRET / TMDB_API_KEY
docker compose build
docker compose up -d
# open http://127.0.0.1:8765
```

---

## Post-deploy checklist

- [ ] `systemctl status unit3dwebup.service` → `active (running)`
- [ ] `systemctl status unit3dprep-web.service` → `active (running)`
- [ ] `curl -X POST http://127.0.0.1:8000/setting -d '{}' -H 'Content-Type: application/json'` → JSON with `userPreferences`
- [ ] `https://unit3dprep.example.com` responds, login works
- [ ] `journalctl -u unit3dprep-web -u unit3dwebup -f` → no errors
- [ ] Settings → Unit3DWebUp card **green** (online)
- [ ] `GET /api/settings/fs-check` → `same_fs: true`
- [ ] A test upload completes end-to-end (or `U3DP_DRY_RUN_TRACKER=1` for dry-run)
- [ ] Automatic backup configured
- [ ] `certbot renew --dry-run` → success
