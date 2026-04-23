# Deployment › VPS (sudo / Docker)

Guide for a generic Linux VPS with `sudo` privileges: Debian/Ubuntu/Arch/any `systemd`-based distro. If you are on **Ultra.cc** go to the [Ultra.cc guide](deploy-ultracc.md) instead: no sudo and nginx user-proxy.

We cover two scenarios:

1. **Native with systemd + nginx + Let's Encrypt** (recommended — less overhead, more control).
2. **Docker / docker-compose** (if you prefer containers).

---

## 1 — System prerequisites

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    libmediainfo0v5 \
                    nginx git \
                    certbot python3-certbot-nginx
```

Create a dedicated user (do not run services as `root`):

```bash
sudo adduser --system --group --shell /bin/bash --home /opt/unit3dprep unit3dprep
sudo -u unit3dprep -i
```

All subsequent steps run as `unit3dprep` unless stated otherwise.

---

## 2 — Install the application

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install unit3dup              # required uploader on PATH
```

Generate password hash and secret:

```bash
python generate_hash.py
```

Copy the output into an env file systemd will load (step 3).

Create the folders:

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # verify same filesystem
```

---

## 3 — Systemd unit

Create `/etc/systemd/system/unit3dprep.service`:

```ini
[Unit]
Description=unit3dprep web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=unit3dprep
Group=unit3dprep
WorkingDirectory=/opt/unit3dprep/unit3dprep
EnvironmentFile=/opt/unit3dprep/unit3dprep.env
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

Create `/opt/unit3dprep/unit3dprep.env` (mode 600):

```bash
U3DP_PASSWORD_HASH=$2b$12$...
U3DP_SECRET=...
TMDB_API_KEY=...
U3DP_HOST=127.0.0.1
U3DP_PORT=8765
U3DP_HTTPS_ONLY=1
```

```bash
sudo chown unit3dprep:unit3dprep /opt/unit3dprep/unit3dprep.env
sudo chmod 600 /opt/unit3dprep/unit3dprep.env
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now unit3dprep.service
sudo systemctl status unit3dprep.service
journalctl -u unit3dprep.service -f
```

---

## 4 — Nginx reverse proxy + HTTPS

`/etc/nginx/sites-available/unit3dprep.conf`:

```nginx
server {
    listen 80;
    server_name unit3dprep.example.com;

    # Temporary for certbot — it will rewrite this
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
        proxy_set_header   Connection        "";    # needed for SSE / keep-alive
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

## 5 — Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Keep port `8765` closed: the service only listens on `127.0.0.1`.

---

## 6 — Backups

Files to back up periodically (only user `unit3dprep` needs access):

```
/opt/unit3dprep/unit3dprep.env               # secrets
~/Unit3Dup_config/Unit3Dbot.json               # tracker + client config
~/.unit3dprep_db.json                         # upload history
~/.unit3dprep_tmdb_cache.json                 # regeneratable
~/.unit3dprep_lang_cache.json                 # regeneratable
```

Example with `rsync` + cron:

```bash
0 3 * * * rsync -a --delete /opt/unit3dprep/ user@backup:/backups/unit3dprep/
```

---

## 7 — Updates

```bash
sudo -u unit3dprep -i
cd ~/unit3dprep
git pull
source .venv/bin/activate
pip install -e .
exit
sudo systemctl restart unit3dprep.service
```

If you touched the frontend, rebuild it (requires Node):

```bash
cd frontend
npm install
npm run build
```

---

## Docker variant

Minimal `Dockerfile` example (not shipped in the repo — add one if you need it):

```dockerfile
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends libmediainfo0v5 git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e . unit3dup

ENV U3DP_HOST=0.0.0.0 \
    U3DP_PORT=8765

EXPOSE 8765
CMD ["unit3dprep-web"]
```

`docker-compose.yml`:

```yaml
services:
  unit3dprep:
    build: .
    restart: unless-stopped
    ports:
      - "127.0.0.1:8765:8765"
    environment:
      U3DP_PASSWORD_HASH: ${U3DP_PASSWORD_HASH}
      U3DP_SECRET: ${U3DP_SECRET}
      TMDB_API_KEY: ${TMDB_API_KEY}
      U3DP_HTTPS_ONLY: "1"
    volumes:
      - ./media:/root/media:ro
      - ./seedings:/root/seedings
      - ./unit3dup-config:/root/Unit3Dup_config
      - unit3dprep-data:/root

volumes:
  unit3dprep-data:
```

!!! danger "Hardlinks and Docker"
    Hardlinks only work **inside the same volume**. If you mount `media` and `seedings` as separate bind mounts, hardlinks fail. Use **one single volume** containing both subfolders, or bind-mount the host folder that contains both `media/` and `seedings/`.

Proxy in front of Docker: handle TLS with Caddy / Traefik / external nginx pointing to `127.0.0.1:8765`.

---

## Post-deploy checklist

- [ ] `systemctl status unit3dprep.service` → `active (running)`
- [ ] `https://unit3dprep.example.com` responds, login works
- [ ] `journalctl -u unit3dprep-web -f` → no errors
- [ ] `GET /api/settings/fs-check` → `same_fs: true`
- [ ] A test upload completes end-to-end
- [ ] Automatic backup configured
- [ ] `certbot renew --dry-run` → success
