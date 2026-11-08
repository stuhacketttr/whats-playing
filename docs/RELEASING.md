# Releasing

Nothing here runs automatically. Claude Code must get Stu's explicit go-ahead before any step marked **(external)**.

## One-off before the first public release
1. Set `COPYRIGHT_HOLDER` and `REPO_URL` in `legal.py`; replace `[YOUR GITHUB HANDLE]` in `README.md`.
2. `python tools\build_legal_files.py` (rewrites `LICENSE`, `TERMS.txt`).
3. Decide the ShazamIO question (docs/HANDOFF.md, Open decisions).
4. **(external, Stu does it)** Register for a GetSongBPM key with the repo URL as Website URL and Backlink URL.
5. `python tools\check_release_ready.py` must print `READY TO PUBLISH`.

## Each release
1. Bump the version in **three** places: `legal.py` `APP_VERSION`, `installer.iss` default `MyAppVersion`, `build-installer.bat` default `VERSION`. (The checker verifies they agree.)
2. If dependencies changed: update `constraints.txt`, `legal_packages.py`, regenerate `THIRD_PARTY_NOTICES.txt`.
3. `python tools\build_legal_files.py`
4. `pytest` and `python -W error -m py_compile app.py musicinfo.py legal.py legal_packages.py`
5. `python tools\check_release_ready.py`
6. `build-installer.bat X.Y.Z` → `installer\WhatsPlaying-Setup-X.Y.Z.exe`
7. Test on Windows: install, run, identify a track, delete a row, uninstall (`.env` and CSV are kept on uninstall by design).
8. Commit, then tag: `git tag vX.Y.Z` **(external when pushed)**.
9. Checksum: `certutil -hashfile installer\WhatsPlaying-Setup-X.Y.Z.exe SHA256`
10. **(external)** `git push origin main --tags`, then
    `gh release create vX.Y.Z installer\WhatsPlaying-Setup-X.Y.Z.exe --title "vX.Y.Z" --notes-file notes.md`
    and put the SHA256 in the notes.

## Notes
- The installer is unsigned: Windows SmartScreen will warn ("Windows protected your PC" → More info → Run anyway). Say so in release notes. Code signing is an open decision.
- Never attach `.env`, CSVs or clips. `.gitignore` excludes them; the checker fails if they are tracked.
- Do not commit `dist\`, `build\` or `installer\` output.
