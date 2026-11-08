"""Legal and help text for What's Playing - the single source for the in-app Help panel,
the installer's terms page (TERMS.txt) and the LICENSE file (see tools/build_legal_files.py).

BEFORE PUBLISHING: set COPYRIGHT_HOLDER and REPO_URL below, then rebuild.
This text is a good-faith starting point and is not legal advice.
"""
from legal_packages import BUILD_TOOLS, GENERATED, PACKAGES  # noqa: F401  (generated file)

APP_NAME = "What's Playing"
APP_VERSION = "1.1.0"
COPYRIGHT_YEAR = "2026"
COPYRIGHT_HOLDER = "stuhacketttr"
REPO_URL = "https://github.com/stuhacketttr/whats-playing"   # no trailing slash; repo not created yet

SHAZAM_API_PRIVACY_URL = "https://shazam-api.com/privacy"
SHAZAM_API_TERMS_URL = "https://shazam-api.com/terms"
APPLE_PRIVACY_URL = "https://www.apple.com/legal/privacy/"
GETSONGBPM_URL = "https://getsongbpm.com"
GETSONGBPM_API_URL = "https://getsongbpm.com/api"


def identity_is_placeholder() -> bool:
    return COPYRIGHT_HOLDER.startswith("[") or not COPYRIGHT_HOLDER.strip()


def _contact() -> str:
    if REPO_URL:
        return f"by opening an issue at {REPO_URL}/issues"
    return "through the project's GitHub Issues page"


def mit_text() -> str:
    return f"""MIT License

Copyright (c) {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def sections() -> list:
    """Help sections. Paragraph markup: '## ' = sub-heading, '- ' = bullet, otherwise plain text."""
    contact = _contact()
    return [
        {
            "id": "about",
            "title": "How to use",
            "paragraphs": [
                f"{APP_NAME} listens to whatever your PC is playing and tells you which track it is. "
                "It records a short clip of your system's sound output (no microphone is used) and "
                "identifies it with ShazamIO, a free Shazam-compatible library.",
                "## Using it",
                "- Play some music, then click Identify now. It listens for about 10 seconds.",
                "- Turn on Continuous to identify tracks automatically as they change.",
                "- Each match appears in the track box and is added to History.",
                "- BPM and key appear beside each match, with the key shown by name and in Camelot notation, "
                "for example A minor (8A). With a free GetSongBPM key in the .env file the app looks up published "
                "values first. If there is no key, or the track isn't listed, it estimates them from the captured "
                "clip and marks them \"est.\". Estimates are only a guide: they are often half or double the real "
                "tempo, or give the relative major or minor key.",
                "- The Find on links open a Spotify, Bandcamp or SoundCloud search for the artist and title in your "
                "browser. They are searches, so check that the result is the right track.",
                "- If ShazamIO can't match a clip, you are offered a retry with shazam-api.com. That uses "
                "paid credits and needs your own key in the .env file, so it only happens if you click.",
                "- Tick one or more History rows and click Delete to remove them from the list and the CSV file.",
                "- Use the audio player beside the buttons to hear the last clip the app captured. It is "
                "handy for checking that the right sound was recorded.",
                "## Where your files are",
                "Everything is saved in the same folder as the program: recognitions.csv (your history, with "
                "automatic .bak.csv backups before any deletion), .env (your settings and API key), "
                "last_clip.wav, retry_clip.wav and whatsplaying.log.",
                "## Settings (.env file)",
                "- SHAZAM_API_KEY: optional key for the shazam-api.com retry.",
                "- GETSONGBPM_API_KEY: optional free key for BPM and key lookups (see getsongbpm.com/api).",
                "- CLIP_SECONDS: how long each clip is (default 10). Try 15 if matches are missed.",
                "- CONTINUOUS_GAP_SECONDS: pause between clips in Continuous mode (default 15).",
                "- SAVE_LAST_CLIP: set to 0 to stop keeping last_clip.wav.",
                "## Troubleshooting",
                "- \"No audio detected\": check that sound is playing through your Windows default output device.",
                "- \"No match\": the track may not be in Shazam's catalogue, or the clip may be too quiet or short. "
                "DJ mixes and remixes are often missed.",
            ],
        },
        {
            "id": "terms",
            "title": "Terms of use",
            "paragraphs": [
                f"These terms apply to your use of {APP_NAME} (version {APP_VERSION}).",
                "## 1. The software",
                f"{APP_NAME} is free software released under the MIT Licence (see Notices). That licence, "
                "not these terms, governs copying, modifying and sharing the code.",
                "## 2. Your use",
                "You use the program at your own risk and you are responsible for what it listens to. It captures "
                "whatever your PC is playing, which could include voices from calls or meetings. Do not use it "
                "where you do not have the right to capture or share that audio, and do not use it to infringe "
                "anyone's copyright or privacy.",
                "## 3. Results",
                "Identification is not guaranteed. A result can be wrong, incomplete or missing. BPM and key "
                "values, whether looked up or estimated, can also be wrong. Do not rely on them where accuracy matters.",
                "## 4. Third-party services",
                "The program relies on services run by other people (see Privacy and Notices). You must follow "
                "their terms. If you add a shazam-api.com or GetSongBPM key, it is your key: keep it secret, and you are "
                "responsible for its use and cost. GetSongBPM's data is provided under its own API terms, which "
                "require a visible link back to getsongbpm.com; the program shows that link whenever it uses their data. Never share a copy of the program or its .env file that "
                "contains your key.",
                "## 5. No warranty and limit of liability",
                "The program is provided \"as is\", without warranty of any kind. To the fullest extent the law "
                "allows, the author is not liable for any loss or damage arising from its use. Nothing in these "
                "terms limits liability that cannot lawfully be limited, including liability for fraud, or for "
                "death or personal injury caused by negligence.",
                "## 6. Changes and governing law",
                "These terms may change in later versions. They are governed by the law of England and Wales.",
                f"Questions: {contact}.",
            ],
        },
        {
            "id": "privacy",
            "title": "Privacy",
            "paragraphs": [
                "This explains what the program stores on your PC and what it sends over the internet.",
                "## Kept on your PC",
                "- History (recognitions.csv): artist, title, album, ISRC code, time, which service matched, "
                "BPM and key (and whether they were looked up or estimated), links, and the web address of the "
                "cover art.",
                "- last_clip.wav: your most recent captured clip, overwritten each time. Set SAVE_LAST_CLIP=0 to disable.",
                "- retry_clip.wav: a clip ShazamIO missed, kept only until you retry, dismiss it, or a track is matched.",
                "- .env: your settings, including any API key. Treat it like a password.",
                "- whatsplaying.log: technical messages from the program.",
                "- Deleting History rows removes them from the list and recognitions.csv, but a .bak.csv backup made "
                "just before still holds them until you delete it.",
                "## No tracking by the author",
                "The program has no analytics or telemetry. The author does not receive your history, audio or any "
                "other data.",
                "## What is sent over the internet",
                "- Every identification: ShazamIO builds an audio fingerprint from the clip on your PC and sends it "
                "to Shazam's servers (run by Apple), together with the usual details any internet request reveals, "
                "such as your IP address.",
                "- Only if you click Try shazam-api.com: the audio clip itself is uploaded to shazam-api.com using "
                "your key. Its privacy policy says uploaded audio is deleted after processing, generally within "
                "an hour, and that it logs request details such as IP address and time.",
                "- Only if you add a GetSongBPM key: the artist name and track title (text only, no audio) are "
                "sent to GetSongBPM, with the usual details such as your IP address, to look up BPM and key. "
                "Estimating BPM and key from the clip happens entirely on your PC.",
                "- Find on links: clicking one opens your default browser at that site's search page, with the "
                "artist and title in the address. That site then sees your visit and its own privacy policy applies.",
                "- Cover art: the window loads images from web addresses supplied by those services, so the image "
                "hosts can see your IP address.",
                "## Take care with sensitive audio",
                "The program records everything your PC plays, so avoid running it during calls, meetings or "
                "anything private, especially if other people's voices could be captured.",
                "## Their policies apply too",
                "Once data reaches those services, their own privacy policies apply, not this one.",
                "## Your choices",
                "Delete History rows in the app, delete the files above, or delete the program's folder to remove "
                "everything. Uninstalling deliberately keeps .env and recognitions.csv so you do not lose them by accident.",
            ],
            "links": [
                {"label": "shazam-api.com privacy policy", "url": SHAZAM_API_PRIVACY_URL},
                {"label": "Apple privacy information", "url": APPLE_PRIVACY_URL},
                {"label": "GetSongBPM website (see its own policy)", "url": GETSONGBPM_URL},
            ],
        },
        {
            "id": "credits",
            "title": "Credits",
            "paragraphs": [
                f"{APP_NAME} is built on the work of many open-source authors. Thank you to all of them. "
                "The tables below list what is bundled in the program and the licence each one uses.",
                "## Services this program talks to",
                "- Shazam music recognition (an Apple service), reached through the independent ShazamIO library.",
                "- shazam-api.com, an independent service, used only when you click retry.",
                "- GetSongBPM (getsongbpm.com), an independent service that publishes tempo and key data, used "
                "when you add a key. BPM and key from GetSongBPM are credited in the track box whenever shown.",
                "- Spotify, Bandcamp and SoundCloud are only linked to, as search pages in your browser.",
                "## Other components",
                "- Python runtime (PSF licence), embedded in the program.",
                "- PyInstaller builds the .exe. Its licence has a Bootloader Exception that allows its bootloader "
                "to be embedded in programs under any licence, so this program is not covered by the GPL.",
                "- certifi (MPL-2.0) supplies certificate data, unmodified.",
                "- Microsoft Edge WebView2 Runtime draws the window. It is not bundled; it is a separate Microsoft "
                "component with its own terms.",
                "- Microsoft Visual C++ runtime libraries may be included, under Microsoft's redistribution terms.",
                "- Inno Setup builds the installer. It is not part of the installed program.",
                "- BPM and key estimates are calculated by code written for this program, using numpy. No "
                "third-party analysis service or model is involved.",
                "- Camelot notation is a naming convention popularised by Mixed In Key.",
                "- No fonts or icons are bundled. The window uses fonts already on your PC.",
            ],
            "links": [
                {"label": "GetSongBPM.com (BPM and key data)", "url": GETSONGBPM_URL},
            ],
        },
        {
            "id": "notices",
            "title": "Notices",
            "paragraphs": [
                f"Copyright (c) {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}. Released under the MIT Licence (text below).",
                "## Not affiliated",
                "Shazam is a trademark of Apple Inc. Spotify, Bandcamp, SoundCloud and Mixed In Key (Camelot) are "
                "trademarks of their owners. ShazamIO is an independent open-source project. shazam-api.com "
                "is an independent service that states it is not affiliated with Apple or Shazam. "
                f"{APP_NAME} is not affiliated with, endorsed by or sponsored by Apple, Shazam, ShazamIO, "
                "shazam-api.com, GetSongBPM, Spotify, Bandcamp, SoundCloud, Mixed In Key, Microsoft or any other company named here. All trademarks belong to their owners "
                "and are used only to identify the services involved.",
                "## Unofficial access",
                "ShazamIO describes itself as a reverse-engineered Shazam API. It is not an official Apple "
                "interface, it may stop working at any time, and its use may not be permitted by Shazam's terms. "
                "You use it at your own risk.",
                "## Music data and artwork",
                "Track titles, artist names, album details, artwork, tempo and key data and links come from "
                "third-party services and belong to their owners. Tempo and key data from GetSongBPM is used under "
                "its API terms, with the credit link they require. The program only displays them. It does not store artwork (only its web "
                "address in your history), does not copy or redistribute music, and gives you no rights in any "
                "music or images.",
                "## Not legal advice",
                "This help text is provided for information and is not legal advice.",
                f"Contact: {contact}.",
            ],
        },
    ]
