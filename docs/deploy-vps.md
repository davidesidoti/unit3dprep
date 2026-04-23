# Deploy › VPS (sudo / Docker)

Guida per VPS Linux generico con privilegi `sudo`: Debian/Ubuntu/Arch/qualsiasi distro con `systemd`. Se sei su **Ultra.cc** vai invece alla [guida Ultra.cc](deploy-ultracc.md): niente sudo e nginx user-proxy.

Copriamo due scenari:

1. **Nativo con systemd + nginx + Let's Encrypt** (consigliato — meno overhead, più controllo).
2. **Docker / docker-compose** (se preferisci container).

---

## 1 — Prerequisiti di sistema

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    libmediainfo0v5 \
                    nginx git \
                    certbot python3-certbot-nginx
```

Crea un utente dedicato (evita di far girare servizi come `root`):

```bash
sudo adduser --system --group --shell /bin/bash --home /opt/unit3dprep unit3dprep
sudo -u unit3dprep -i
```

Tutti i passi successivi come utente `unit3dprep` se non specificato altrimenti.

---

## 2 — Installa l'applicazione

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install unit3dup              # uploader richiesto nel PATH
```

Genera hash password e secret:

```bash
python generate_hash.py
```

Copia l'output in un file env che systemd leggerà (vedi step 3).

Crea le cartelle:

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # verifica stesso filesystem
```

---

## 3 — Systemd unit

Crea `/etc/systemd/system/unit3dprep.service`:

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

Crea `/opt/unit3dprep/unit3dprep.env` (modo 600):

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

Abilita e avvia:

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

    # Certbot temporanea — lascia che certbot gestisca
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
        proxy_set_header   Connection        "";    # needed for SSE / keep-alive
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

## 5 — Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Lascia chiusa la porta `8765`: il servizio ascolta solo su `127.0.0.1`.

---

## 6 — Backup

File da backuppare periodicamente (solo l'utente `unit3dprep` vi accede):

```
/opt/unit3dprep/unit3dprep.env               # secret
~/Unit3Dup_config/Unit3Dbot.json               # config tracker + client
~/.unit3dprep_db.json                         # storico upload
~/.unit3dprep_tmdb_cache.json                 # rigenerabile
~/.unit3dprep_lang_cache.json                 # rigenerabile
```

Esempio con `rsync` + cron:

```bash
0 3 * * * rsync -a --delete /opt/unit3dprep/ user@backup:/backups/unit3dprep/
```

---

## 7 — Aggiornamenti

```bash
sudo -u unit3dprep -i
cd ~/unit3dprep
git pull
source .venv/bin/activate
pip install -e .
exit
sudo systemctl restart unit3dprep.service
```

Se hai toccato il frontend devi ricompilarlo (richiede Node):

```bash
cd frontend
npm install
npm run build
```

---

## Variante Docker

Esempio minimo `Dockerfile` (non incluso nel repo — aggiungilo se ti serve):

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

!!! danger "Hardlink e Docker"
    Gli hardlink funzionano solo **nello stesso volume**. Se monti `media` e `seedings` come bind mount separati, l'hardlink fallisce. Usa **un singolo volume** che contiene entrambe le sottocartelle, oppure monta la stessa cartella host che contiene `media/` e `seedings/`.

Proxy davanti a Docker: gestisci TLS con Caddy / Traefik / nginx esterno che puntano a `127.0.0.1:8765`.

---

## Checklist post-deploy

- [ ] `systemctl status unit3dprep.service` → `active (running)`
- [ ] `https://unit3dprep.example.com` risponde, login funziona
- [ ] `journalctl -u unit3dprep-web -f` → nessun errore
- [ ] `GET /api/settings/fs-check` → `same_fs: true`
- [ ] Un upload di test completa end-to-end
- [ ] Backup automatico configurato
- [ ] `certbot renew --dry-run` → successo
