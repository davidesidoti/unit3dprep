---
name: Bug report
about: Report a bug or unexpected behavior in unit3dprep
title: "[Bug]: "
labels: bug
assignees: davidesidoti

---

Thanks for taking the time to file a bug report!

**Before submitting:**
- Check that no [existing issue](https://github.com/davidesidoti/unit3dprep/issues?q=is%3Aissue) already covers this problem
- If you're on an old version, try updating from the UI first (Settings → Version)
- **Always redact** passwords, API keys, bcrypt hashes, and other secrets from logs/config before pasting

---

## Environment

- **unit3dprep version:** <!-- e.g. 0.6.3 — find it in Settings → Version or via `pip show unit3dprep` -->
- **Install mode:** <!-- pip (Ultra.cc) / git editable / other -->
- **Environment:** <!-- Ultra.cc / WSL / native Linux / macOS / native Windows -->
- **Python version:** <!-- output of `python --version` -->
- **Browser (if UI bug):** <!-- e.g. Firefox 123, Chrome 132 -->
- **Device (if UI bug):** <!-- Desktop / Tablet / Mobile (≤768px) -->

## Affected area

<!-- Pick ONE and leave it checked -->

- [ ] Auth / login (bcrypt, sessions)
- [ ] Media Library (scan, categories, season/episode accordion)
- [ ] Upload Wizard
- [ ] Quick Upload
- [ ] unit3dup subprocess (PTY, exit code, log classify)
- [ ] Hardlink / seedings / filesystem check
- [ ] TMDB integration (search, language, poster)
- [ ] Tracker clients (PTT, SIS, Unit3Dbot.json)
- [ ] qBittorrent client (polling, login, seed status)
- [ ] Settings / runtime config (U3DP_*, W_*)
- [ ] Logs tab (filters, SSE, classification)
- [ ] Mobile UI / responsive
- [ ] i18n (IT/EN, missing translations)
- [ ] Update flow (app or unit3dup via UI)
- [ ] systemd service (restart, ExecStart, can_update_app)
- [ ] Build / install (pip, dist-info, venv)
- [ ] Documentation (MkDocs, public site)
- [ ] API (FastAPI endpoint)
- [ ] Frontend (React SPA, routing, localStorage)
- [ ] Other (describe below)

## Bug description

<!-- What happened? -->

## Steps to reproduce

1.
2.
3.

## Expected behavior

<!-- What should have happened? -->

## Relevant logs

<!--
From the Logs tab in the UI, or `journalctl --user -u unit3dprep-web.service -n 200` on Ultra.cc.
REDACT secrets.
-->

```
paste logs here
```

## Browser console (if UI bug)

<!-- F12 → Console tab. Paste red errors. -->

```
paste console errors here
```

## Relevant configuration

<!--
Custom env vars (U3DP_*, W_*), configured trackers, MEDIA_ROOT/SEEDINGS_DIR paths, etc.
DO NOT paste secrets — write [redacted].
-->

```
U3DP_ROOT_PATH=
U3DP_LANG=
MEDIA_ROOT=
SEEDINGS_DIR=
```

## Screenshots / recordings

<!-- Drag images or GIFs here -->

## Additional context

<!-- When did it start? Regression from a previous version? Workarounds found? -->

---

## Checklist

- [ ] I searched existing issues and found no duplicates
- [ ] I redacted passwords, bcrypt hashes, API keys, and other secrets from logs/config
- [ ] I'm on a supported version (latest release or `main` branch)
