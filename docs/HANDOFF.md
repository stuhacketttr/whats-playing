# Handoff — What's Playing

Status as of 8 November 2026. Version 1.1.0 (see `legal.APP_VERSION`). Written for Claude Code picking this up from the chat-based build sessions.

## Where it stands
Feature-complete for the owner's brief, tested in a Linux sandbox with mocks, **not yet run end to end on Windows**.

| Area | State |
|---|---|
| Capture (WASAPI loopback via `soundcard`) | Written; verified on Stu's PC in the early versions ("works well") |
| ShazamIO recognition | Verified by Stu (does nearly all matches) |
| shazam-api.com retry | Coded; last real call returned `403 Not enough balance` — Stu needs to top up |
| History, tick-box delete, CSV persistence + migration | Unit/integration tested (mocked) |
| BPM + key (lookup then estimate) | Logic tested; estimator on **synthetic audio only**; GetSongBPM response shape from docs, **never called live** |
| Camelot + key names | Tested against the wheel |
| Find-on links (Spotify/Bandcamp/SoundCloud search URLs) | Tested for URL building; opens via `/api/open_external` |
| Help & legal panel, TERMS, notices | Generated and tested for consistency |
| PyInstaller folder / one-file builds, Inno installer | Scripts written, **never run** |
| Spotify favourites | Deliberately deferred (disabled button) |

Tests: `pytest` → 96 passing at handoff.

## Version history
- v1 browser web app (Flask) — capture, ShazamIO + shazam-api + AcoustID
- v2 native window (pywebview), tick-box delete, CSV delete with backup, Spotify placeholder
- v3 error fixes after a 403 balance message; clearer status
- v4 dropped AcoustID/ACRCloud (ShazamIO did all the work); retry-with-shazam-api prompt; single-scroll layout; match/error inside the track box; selectable text
- v5 single-exe investigation → v6 folder build + Inno Setup installer
- v7 Help & legal panel, MIT, TERMS, privacy, third-party notices, pinned constraints
- v8 Find-on links; BPM + Camelot/key (GetSongBPM then local estimate); CSV migration; GetSongBPM credit
- handoff: tests, CI, release checker, `WHATSPLAYING_HOME`, CRLF, docs

## Decisions already made (don't relitigate without asking Stu)
- Windows only, Python 3.12, native window not browser tab, installer per-user (no admin).
- ShazamIO is the free default; shazam-api.com only on an explicit click; AcoustID/ACRCloud removed.
- Licence MIT; governing law England & Wales; contact = GitHub Issues only.
- BPM/key: published value first (GetSongBPM), local estimate second, always labelled.
- Key shown as name **and** Camelot. History saved in the CSV and shown.
- Spotify favourites deferred.
- Nothing is sent anywhere except: fingerprint → Shazam (ShazamIO); artist+title text → GetSongBPM (if key set); audio clip → shazam-api.com (only on retry click).

## Open decisions for Stu (ask, don't assume)
1. **Ship ShazamIO in a public repo?** It's an unofficial reverse-engineered client; could conflict with Shazam's terms and may break without notice. Options: keep, keep with prominent disclaimer (current), make it an optional extra, or remove.
2. **GitHub presence:** repo only (assumed) or also GitHub Pages site?
3. **Public vs private** at first push. Recommended: create private, run checks, then flip.
4. **GetSongBPM key:** register at getsongbpm.com/api with the repo URL as Website URL and Backlink URL. They ask private/in-development projects to contact them. Stu does the registration himself.
5. Code signing (SmartScreen will warn on unsigned installers).
6. Spotify favourites — when, and he must create a free Spotify developer app.

## Placeholders to fill (Stu supplies the handle)
- `legal.py`: `COPYRIGHT_HOLDER` (his GitHub handle or project name), `REPO_URL`.
- `README.md` Legal section: `[YOUR GITHUB HANDLE]`.
- Then `python tools\build_legal_files.py` and `python tools\check_release_ready.py`.

## Suggested first session with Claude Code
1. Read `CLAUDE.md`, this file. Run `pytest` and `python -W error -m py_compile app.py musicinfo.py legal.py legal_packages.py`.
2. Run `run.bat` on Stu's PC; confirm the window opens and **Identify now** works with music playing. Report anything that differs from this document.
3. Run `build.bat`, launch `dist\WhatsPlaying\WhatsPlaying.exe`, confirm it works frozen (data files next to the exe). Fix PyInstaller hidden-import problems if any.
4. Only then `build-installer.bat` (needs Inno Setup 6.3+), test install/uninstall on the machine.
5. With a GetSongBPM key in `.env`, identify 3–5 known tracks and check the live response parses (`musicinfo._hit_to_info`). Adjust and add a test using the real shape.
6. Ask Stu for the GitHub handle, fill placeholders, regenerate legal files, run the checker.
7. Initialise git, commit locally. **Stop and ask before creating the remote or pushing.**

## Known risks / limits
- Estimators: synthetic only; expect errors on real music, especially half/double-time on 170–180 BPM jungle/DnB and key on atonal/bass-heavy electronica. Plan to tune with real `last_clip.wav` clips Stu supplies (keep them out of git).
- GetSongBPM rate limits unstated; the in-memory cache avoids repeat lookups in a session only.
- pywebview/WebView2: if the window fails to open, `--browser` shows the same UI in a browser tab.
- `soundcard` loopback picks the default speaker; non-default outputs may need selection logic.
- THIRD_PARTY_NOTICES lists PyInstaller (GPL with Bootloader Exception) as a build tool; `proxy_tools` has no licence file in its wheel — noted in the notices.

## Where things are documented
`README.md` (users) · `CLAUDE.md` (agent rules and gotchas) · `docs/RELEASING.md` (release steps) · in-app **Help & legal**.
