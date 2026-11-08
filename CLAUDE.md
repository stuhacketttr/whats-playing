# CLAUDE.md — What's Playing

Read this first. Then read `docs/HANDOFF.md` (status, decisions, what is and isn't verified). **Start with its "Pick up here" section** for the latest state and next actions.

## What this is
A personal Windows desktop app that identifies the track playing on the PC.
WASAPI loopback capture → ShazamIO (free) → optional manual retry via shazam-api.com (paid, user-clicked) →
enrich with BPM + key (GetSongBPM lookup, else local estimate) → show in a native window → append to a CSV history.
Python 3.12, Windows 10/11 x64 only. Flask on 127.0.0.1 (random port) + pywebview (Edge WebView2) for the window.
Packaged with PyInstaller and an Inno Setup installer. MIT licence.

## Standing rules (from the owner, Stu — apply to everything)
- **Never push, publish, tag, create releases, or change anything external (GitHub settings, API registrations, accounts) without his explicit say-so in the current conversation.** Local commits are fine when asked for.
- **Back up before altering any user data or file that isn't under version control** (e.g. his `.env`, `recognitions.csv`). The app already makes timestamped `.bak.csv` backups; keep that behaviour.
- **Ambiguous or unclear → ask before proceeding. Never infer.** Offer numbered choices where you can.
- Flag uncertain facts with a confidence level and cite sources.
- **UK English** in prose, UI text, comments and docs ("licence" noun, "colour", "initialise").
- **Windows only.** Give Windows commands (PowerShell / cmd), `py -3.12`, backslash paths. No bash-isms in user-facing instructions.
- Be concise and conversational. End substantive replies with one concrete next action.
- Stu is technically literate in paid search and markets, intermediate in ad tech, **beginner with APIs and data pipelines** — explain those steps plainly.

## Commands (Windows, from the repo root)
```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt
pip install -r requirements-dev.txt

run.bat                              :: run the app (add --browser to use a normal browser tab for debugging)
pytest                               :: full suite (~6 s, no audio device or network needed)
python -W error -m py_compile app.py musicinfo.py legal.py legal_packages.py   :: catches JS-escape damage in PAGE
python tools\build_legal_files.py    :: regenerate LICENSE and TERMS.txt from legal.py
python tools\check_release_ready.py  :: pre-publish gate (expected to FAIL until placeholders are filled)
build.bat | build-onefile.bat | build-installer.bat [X.Y.Z]
```
CI (`.github/workflows/tests.yml`) runs compile + pytest on windows-latest, Python 3.12.

## Layout
| File | Role |
|---|---|
| `app.py` | Flask app, capture, recognisers, CSV persistence, `enrich`, routes, the whole UI as the `PAGE` string, pywebview window |
| `musicinfo.py` | Key tables/Camelot, numpy-only BPM and key estimators, GetSongBPM lookup + matching, `get_music_info` |
| `legal.py` | Single source of truth for version, copyright, terms/privacy/credits text (`sections()`), MIT text |
| `legal_packages.py` | GENERATED list of bundled packages (name, version, licence, URL) |
| `tools/build_legal_files.py` | Writes `LICENSE` and `TERMS.txt` from `legal.py` |
| `tools/check_release_ready.py` | Pre-publish gate |
| `installer.iss`, `build*.bat` | Packaging |
| `tests/` | pytest; `synth.py` makes synthetic tracks with known BPM and key |

## Gotchas — do not break these
1. **Lock order:** always take `csv_lock` before `state_lock`. Capture uses the `busy` lock; retry uses `retry_lock`. Reversing the order deadlocks.
2. **`PAGE` is a normal (non-raw) Python triple-quoted string** containing HTML and JS. Every JS backslash must be doubled (`\\s`, `\\u00b7`, `\\(`). A single backslash either mangles the regex or raises a SyntaxError. Always run `python -W error -m py_compile app.py`; `test_embedded_javascript_has_no_python_escape_damage` also guards this. Don't "tidy" it into a raw string without re-checking every escape.
3. **CSV schema** is `id,timestamp,artist,title,album,isrc,source,cover,links,bpm,bpm_src,key,camelot,key_src,genre,label`. Older files are auto-migrated after a timestamped `*.bak.csv`. Deleting rows rewrites atomically. Any schema change needs a migration + a test.
4. **`BASE`** (where `.env`, CSV, clips live) = `WHATSPLAYING_HOME` if set, else the exe's folder when frozen, else the source folder. Tests rely on `WHATSPLAYING_HOME`; never write to the real folder from tests.
5. **`enrich()` must never raise** — a failed BPM/key lookup must not lose a successful match. It reuses the fields if the track equals the latest history row (no repeat API calls).
6. **Link opening** goes through `/api/open_external` (http/https only, same-origin only) so links open in the default browser, not inside the WebView.
7. **`.bat` and `.iss` files must be CRLF** (`.gitattributes` enforces it). LF-only batch files misbehave on Windows.
8. **Pin to Python 3.12 and `constraints.txt`.** Some dependencies (shazamio-core, pythonnet) lack wheels for newer Pythons.
9. **Legal text lives in `legal.py`.** After changing dependencies or versions: update `legal_packages.py`, run `build_legal_files.py`, regenerate `THIRD_PARTY_NOTICES.txt`, run `test_legal.py`.
10. **GetSongBPM requires a visible backlink** to getsongbpm.com wherever their data is shown. Keep the credit link in the UI and README.
11. **Estimator honesty:** BPM/key estimated from audio are labelled "est."/"~" in the UI. Do not present estimates as published values.

## Known limits / unverified (see docs/HANDOFF.md for detail)
- The PyInstaller folder build and the pywebview window now run on Stu's PC. Still unrun: `build-onefile.bat`, the Inno Setup installer.
- GetSongBPM's live JSON shape is coded from its docs; the first real call may need adjusting.
- BPM/key estimator proven on synthetic audio only; real-music accuracy unknown. Half/double-time bias for fast music (jungle/DnB ~170–180).
- ShazamIO is unofficial/reverse-engineered: legal and reliability risk. shazam-api.com is asynchronous (POST, then poll `resultsUrl`); credits work.

## Roadmap (not started unless Stu asks)
Spotify "add to favourites" (button is a disabled placeholder; needs a free Spotify Client ID, PKCE flow) · tune estimators on real clips (Stu to supply `last_clip.wav` files) · code signing · optional GitHub Pages site · auto-update.

## Working agreement for changes
Small, reviewable commits. Run `pytest` and the `py_compile` check before every commit. Add or update a test with each behavioural change. Update `docs/HANDOFF.md` when status or decisions change.
