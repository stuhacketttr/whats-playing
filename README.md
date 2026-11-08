# What's Playing

A small Windows app that tells you which track is playing on your PC. It listens to your
system's sound output (no microphone needed), identifies the track, and keeps a history you
can copy from and clean up.

- **Free by default:** identification uses [ShazamIO](https://github.com/shazamio/ShazamIO), no account needed.
- **Optional paid retry:** if ShazamIO can't match a clip, the app offers to retry it with
  [shazam-api.com](https://shazam-api.com/) using your own key. It only does that when you click.
- **BPM and key:** shown for each track, with the key in Camelot notation as well (for example A minor, 8A).
  Published values come from [GetSongBPM](https://getsongbpm.com) when you add a free key; otherwise the app
  estimates them from the audio clip on your PC and marks them "est." (estimates are only a guide).
- **Find on links:** one click opens a Spotify, Bandcamp or SoundCloud search for the track in your browser.
- **Native window:** a normal Windows app, with a scrolling history, tick-box delete, and selectable text.
- **Local only:** no analytics or telemetry. History is saved as a CSV file next to the program.

> **Status:** personal project, Windows 10/11 (64-bit) only. The Spotify "add to favourites" button is a placeholder.

## Install

Download `WhatsPlaying-Setup-<version>.exe` from the **Releases** page and run it. It installs for
your user only (no admin prompt) and adds a Start menu shortcut.

The app window needs the Microsoft Edge WebView2 Runtime. Most Windows 10/11 PCs already have it;
the installer warns you if not.

## Use

1. Play something, then click **Identify now** (it listens for about 10 seconds), or switch on **Continuous**.
2. The match appears in the track box and is added to History.
3. Tick History rows and click **Delete** to remove them (a backup of the CSV is made first).
4. **Help & legal** inside the app covers settings, privacy, terms and credits.

### Optional keys

Open `.env` (next to the program) and set either or both. Never commit or share this file.

- `SHAZAM_API_KEY=...` for the shazam-api.com retry (paid credits, only used when you click).
- `GETSONGBPM_API_KEY=...` for published BPM and key lookups. Get a free key at
  [getsongbpm.com/api](https://getsongbpm.com/api). They require a visible link back to their site (the app
  shows one) and ask private or in-development projects to contact them when registering.

## Build from source

Needs Windows 64-bit and [Python 3.12](https://www.python.org/downloads/).

```bat
run.bat                 :: run from source
build.bat               :: folder build   -> dist\WhatsPlaying\WhatsPlaying.exe
build-onefile.bat       :: single file    -> dist\WhatsPlaying.exe
build-installer.bat     :: installer      -> installer\WhatsPlaying-Setup-<version>.exe  (needs Inno Setup 6.3+)
```

Dependency versions are pinned in `constraints.txt`. If you change dependencies, regenerate
`legal_packages.py` and `THIRD_PARTY_NOTICES.txt` so the credits stay accurate.

## Development

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt
pip install -r requirements-dev.txt
pytest
```

Tests run without an audio device or network (capture, recognisers and GetSongBPM are mocked).
Contributor and AI-assistant notes are in [CLAUDE.md](CLAUDE.md); release steps in [docs/RELEASING.md](docs/RELEASING.md).

## Privacy in brief

- Each identification sends an audio **fingerprint** (not the file) from ShazamIO to Shazam's servers.
- If you add a GetSongBPM key, the artist name and track title (text only) are sent to GetSongBPM.
  Estimating BPM and key from the clip happens entirely on your PC.
- Only if you click the retry button, the **audio clip itself** is uploaded to shazam-api.com.
- The program records everything your PC plays. Don't run it during calls or anything private.
- The author receives no data.

Full details are in the app (Help & legal > Privacy) and `TERMS.txt`.

## Legal

- Released under the [MIT Licence](LICENSE). Copyright (c) 2026 stuhacketttr.
- Third-party software and licences: see [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
- Terms of use, privacy and notices: see [TERMS.txt](TERMS.txt).
- Not affiliated with, endorsed by or sponsored by Apple, Shazam, ShazamIO, shazam-api.com, GetSongBPM,
  Spotify, Bandcamp, SoundCloud, Mixed In Key or Microsoft.
  "Shazam" is a trademark of Apple Inc. ShazamIO is an unofficial, reverse-engineered client and may
  stop working, or conflict with Shazam's terms, at any time. Use it at your own risk.
- Track data, artwork, and tempo and key data belong to their owners. BPM and key data courtesy of
  [GetSongBPM.com](https://getsongbpm.com).

## Issues

Questions and bug reports: use this repository's **Issues** page.
