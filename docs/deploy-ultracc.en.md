# Deployment › Ultra.cc

Specific guide for **[Ultra.cc](https://ultra.cc)**. Ultra.cc is a managed seedbox: no `sudo`, no Docker, Python from `pyenv` as an unprivileged user, nginx in "user-proxy" mode configured via files in `~/.apps/nginx/proxy.d/`.

The app runs as a **systemd user** service (not system). The final public URL looks like `https://<user>.<host>.usbx.me/unit3dprep`.

Official Ultra.cc references this guide is based on:

- **Assigned ports**: <https://docs.ultra.cc/unofficial-ssh-utilities/assigned-ports-command>
- **Generic software install + nginx user-proxy**: <https://docs.ultra.cc/unofficial-application-installers/generic-software-installation>

---

## 1 — SSH and reserved port

SSH into your Ultra.cc machine.

List free ports from your assigned range:

```bash
app-ports free
```

Pick a port **inside your assigned range** (e.g. `45678`) and note it — you will use it as `U3DP_PORT`. Using ports outside the range violates the Fair Usage Policy.

Show ports already allocated to other apps:

```bash
app-ports show
```

---

## 2 — Install the package

Ultra.cc ships Python via `pyenv`. Verify:

```bash
python3 --version
which python3
```

On Ultra.cc the default Python is often 3.13 in pyenv, which has a broken `_sqlite3` (`undefined symbol: sqlite3_deserialize`). **This is not a problem** for this project: the app uses JSON for history, not SQLite. But if you see other tools fail on `import sqlite3`, install Python 3.11 with `pyenv install 3.11` and `pyenv local 3.11.X`.

Clone and install:

```bash
cd ~
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv ~/.venvs/unit3dprep
source ~/.venvs/unit3dprep/bin/activate
pip install -e .
pip install unit3dup
```

Check that `unit3dup` is on PATH:

```bash
which unit3dup
# expected: /home/<user>/.venvs/unit3dprep/bin/unit3dup
```

---

## 3 — Secrets and environment variables

```bash
python generate_hash.py
```

The output already suggests `U3DP_HTTPS_ONLY=1`. Add the lines to `~/.bashrc`:

```bash
# unit3dprep
export U3DP_PASSWORD_HASH="$2b$12$..."
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_HOST="127.0.0.1"
export U3DP_PORT="45678"                 # the port picked via `app-ports free`
export U3DP_ROOT_PATH="/unit3dprep"
export U3DP_HTTPS_ONLY="1"

# optional — if your media live outside ~/media
# export U3DP_MEDIA_ROOT="/home/<user>/files/media"
# export U3DP_SEEDINGS_DIR="/home/<user>/files/seedings"
```

Reload:

```bash
source ~/.bashrc
```

!!! note "Why `U3DP_ROOT_PATH=/unit3dprep`"
    Ultra.cc's nginx **does not strip** the `/unit3dprep` prefix when forwarding to the backend. So the FastAPI app must register every route *with* that prefix (the code does this automatically by reading `U3DP_ROOT_PATH`). If you set `U3DP_ROOT_PATH=""`, routes won't match and you'll see 404s.

---

## 4 — Prepare folders

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # same filesystem?
```

On Ultra.cc `$HOME` is typically all on the same device, so no problem. If you use `~/files/` or custom paths, verify.

---

## 5 — Systemd user unit

Create the folder if missing:

```bash
mkdir -p ~/.config/systemd/user
```

Create `~/.config/systemd/user/unit3dprep.service`:

```ini
[Unit]
Description=unit3dprep web UI
After=network-online.target

[Service]
Type=exec
# %h = user home
EnvironmentFile=%h/.config/unit3dprep.env
ExecStart=%h/.venvs/unit3dprep/bin/unit3dprep-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Move the variables into a dedicated file (so systemd finds them without relying on `~/.bashrc`):

```bash
mkdir -p ~/.config
cat > ~/.config/unit3dprep.env <<'EOF'
U3DP_PASSWORD_HASH=$2b$12$...
U3DP_SECRET=...
TMDB_API_KEY=...
U3DP_HOST=127.0.0.1
U3DP_PORT=45678
U3DP_ROOT_PATH=/unit3dprep
U3DP_HTTPS_ONLY=1
EOF
chmod 600 ~/.config/unit3dprep.env
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now unit3dprep.service
systemctl --user status unit3dprep.service
journalctl --user -u unit3dprep.service -f
```

Verify enable state:

```bash
systemctl --user is-enabled unit3dprep.service
```

!!! tip "Linger"
    Ultra.cc enables `loginctl enable-linger` automatically for users, so the service starts even without an SSH session. If in doubt:
    ```bash
    loginctl show-user $(whoami) | grep -i linger
    ```
    If `Linger=no`, contact support.

!!! note "Renamed the unit?"
    The in-app auto-update ("Update app" button in the Sidebar) runs `systemctl --user restart <unit>` when done. Default is `unit3dprep.service`; if you renamed the unit (e.g. `unit3dprep-web.service`), add to the `[Service]` block:
    ```ini
    Environment=U3DP_SYSTEMD_UNIT=unit3dprep-web.service
    ```
    or save the name via **Settings › App Auto-Update**. Without this, `can_update_app` stays `false` and the button is disabled.

---

## 6 — Nginx user-proxy

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
    `proxy_pass http://127.0.0.1:45678;` (no trailing slash after the port) → nginx **does not strip** `/unit3dprep` → the app receives it. This is the correct pairing with `U3DP_ROOT_PATH=/unit3dprep`. If you add a trailing slash (`http://127.0.0.1:45678/;`) nginx strips and you must set `U3DP_ROOT_PATH=""`.

Reload nginx:

```bash
app-nginx restart
```

(or from the UCP panel → Nginx → Restart).

---

## 7 — Verify

Open in your browser:

```
https://<user>.<host>.usbx.me/unit3dprep
```

You should see the login screen. Enter the password.

If you see a 404 or blank page:

1. `journalctl --user -u unit3dprep-web -f` — is the server up?
2. `curl -I http://127.0.0.1:45678/unit3dprep/` from the shell — does it answer 200?
3. Was `~/.apps/nginx/proxy.d/unit3dprep.conf` loaded? Did you run `app-nginx restart`?
4. Does `U3DP_ROOT_PATH` match `proxy_pass`?

---

## 8 — `unit3dup` configuration

`unit3dup` on Ultra.cc configures via the same `Unit3Dbot.json`. If it does not exist yet, the Web UI creates it on the first Settings save.

Set at least:

- `ITT_URL`, `ITT_APIKEY`, `ITT_PID` (from your ItaTorrents profile)
- `TMDB_APIKEY` (same value as `TMDB_API_KEY`)
- `TORRENT_CLIENT` = `qbittorrent` (typically), `QBIT_HOST=127.0.0.1`, `QBIT_PORT=<your Ultra.cc qBit port>`, `QBIT_USER`, `QBIT_PASS`
- `TAG` = something like `ItaTorrentsBot` (it appears in the final filename)

Or edit by hand:

```bash
nano ~/Unit3Dup_config/Unit3Dbot.json
```

(Ultra.cc may have it at `~/.config/Unit3Dup/` or similar if you installed differently — use `UNIT3DUP_CONFIG` to point explicitly.)

---

## 9 — Test upload

1. Put a `.mkv` file with Italian audio into `~/media/movies/<Title>/`.
2. Open the Web UI → Library → select `movies` → the item appears.
3. Click → Upload Wizard → follow the steps.
4. Check in History that the exit code becomes `0`.
5. In Queue the torrent should appear, seeded by your qBit.

---

## Updates

### Via Web UI (recommended)

When a new GitHub release is available, an "Update available" banner appears at the bottom-left of the Sidebar. Click → modal shows `pip install` live-streamed, followed by an auto-reload countdown, then a post-reload popup with the changelog.

The same button handles `unit3dup` (latest from PyPI). Prerequisites: the user unit must exist and be accessible via `systemctl --user cat`. See the note above if you renamed it.

### Manual

If you prefer the shell (or if in-app update fails):

```bash
# pip-from-git install (no .git checkout)
~/.venvs/unit3dprep/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/unit3dprep.git@vX.Y.Z"
systemctl --user restart unit3dprep.service

# or, if you have a git checkout with .git present
cd ~/unit3dprep
git pull --ff-only origin main
source ~/.venvs/unit3dprep/bin/activate
pip install -e .
systemctl --user restart unit3dprep.service
```

Frontend: the published package ships the pre-built `dist/`, no Node needed on Ultra.cc.

---

## Ultra.cc-specific troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| 404 on `/unit3dprep` | nginx not reloaded | `app-nginx restart` |
| Blank page, 200 OK | `U3DP_ROOT_PATH` and `proxy_pass` misaligned | No trailing slash → `U3DP_ROOT_PATH=/unit3dprep` |
| Cookie not persisting | missing `U3DP_HTTPS_ONLY=1` or protocol mismatch | Set it and restart |
| Service does not start after logout | linger disabled | `loginctl show-user` / support ticket |
| `OSError: Invalid cross-device link` | `seedings` on a different FS | Move `~/seedings` under `$HOME` |
| `unit3dup: command not found` | venv not active for systemd | `which unit3dup` → add it to PATH via `Environment=PATH=%h/.venvs/unit3dprep/bin:/usr/bin` in `.service` |

See also [general Troubleshooting](troubleshooting.md).
