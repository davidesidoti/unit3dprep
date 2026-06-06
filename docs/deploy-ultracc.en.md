# Deployment › Ultra.cc

Specific guide for **[Ultra.cc](https://ultra.cc)**. Ultra.cc is a managed seedbox: no `sudo`, no Docker, Python from `pyenv` as an unprivileged user, nginx in "user-proxy" mode configured via files in `~/.apps/nginx/proxy.d/`.

The app runs as two **systemd user** services: `unit3dprep-web.service` (Web UI) and `unit3dwebup.service` (upload bot). The final public URL looks like `https://<user>.<host>.usbx.me/unit3dprep`.

Official Ultra.cc references this guide is based on:

- **Assigned ports**: <https://docs.ultra.cc/unofficial-ssh-utilities/assigned-ports-command>
- **Generic software install + nginx user-proxy**: <https://docs.ultra.cc/unofficial-application-installers/generic-software-installation>

---

## 1 — SSH and reserved port

SSH into your Ultra.cc machine. List free ports from your assigned range:

```bash
app-ports free
```

Pick a port **inside your assigned range** (e.g. `45678`) for the Web UI and note it as `U3DP_PORT`. Using ports outside the range violates the Fair Usage Policy.

```bash
app-ports show
```

!!! info "Only one reserved port"
    `Unit3DWebUp` stays on `127.0.0.1:8000` (loopback, not reserved) — webup talks only to the Web UI through localhost, never publicly exposed. Both Redis (`127.0.0.1:6379`) and webup don't require a port reservation.

---

## 2 — Verify Redis

Ultra.cc preinstalls Redis in user mode on `127.0.0.1:6379`. Verify:

```bash
redis-cli ping
```

Expected: `PONG`. If it doesn't answer, contact support.

!!! warning "Redis is not movable"
    Webup hardcodes Redis at `localhost:6379`. The `REDIS_HOST` / `REDIS_PORT` env vars are ignored. No port reservation needed.

---

## 3 — ffmpeg

Verify ffmpeg is available:

```bash
which ffmpeg
ffmpeg -version | head -1
```

If missing, contact support: webup needs it silently to generate screenshots; without it `/scan` returns 0 items.

---

## 4 — Install unit3dprep + Unit3DWebUp

Ultra.cc ships Python via `pyenv`. Verify:

```bash
python3 --version
which python3
```

Default Python on Ultra.cc is often 3.13 in pyenv, with broken `_sqlite3` (`undefined symbol: sqlite3_deserialize`). **Not a problem** for this project: app uses JSON for history, not SQLite. This stack needs **Python 3.12+** anyway (Unit3DWebUp 0.0.25 requires `>=3.12`): install it with `pyenv install 3.12` and `pyenv local 3.12.X`.

Same venv for both packages (simple):

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

Verify both entry points:

```bash
which unit3dprep-web
~/.venvs/unit3dprep/bin/python -c "import unit3dwup.start; print(unit3dwup.start.app)"
```

!!! tip "No `requirements.txt` for webup"
    Webup `0.0.x` no longer ships `requirements.txt`. The integrated auto-update runs `pip install --upgrade Unit3DwebUp` (NOT `pip install -r requirements.txt`).

---

## 5 — Generate secret and prepare `.env`

```bash
python generate_hash.py
```

Create the shared `.env`:

```bash
mkdir -p ~/.config/unit3dprep
cat > ~/.config/unit3dprep/.env <<'EOF'
# Auth
U3DP_PASSWORD_HASH='$2b$12$...'
U3DP_SECRET=hex-secret
TMDB_API_KEY=your-tmdb-key

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

!!! danger "Single quotes around the bcrypt hash"
    The hash contains `$`. Without single quotes bash expands `$2b`/`$12` as empty variables → silent 401 login.

!!! note "Why `U3DP_ROOT_PATH=/unit3dprep`"
    Ultra.cc's nginx **does not strip** the `/unit3dprep` prefix when forwarding to the backend. So the FastAPI app mounts every route *with* that prefix (it reads `U3DP_ROOT_PATH`). With `U3DP_ROOT_PATH=""`, routes won't match and you'll see 404s.

---

## 6 — Prepare media folders

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # same filesystem?
```

On Ultra.cc `$HOME` is typically all on the same device, so no problem. If you use `~/files/` or custom paths, verify.

---

## 7 — Systemd user units

```bash
mkdir -p ~/.config/systemd/user
```

### `unit3dwebup.service`

The template is in the repo: [`deploy/systemd/unit3dwebup.service`](https://github.com/davidesidoti/unit3dprep/blob/main/deploy/systemd/unit3dwebup.service). Adapt to your venv:

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

!!! note "`WEBUP_VENV_BIN` when webup lives in the same venv"
    `WEBUP_VENV_BIN` tells the version lookup (and the auto-update) where to find the `python` with `Unit3DwebUp` installed. Legacy default `~/dev/Unit3DWebUp/.venv/bin` does not exist if you followed this guide (webup in the same venv as unit3dprep). Without this env the "Version → Unit3DWebUp" card shows "Current: -" and the update button is disabled.

!!! warning "Never set `DOCKER`"
    Webup `config/settings.py` does `env_file=ENV_FILE if not os.getenv("DOCKER") else None` (truthy check). `DOCKER=false` (string) → `env_file=None` → webup ignores the `.env` → every request fails with 500 "Field required". Omit it from the unit file.

!!! note "`U3DP_SYSTEMD_UNIT` on Ultra.cc"
    The "Update app" button validates the unit with `systemctl --user cat <unit>`. The default is already `unit3dprep-web.service` — the same name this guide uses — so `can_update_app` works; the unit file above sets it explicitly anyway. Change it only if you rename the unit.

Enable and start (order matters — webup must be up before the app):

```bash
systemctl --user daemon-reload
systemctl --user enable --now unit3dwebup.service
systemctl --user enable --now unit3dprep-web.service
systemctl --user status unit3dwebup.service unit3dprep-web.service
journalctl --user -u unit3dwebup.service -u unit3dprep-web.service -f
```

Bot smoke test:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Response: `{"userPreferences": ...}`.

!!! tip "Linger"
    Ultra.cc auto-enables `loginctl enable-linger`, so services start even without an active SSH session. Verify:
    ```bash
    loginctl show-user $(whoami) | grep -i linger
    ```
    If `Linger=no`, contact support.

---

## 8 — Nginx user-proxy

Create (or edit) `~/.apps/nginx/proxy.d/unit3dprep.conf`:

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

!!! warning "No trailing slash in `proxy_pass`"
    `proxy_pass http://127.0.0.1:45678;` (no trailing slash) → nginx **does not strip** `/unit3dprep` → the app receives it. Pairs with `U3DP_ROOT_PATH=/unit3dprep`. With a trailing slash (`http://127.0.0.1:45678/;`) nginx strips, and you must set `U3DP_ROOT_PATH=""`.

Reload nginx:

```bash
app-nginx restart
```

(or from UCP panel → Nginx → Restart).

---

## 9 — End-to-end verification

Open in your browser:

```
https://<user>.<host>.usbx.me/unit3dprep
```

Log in. If you see 404 or a blank page:

1. `journalctl --user -u unit3dprep-web -f` — server up?
2. `journalctl --user -u unit3dwebup -f` — bot up?
3. `curl -I http://127.0.0.1:45678/unit3dprep/` from the shell — answers 200?
4. `curl -X POST http://127.0.0.1:8000/setting -d '{}' -H 'Content-Type: application/json'` — webup answers JSON?
5. Did you load `~/.apps/nginx/proxy.d/unit3dprep.conf`? Did you run `app-nginx restart`?
6. Does `U3DP_ROOT_PATH` match `proxy_pass`?

---

## 10 — Initial configuration (Web UI)

1. Log in → **Settings → Trackers** → URL/API key/PID for ITT (and PTT/SIS).
2. **Torrent client** → host/port/credentials for qBittorrent (port typically assigned by Ultra.cc in the panel).
3. **Image hosts** → at least one configured key, ordered in `IMAGE_HOST_ORDER`.
4. **Metadata** → confirm `TMDB_APIKEY`.
5. Save → each key is written to `~/.config/unit3dprep/.env` with canonical naming and propagated to `unit3dwebup` via `POST /setenv` (no restart).
6. Check the **Unit3DWebUp** card in Settings: must be green with version and ms latency.

---

## 11 — Test upload

1. Put a `.mkv` with Italian audio in `~/media/movies/<Title>/`.
2. Open the Web UI → Library → select `movies` → the item appears.
3. Click → Upload Wizard → follow the steps.
4. Check History: exit code becomes `0`.
5. The torrent should appear in Queue, seeded by your qBit.

To test the pipeline without polluting the tracker, set `U3DP_DRY_RUN_TRACKER=1` in `.env` and re-run: the wizard skips `/upload` but runs `setenv → scan → maketorrent → seed`.

---

## 12 — Updates

### Via Web UI (recommended)

In **Settings → Version** there are two cards (App + Unit3DWebUp). Click "Install update" → SSE modal with live logs → transient systemd restart → browser reload → changelog popup. See [Usage › Web UI](uso-web.md#version-and-auto-update).

Prerequisites already satisfied by the two `Environment=` lines in the units:

- `U3DP_SYSTEMD_UNIT=unit3dprep-web.service`
- `WEBUP_SYSTEMD_UNIT=unit3dwebup.service`

### Manual

```bash
# App in editable mode (.git present):
cd ~/unit3dprep
git pull --ff-only origin main
~/.venvs/unit3dprep/bin/pip install -e .

# App via pip-from-git (no .git checkout):
~/.venvs/unit3dprep/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/unit3dprep.git@vX.Y.Z"

# Webup (always via PyPI):
~/.venvs/unit3dprep/bin/pip install --upgrade Unit3DwebUp

systemctl --user restart unit3dwebup.service
systemctl --user restart unit3dprep-web.service
```

Frontend: the published package ships the prebuilt `dist/`, no Node needed on Ultra.cc.

!!! note "Orphan `dist-info` cleanup"
    After a package rename or repeated reinstalls, an orphan `<oldname>-<ver>.dist-info` may stay in `site-packages` that `pip uninstall` won't remove ("Can't uninstall — No files were found"). Clean it manually:
    ```bash
    find ~/.venvs ~/.local -name "unit3dprep-*.dist-info" -o -name "itatorrents-*.dist-info"
    rm -rf <each orphan dist-info>
    ```

---

## Ultra.cc-specific troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| 404 on `/unit3dprep` | nginx not reloaded | `app-nginx restart` |
| Blank page, 200 OK | `U3DP_ROOT_PATH` and `proxy_pass` misaligned | No trailing slash → `U3DP_ROOT_PATH=/unit3dprep` |
| Cookie not persisting | missing `U3DP_HTTPS_ONLY=1` or protocol mismatch | Set it and restart |
| Service does not start after logout | linger disabled | `loginctl show-user` / support ticket |
| `OSError: Invalid cross-device link` | `seedings` on a different FS | Move `~/seedings` under `$HOME` |
| Webup `500` everywhere | `DOCKER` env set or `.env` empty values | Remove `DOCKER`; use Settings UI to write the `.env` |
| Version card `Current: -` | `Unit3DwebUp` not installed in the venv read by `WEBUP_VENV_BIN` | `~/.venvs/unit3dprep/bin/pip install Unit3DwebUp` |
| `can_update_app: false` | your systemd unit has a name other than the default `unit3dprep-web.service` | Add `Environment=U3DP_SYSTEMD_UNIT=<unit-name>` to the unit file |
| `status=203/EXEC` on systemctl | path in `ExecStart` does not exist | `ls -la <path>` — verify `which unit3dprep-web` |

See also [general Troubleshooting](troubleshooting.md).
