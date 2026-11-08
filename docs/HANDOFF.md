# Handoff — What's Playing

Status as of 8 November 2026. Version 1.1.0 (see `legal.APP_VERSION`). Written for Claude Code picking this up from the chat-based build sessions.

## Pick up here (8 November 2026)
**Repo:** `C:\Users\stuha\repos\whats-playing` (the repo root; it used to be nested one folder deeper and was flattened). Remote: `https://github.com/stuhacketttr/whats-playing`, branch `main`, last pushed commit `77fda5f`. Start Claude Code from this folder so the session appears under the repo in the sidebar.

**Done this session**
- Genre and label from Shazam, with a CSV migration (commit `946ba76`).
- `.env` backups and the local handoff files (`START_HERE.md`, the zip) are git-ignored.
- shazam-api.com retry fixed: poll `resultsUrl`, read the `artwork` field, `no_matches` is not an error (`21eafe8`, `77fda5f`). Tests added for both.
- Built the windowed exe and put a "What's Playing" shortcut on the desktop.

**Current quirks**
- The live exe is in `dist-new\WhatsPlaying\` (not `dist\`). `dist\WhatsPlaying` is an empty folder that Windows says is in use by an unknown process; `build.bat` fails on it. Delete the whole `dist` folder after a reboot, then `build.bat` works as normal and the shortcut can point back at `dist\WhatsPlaying`.
- `dist-new/` is **not** in `.gitignore` yet, so it shows as untracked. Add it (or move the build back to `dist\`).
- The exe uses its own `.env` and `recognitions.csv` in its folder, which are copies. History in the exe and in the repo root has diverged. If you rebuild, save those two files first and copy them back.
- `build.bat` ends with `pause`; from a script, pipe an empty line into it.

**Next actions**
1. Try "Try shazam-api.com" on a real missed clip in the rebuilt exe and confirm both the match and no-match paths.
2. Delete `dist` after a reboot, add `dist-new/` to `.gitignore` or rebuild into `dist`, and repoint the shortcut.
3. Decide how to keep one history file (repo copy vs exe copy).
4. Still open from before: GetSongBPM live check, `build-onefile.bat` and `build-installer.bat` (needs Inno Setup), the "Open decisions" below.

## Where it stands
Feature-complete for the owner's brief. Now running on Stu's Windows PC from source and as a PyInstaller build; see "Pick up here" below.

| Area | State |
|---|---|
| Capture (WASAPI loopback via `soundcard`) | Written; verified on Stu's PC in the early versions ("works well") |
| ShazamIO recognition | Verified by Stu (does nearly all matches) |
| shazam-api.com retry | **Fixed 8 Nov 2026, verified live** (one call, real key). The v2 API is asynchronous: POST returns `processing` plus `resultsUrl`, which `rec_shazamapi` now polls. A miss is `status: "no_matches"`, treated as a plain no-match. Credits work. Not yet re-tried from the rebuilt exe |
| History, tick-box delete, CSV persistence + migration | Unit/integration tested (mocked) |
| BPM + key (lookup then estimate) | Logic tested; estimator on **synthetic audio only**; GetSongBPM response shape from docs, **never called live** |
| Camelot + key names | Tested against the wheel |
| Find-on links (Spotify/Bandcamp/SoundCloud search URLs) | Tested for URL building; opens via `/api/open_external` |
| Help & legal panel, TERMS, notices | Generated and tested for consistency |
| PyInstaller folder build | **Built and run on Stu's PC** (no console window, desktop shortcut). One-file build and Inno installer still **never run** |
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
