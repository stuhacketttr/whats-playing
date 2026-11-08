"""What's Playing (desktop) - identify audio playing on this Windows PC.

Captures system audio via WASAPI loopback and identifies it with ShazamIO (free).
If ShazamIO misses, the app offers to retry the same clip with shazam-api.com
(paid credits) - it only does so when you click the button.
Runs in a native window (pywebview). `python app.py --browser` uses your browser instead.
"""
import asyncio
import csv
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import wave
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

import legal  # help text, terms, privacy and third-party credits (see legal.py)
import musicinfo  # BPM and key: GetSongBPM lookup, or an estimate from the clip

FROZEN = getattr(sys, "frozen", False)
# Portable: data, .env and logs live next to the .exe (or next to app.py when run from source).
# WHATSPLAYING_HOME overrides that (the tests use it so they never touch real data).
BASE = Path(os.getenv("WHATSPLAYING_HOME") or (Path(sys.executable).parent if FROZEN else Path(__file__).parent))
BASE.mkdir(parents=True, exist_ok=True)

if FROZEN:  # --noconsole builds have no stdout/stderr; send them to a log file
    _log = open(BASE / "whatsplaying.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = _log

# Bundled read-only files: a one-file .exe unpacks them to a temp folder (sys._MEIPASS).
RES = Path(getattr(sys, "_MEIPASS", BASE))
_env_template = next((p for p in (BASE / ".env.example", RES / ".env.example") if p.exists()), None)
if not (BASE / ".env").exists() and _env_template:
    shutil.copy2(_env_template, BASE / ".env")
load_dotenv(BASE / ".env")

logging.getLogger("werkzeug").setLevel(logging.ERROR)

LOG_FILE = BASE / "recognitions.csv"
FIELDS = ["id", "timestamp", "artist", "title", "album", "isrc", "source", "cover", "links",
          "bpm", "bpm_src", "key", "camelot", "key_src", "genre", "label"]
MUSIC_FIELDS = ("bpm", "bpm_src", "key", "camelot", "key_src")
CLIP_SECONDS = int(os.getenv("CLIP_SECONDS", "10"))
CONTINUOUS_GAP = int(os.getenv("CONTINUOUS_GAP_SECONDS", "15"))
SAMPLE_RATE = 44100
SILENCE_PEAK = 0.002
# Playback aid: the most recent captured clip, so you can hear what was recognised.
LAST_CLIP = BASE / "last_clip.wav"
SAVE_LAST_CLIP = os.getenv("SAVE_LAST_CLIP", "1") != "0"
# The clip ShazamIO missed, kept only until you retry, dismiss it, or a track is matched.
RETRY_CLIP = BASE / "retry_clip.wav"
SOURCE_LABEL = {"shazamio": "ShazamIO", "shazamapi": "shazam-api.com"}

app = Flask(__name__)


@app.before_request
def _local_requests_only():
    """Defence against DNS rebinding and cross-site requests: the app is only ever reached as
    127.0.0.1 or localhost, so any other Host header (a rebound attacker domain) is refused, and
    an Origin header, when sent, must be this same local address."""
    host = request.host
    if host.rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
        return Response("Forbidden", status=403)
    origin = request.headers.get("Origin")
    if origin and origin != f"http://{host}":
        return Response("Forbidden", status=403)

state = {
    "status": "idle",   # idle | listening | matching | matched | no_match | silence | error
    "message": "Ready.",
    "clip_id": 0,       # bumps each time a clip is captured and saved
    "peak": None,       # loudness of the last clip, 0-1
    "retry": None,      # {"time": "HH:MM:SS"} while a missed clip can be retried
    "current": None,
    "history": [],      # newest first; every row is also in the CSV
    "continuous": False,
}
state_lock = threading.Lock()   # guards `state`
csv_lock = threading.Lock()     # guards the CSV file; always take csv_lock BEFORE state_lock
busy = threading.Lock()         # one capture at a time
retry_lock = threading.Lock()   # one shazam-api.com retry at a time
loop_thread = None
_backup_done = False


# ---------------------------------------------------------------- capture
def capture_wav(seconds: int, path: str) -> float:
    """Record system output (loopback) to a mono 16-bit WAV. Returns peak level 0-1."""
    import soundcard as sc  # imported lazily so the module loads on any OS

    speaker = sc.default_speaker()
    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
    with mic.recorder(samplerate=SAMPLE_RATE) as rec:
        data = rec.record(numframes=SAMPLE_RATE * seconds)
    mono = data.mean(axis=1) if data.ndim > 1 else data
    peak = float(np.abs(mono).max()) if mono.size else 0.0
    pcm = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return peak


# ------------------------------------------------------------ recognisers
def rec_shazamio(path: str):
    """Free, no key. Unofficial Shazam client (library: shazamio)."""
    from shazamio import Shazam

    async def go():
        sh = Shazam()
        fn = getattr(sh, "recognize", None) or getattr(sh, "recognize_song")
        return await fn(path)

    out = asyncio.run(go())
    t = (out or {}).get("track")
    if not t:
        return None
    album = label = None
    for section in t.get("sections", []):
        for meta in section.get("metadata", []) or []:
            if meta.get("title") == "Album":
                album = meta.get("text")
            elif meta.get("title") == "Label":
                label = meta.get("text")
    images = t.get("images") or {}
    return {
        "title": t.get("title"),
        "artist": t.get("subtitle"),
        "album": album,
        "genre": (t.get("genres") or {}).get("primary"),
        "label": label,
        "cover": images.get("coverarthq") or images.get("coverart"),
        "isrc": t.get("isrc"),
        "links": {"shazam": t.get("url")},
    }


def rec_shazamapi(path: str):
    """shazam-api.com (paid credits, needs SHAZAM_API_KEY). Only used when you click retry."""
    key = os.getenv("SHAZAM_API_KEY")
    if not key:
        raise RuntimeError("SHAZAM_API_KEY is not set in .env")
    field = os.getenv("SHAZAM_API_FILE_FIELD", "file")
    with open(path, "rb") as f:
        r = requests.post(
            "https://shazam-api.com/api/v2/recognize",
            headers={"Authorization": f"Bearer {key}"},
            files={field: ("clip.wav", f, "audio/wav")},
            timeout=60,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    # The API is asynchronous: the POST returns status "processing" plus a resultsUrl to poll.
    results_url = j.get("resultsUrl")
    deadline = time.time() + 45
    while j.get("status") == "processing" and results_url and time.time() < deadline:
        time.sleep(2)
        pr = requests.get(
            "https://shazam-api.com" + results_url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        if pr.status_code >= 400:
            raise RuntimeError(f"HTTP {pr.status_code}: {pr.text[:200]}")
        j = pr.json()
    if j.get("status") == "processing":
        raise RuntimeError("timed out waiting for shazam-api.com to finish")
    if j.get("status") in ("error", "failed", "failure"):
        raise RuntimeError(f"shazam-api.com reported a failure: {str(j)[:200]}")
    results = j.get("results") or []
    if j.get("status") != "success" or not results:
        return None
    x = results[0]
    return {
        "title": x.get("title"),
        "artist": x.get("artist"),
        "album": x.get("album"),
        "genre": x.get("genre"),
        "label": x.get("label"),
        "cover": x.get("artwork") or x.get("cover") or x.get("coverArt") or x.get("image"),
        "isrc": x.get("isrc"),
        "links": x.get("links") or {},
    }


def run_shazamio(path: str):
    """Returns (result, None, None) on a match, else (None, 'no_match'|'error', message)."""
    try:
        res = rec_shazamio(path)
    except Exception as exc:
        return None, "error", f"ShazamIO error: {exc}"
    if res and res.get("title"):
        res["source"] = "shazamio"
        return res, None, None
    return None, "no_match", "ShazamIO found no match."


# ------------------------------------------------------------ persistence
def set_state(**kw):
    with state_lock:
        state.update(kw)


def _to_csv_row(r: dict) -> dict:
    return {
        "id": r["id"], "timestamp": r.get("time", ""), "artist": r.get("artist") or "",
        "title": r.get("title") or "", "album": r.get("album") or "", "isrc": r.get("isrc") or "",
        "source": r.get("source") or "", "cover": r.get("cover") or "",
        "links": json.dumps(r.get("links") or {}),
        "bpm": "" if r.get("bpm") is None else r["bpm"], "bpm_src": r.get("bpm_src") or "",
        "key": r.get("key") or "", "camelot": r.get("camelot") or "", "key_src": r.get("key_src") or "",
        "genre": r.get("genre") or "", "label": r.get("label") or "",
    }


def backup_csv():
    """Copy the CSV aside once per session, before the first time we rewrite it."""
    global _backup_done
    if _backup_done or not LOG_FILE.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(LOG_FILE, LOG_FILE.with_name(f"recognitions.{stamp}.bak.csv"))
    _backup_done = True


def write_all(rows_chronological):
    """Atomically rewrite the CSV. Caller must hold csv_lock."""
    tmp = LOG_FILE.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows_chronological:
            w.writerow(_to_csv_row(r))
    os.replace(tmp, LOG_FILE)


def append_csv(r: dict):
    """Append one row. Caller must hold csv_lock."""
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(_to_csv_row(r))


def load_history():
    """Load the CSV into memory. Old-format files (no id column) are backed up, then upgraded."""
    if not LOG_FILE.exists():
        return
    with csv_lock:
        with open(LOG_FILE, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            raw = list(reader)
        rows = []
        for r in raw:
            try:
                links = json.loads(r.get("links") or "{}")
            except ValueError:
                links = {}
            try:
                bpm = int(float(r.get("bpm"))) if r.get("bpm") else None
            except ValueError:
                bpm = None
            rows.append({
                "bpm": bpm, "bpm_src": r.get("bpm_src") or "", "key": r.get("key") or "",
                "camelot": r.get("camelot") or "", "key_src": r.get("key_src") or "",
                "genre": r.get("genre") or None, "label": r.get("label") or None,
                "id": r.get("id") or uuid.uuid4().hex[:8],
                "time": r.get("timestamp", ""),
                "artist": r.get("artist", ""), "title": r.get("title", ""),
                "album": r.get("album") or None, "isrc": r.get("isrc") or None,
                "source": r.get("source", ""), "cover": r.get("cover") or None,
                "links": links if isinstance(links, dict) else {},
            })
        if fields != FIELDS:
            backup_csv()
            write_all(rows)
        with state_lock:
            state["history"] = list(reversed(rows))


# ------------------------------------------------------------ settings (.env)
ENV_FILE = BASE / ".env"
SETTING_KEYS = {"shazam_api_key": "SHAZAM_API_KEY", "getsongbpm_api_key": "GETSONGBPM_API_KEY"}
_env_backup_done = False
_env_lock = threading.Lock()


def _valid_secret(v: str) -> bool:
    """API keys are single tokens: no spaces, quotes, '#' or line breaks (they would corrupt .env)."""
    return len(v) <= 200 and not any(c.isspace() or c in "\"'#\\" for c in v)


def save_env_values(values: dict):
    """Set (or clear, when empty) KEY=value lines in .env, keeping every other line as it is.
    The file is backed up once per session first, and the running app picks the change up at once."""
    global _env_backup_done
    with _env_lock:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
        if ENV_FILE.exists() and not _env_backup_done:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(ENV_FILE, ENV_FILE.with_name(f".env.{stamp}.bak"))
            _env_backup_done = True
        for key, val in values.items():
            new = f"{key}={val}"
            for i, ln in enumerate(lines):
                if ln.split("=", 1)[0].strip() == key and "=" in ln and not ln.lstrip().startswith("#"):
                    lines[i] = new
                    break
            else:
                lines.append(new)
        tmp = ENV_FILE.with_name(".env.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, ENV_FILE)
        for key, val in values.items():
            if val:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)


def copy_image_to_clipboard(data: bytes):
    """Put an image (any format Windows can decode) on the Windows clipboard via PowerShell,
    so no extra Python package is needed. Raises RuntimeError on failure."""
    import subprocess
    fd, path = tempfile.mkstemp(suffix=".img")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        script = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                  "$i=[System.Drawing.Image]::FromFile($env:WP_IMG);"
                  "$d=New-Object System.Windows.Forms.DataObject;$d.SetImage($i);"
                  "[System.Windows.Forms.Clipboard]::SetDataObject($d,$true);$i.Dispose()")
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", script],
            env={**os.environ, "WP_IMG": path}, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "clipboard error").strip()[:200])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------------------ core
def clear_retry_clip():
    try:
        RETRY_CLIP.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def enrich(res: dict, clip_path) -> list:
    """Add BPM and key to a matched track. Never raises. Returns short notes for the status line."""
    with state_lock:
        latest = state["history"][0] if state["history"] else None
    if latest and latest["title"] == res["title"] and latest["artist"] == res["artist"]:
        for f in MUSIC_FIELDS:           # same track as last time: reuse, no new lookup
            res[f] = latest.get(f)
        return []
    set_state(status="matching", message="Looking up BPM and key...")
    try:
        info, notes = musicinfo.get_music_info(
            res.get("artist") or "", res.get("title") or "", clip_path,
            os.getenv("GETSONGBPM_API_KEY", "").strip())
    except Exception as exc:
        info, notes = {}, [f"BPM and key unavailable: {exc}."]
    for f in MUSIC_FIELDS:
        res[f] = info.get(f) if f == "bpm" else (info.get(f) or "")
    return notes


def commit_result(res: dict, notes=()):
    """Record a successful match: history, CSV, current track, status message."""
    res["id"] = uuid.uuid4().hex[:8]
    res["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with csv_lock:
        with state_lock:
            latest = state["history"][0] if state["history"] else None
            same = bool(latest and latest["title"] == res["title"]
                        and latest["artist"] == res["artist"])
            if same:
                res["id"] = latest["id"]
            else:
                state["history"].insert(0, res)
            state["current"] = res
            state["status"] = "matched"
            state["message"] = " ".join(
                [f"Matched via {SOURCE_LABEL.get(res['source'], res['source'])}."] + list(notes))
            state["retry"] = None
        if not same:
            append_csv(res)
    clear_retry_clip()


def identify_once():
    if not busy.acquire(blocking=False):
        return
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        set_state(status="listening", message=f"Listening for {CLIP_SECONDS}s...")
        peak = capture_wav(CLIP_SECONDS, tmp)
        clip_saved = False
        if SAVE_LAST_CLIP:
            try:
                shutil.copyfile(tmp, LAST_CLIP)
                clip_saved = True
            except OSError:
                pass  # playback aid only; never block recognition
        with state_lock:
            state["peak"] = round(peak, 3)
            if clip_saved:
                state["clip_id"] += 1
        if peak < SILENCE_PEAK:
            set_state(status="silence",
                      message=f"No audio detected on the default output device (level {peak:.3f}).")
            return
        set_state(status="matching", message=f"Matching with ShazamIO... (level {peak:.2f})")
        res, kind, problem = run_shazamio(tmp)
        if not res:
            retry = None
            try:
                shutil.copyfile(tmp, RETRY_CLIP)
                retry = {"time": datetime.now().strftime("%H:%M:%S")}
            except OSError:
                pass
            set_state(status=kind, message=problem, retry=retry)
            return
        commit_result(res, enrich(res, tmp))
    except Exception as exc:
        set_state(status="error", message=f"Error: {exc}")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        busy.release()


def retry_with_shazamapi():
    """User-triggered: send the clip ShazamIO missed to shazam-api.com (one attempt)."""
    if not retry_lock.acquire(blocking=False):
        return
    try:
        if not RETRY_CLIP.exists():
            set_state(status="error", retry=None, message="The missed clip is no longer available.")
            return
        set_state(status="matching", message="Trying shazam-api.com...")
        try:
            res, err = rec_shazamapi(str(RETRY_CLIP)), None
        except Exception as exc:
            res, err = None, str(exc)
        if res and res.get("title"):
            res["source"] = "shazamapi"
            commit_result(res, enrich(res, str(RETRY_CLIP)))
        else:
            msg = "shazam-api.com found no match." if err is None else f"shazam-api.com error: {err}"
            set_state(status="no_match" if err is None else "error", message=msg, retry=None)
            clear_retry_clip()
    finally:
        retry_lock.release()


def continuous_loop():
    while state["continuous"]:
        identify_once()
        for _ in range(CONTINUOUS_GAP):
            if not state["continuous"]:
                break
            time.sleep(1)


# ---------------------------------------------------------------- routes
@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.get("/api/state")
def api_state():
    with state_lock:
        snap = dict(state)
        snap["history"] = list(state["history"])
    snap["shazamapi_ready"] = bool(os.getenv("SHAZAM_API_KEY"))
    return jsonify(snap)


def _find_file(name: str):
    """Locate a bundled/shipped file: next to the program, in the one-file unpack folder, or beside app.py."""
    for d in (BASE, RES, Path(__file__).parent):
        p = d / name
        if p.exists():
            return p
    return None


@app.get("/api/legal")
def api_legal():
    return jsonify(
        app=legal.APP_NAME, version=legal.APP_VERSION, holder=legal.COPYRIGHT_HOLDER,
        generated=legal.GENERATED, sections=legal.sections(), mit_text=legal.mit_text(),
        packages=[dict(name=n, version=v, licence=lic, url=u) for n, v, lic, u in legal.PACKAGES],
        build_tools=[dict(name=n, version=v, licence=lic, url=u) for n, v, lic, u in legal.BUILD_TOOLS],
    )


@app.get("/legal/notices.txt")
def legal_notices():
    p = _find_file("THIRD_PARTY_NOTICES.txt")
    if not p:
        return Response("THIRD_PARTY_NOTICES.txt was not found next to the program.",
                        status=404, mimetype="text/plain")
    return Response(p.read_text(encoding="utf-8"), mimetype="text/plain")


@app.post("/api/open_external")
def api_open_external():
    """Open a link in the user's default browser (the app window itself never navigates away)."""
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(ok=False), 403   # only our own page may ask
    url = str((request.get_json(silent=True) or {}).get("url") or "")
    if not url.startswith(("https://", "http://")):
        return jsonify(ok=False), 400
    webbrowser.open(url)
    return jsonify(ok=True)


@app.get("/api/settings")
def api_settings():
    """Only says whether each key is set, with a masked hint. The key itself is never sent to the page."""
    out = {}
    for field, env in SETTING_KEYS.items():
        v = os.getenv(env, "").strip()
        out[field] = {"set": bool(v), "hint": ("•" * 6 + v[-4:]) if len(v) > 8 else ("•" * 6 if v else "")}
    return jsonify(out)


@app.post("/api/settings")
def api_save_settings():
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(ok=False), 403
    body = request.get_json(silent=True) or {}
    values = {}
    for field, env in SETTING_KEYS.items():
        if field in body:
            v = str(body[field] or "").strip()
            if not _valid_secret(v):
                return jsonify(ok=False, error="Keys can't contain spaces, quotes or # characters."), 400
            values[env] = v
    if values:
        save_env_values(values)
    return api_settings()


@app.post("/api/copy_cover")
def api_copy_cover():
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(ok=False), 403
    tid = (request.get_json(silent=True) or {}).get("id")
    with state_lock:
        rows = ([state["current"]] if state["current"] else []) + state["history"]
    url = next((r.get("cover") for r in rows if r and r.get("id") == tid and r.get("cover")), None)
    if not url or not url.startswith(("https://", "http://")):
        return jsonify(ok=False, error="No album cover for this track."), 404
    try:
        r = requests.get(url, timeout=15, stream=True)
        r.raise_for_status()
        if not r.headers.get("Content-Type", "").startswith("image/"):
            raise RuntimeError("the cover link did not return an image")
        data = r.raw.read(10_000_001, decode_content=True)
        if len(data) > 10_000_000:
            raise RuntimeError("the cover image is too large")
        copy_image_to_clipboard(data)
    except Exception as exc:
        return jsonify(ok=False, error=f"Couldn't copy the cover: {exc}"), 502
    return jsonify(ok=True)


@app.get("/api/last_clip")
def api_last_clip():
    if not LAST_CLIP.exists():
        return Response(status=404)
    resp = Response(LAST_CLIP.read_bytes(), mimetype="audio/wav")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/identify")
def api_identify():
    threading.Thread(target=identify_once, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/retry")
def api_retry():
    if not os.getenv("SHAZAM_API_KEY"):
        set_state(status="error", message="SHAZAM_API_KEY is not set in .env")
        return jsonify(ok=False)
    threading.Thread(target=retry_with_shazamapi, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/dismiss_retry")
def api_dismiss_retry():
    set_state(retry=None)
    clear_retry_clip()
    return jsonify(ok=True)


@app.post("/api/continuous")
def api_continuous():
    global loop_thread
    on = bool((request.get_json(silent=True) or {}).get("on"))
    set_state(continuous=on)
    if on and (loop_thread is None or not loop_thread.is_alive()):
        loop_thread = threading.Thread(target=continuous_loop, daemon=True)
        loop_thread.start()
    return jsonify(ok=True, continuous=on)


@app.post("/api/delete")
def api_delete():
    ids = set((request.get_json(silent=True) or {}).get("ids") or [])
    if not ids:
        return jsonify(ok=True, removed=0)
    with csv_lock:
        with state_lock:
            before = len(state["history"])
            state["history"] = [h for h in state["history"] if h["id"] not in ids]
            removed = before - len(state["history"])
            if state["current"] and state["current"]["id"] in ids:
                state["current"] = None
            chronological = list(reversed(state["history"]))
        if removed:
            backup_csv()
            write_all(chronological)
    return jsonify(ok=True, removed=removed)


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>What's Playing</title>
<style>
:root{color-scheme:dark}
[hidden]{display:none!important}
html,body{height:100%;margin:0}
body{font-family:Segoe UI,system-ui,sans-serif;background:#0f1115;color:#e8eaed;padding:20px;box-sizing:border-box;display:flex;justify-content:center;overflow:hidden}
main{width:100%;max-width:640px;height:100%;display:flex;flex-direction:column;min-height:0}
h1{font-size:20px;font-weight:600;margin:0}
.top{flex:none;display:flex;align-items:center;justify-content:space-between;margin:0 0 14px}
.topbtns{display:flex;gap:8px}
.field{margin:14px 0}
.field label{display:block;font-size:14px;font-weight:600;margin-bottom:4px}
.field input{width:100%;box-sizing:border-box;background:#14171d;color:#e8eaed;border:1px solid #343a48;border-radius:8px;padding:9px 10px;font-size:14px}
.field .note{font-size:12px;color:#889;margin:4px 0 0}
.field .status{font-size:12px;margin:4px 0 0}
.help{position:fixed;inset:0;background:#0f1115;z-index:20;padding:20px;box-sizing:border-box;display:flex;justify-content:center}
.helpin{width:100%;max-width:640px;height:100%;display:flex;flex-direction:column;min-height:0}
.helphead{flex:none;display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
#tabs{flex:none;display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
#helpbody{flex:1;min-height:0;overflow-y:auto;font-size:14px;line-height:1.55;padding-right:8px;user-select:text;-webkit-user-select:text;scrollbar-color:#3a4050 transparent}
#helpbody h3{font-size:15px;margin:18px 0 6px;color:#cfd3dc}
#helpbody p{margin:8px 0}
#helpbody .bul{display:flex;gap:8px;margin:4px 0}
#helpbody .dot{color:#7db4ff;flex:none}
#helpbody a{color:#7db4ff}
#helpbody .note{font-size:12px;color:#889}
.pk{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:6px}
.pk th{text-align:left;color:#9aa;font-weight:600;padding:4px 6px;border-bottom:1px solid #2a2f3a}
.pk td{padding:4px 6px;border-bottom:1px solid #1d212a;vertical-align:top;word-break:break-word}
details.full{margin:14px 0}
details.full summary{cursor:pointer;color:#7db4ff;font-size:13px;user-select:none;-webkit-user-select:none}
details.full pre{white-space:pre-wrap;word-break:break-word;font-size:11px;line-height:1.45;background:#14171d;border:1px solid #2a2f3a;border-radius:8px;padding:12px;margin:8px 0 0}
.card{flex:none;background:#181b22;border:1px solid #2a2f3a;border-radius:12px;padding:18px;display:flex;gap:16px}
.cover{width:120px;height:120px;border-radius:8px;background:#232834;object-fit:cover;flex:none;user-select:none;-webkit-user-select:none}
.cardbody{flex:1;min-width:0}
.title{font-size:22px;font-weight:600;margin:0;word-break:break-word}
.artist{font-size:16px;color:#aab;margin:4px 0;word-break:break-word}
.meta{font-size:13px;color:#889;margin:2px 0}
.title,.artist,.meta,#msg,#hist li div{user-select:text;-webkit-user-select:text;cursor:text}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;background:#2b3a55;color:#9cc2ff;margin-right:6px}
.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:6px}
.actions a{color:#7db4ff;font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px}
.chip{display:inline-flex;align-items:center;gap:6px;background:#20242d;border:1px solid #343a48;border-radius:8px;padding:3px 10px;font-size:14px;font-weight:600;user-select:text;-webkit-user-select:text;cursor:text}
.chip small{font-size:10px;font-weight:600;color:#f2c94c;letter-spacing:.04em;text-transform:uppercase}
.credit{font-size:11px;color:#889;margin:2px 0 4px}
.credit a,.rowlinks a{color:#7db4ff}
.rowlinks{font-size:12px;margin-top:2px}
.rowlinks a{margin-right:10px}
#msg{margin-top:10px;font-size:13px;word-break:break-word}
#msg.muted{color:#9aa}#msg.ok{color:#6fcf97}#msg.warn{color:#f2c94c}#msg.err{color:#ff8a80}
.retry{margin-top:10px;padding:10px 12px;background:#20242d;border:1px solid #343a48;border-radius:8px;font-size:13px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.retry span{flex-basis:100%;user-select:text;-webkit-user-select:text}
.row{flex:none;display:flex;gap:12px;align-items:center;margin:14px 0 10px}
button{background:#3b6fe0;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer;user-select:none;-webkit-user-select:none}
button.alt{background:#2a2f3a}
button.on{background:#1f8f55}
button.danger{background:#c0392b;padding:6px 14px;font-size:13px}
button.small{padding:6px 14px;font-size:13px}
button:disabled{opacity:.45;cursor:not-allowed}
#spot{margin:0;padding:6px 14px;font-size:13px}
.row audio{flex:1;min-width:140px;height:34px}
.hhead{flex:none;display:flex;align-items:center;justify-content:space-between;margin:14px 0 8px;min-height:30px}
h2{font-size:14px;color:#9aa;font-weight:600;margin:0}
#hist{flex:1;min-height:0;overflow-y:auto;list-style:none;padding:0 6px 0 0;margin:0;scrollbar-color:#3a4050 transparent}
#hist li{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid #222733;font-size:14px}
#hist li input{width:16px;height:16px;flex:none;cursor:pointer}
#hist li span{color:#889;font-size:12px}
</style></head><body><main>
<div class="top"><h1>What's Playing</h1><div class="topbtns"><button id="setbtn" class="small alt">Settings</button><button id="helpbtn" class="small alt">Help &amp; legal</button></div></div>
<div class="card">
  <img id="cover" class="cover" alt="">
  <div class="cardbody">
    <div id="info"><p class="meta">Nothing identified yet.</p></div>
    <div id="msg" class="muted"></div>
    <div id="retry" class="retry" hidden>
      <span id="retrytxt"></span>
      <button id="retrygo" class="small">Try shazam-api.com</button>
      <button id="retryno" class="small alt">Dismiss</button>
    </div>
  </div>
</div>
<div class="row">
  <button id="go">Identify now</button>
  <button id="cont" class="alt">Continuous: off</button>
  <audio id="clipaudio" controls preload="none" hidden></audio>
</div>
<div class="hhead"><h2>History</h2><button id="del" class="danger" hidden>Delete</button></div>
<ul id="hist"></ul>
</main>
<div id="help" class="help" hidden><div class="helpin">
  <div class="helphead"><h1>Help &amp; legal</h1><button id="helpclose" class="small alt">Close</button></div>
  <div id="tabs"></div>
  <div id="helpbody"></div>
</div></div>
<div id="settings" class="help" hidden><div class="helpin">
  <div class="helphead"><h1>Settings</h1><button id="setclose" class="small alt">Close</button></div>
  <div id="helpbody">
    <p class="note">Keys are saved in the <code>.env</code> file next to the program (backed up first) and take effect straight away. Treat them like passwords.</p>
    <div class="field"><label for="k_gsb">GetSongBPM API key</label>
      <input id="k_gsb" type="password" autocomplete="off" spellcheck="false">
      <p class="status" id="s_gsb"></p>
      <p class="note">Free. Looks up published BPM and key; without it they are estimated from the audio. <a href="https://getsongbpm.com/api" data-ext="https://getsongbpm.com/api">Get a key</a></p></div>
    <div class="field"><label for="k_shz">shazam-api.com API key (optional)</label>
      <input id="k_shz" type="password" autocomplete="off" spellcheck="false">
      <p class="status" id="s_shz"></p>
      <p class="note">Only used when you click &ldquo;Try shazam-api.com&rdquo; after a missed clip. It uses paid credits.</p></div>
    <div class="row"><button id="setsave">Save</button><span id="setmsg" class="meta"></span></div>
    <p class="note">Leave a box empty to keep the saved key. To remove a key, tick the box below it.</p>
    <p class="note"><label><input type="checkbox" id="c_gsb"> Remove the GetSongBPM key</label><br><label><input type="checkbox" id="c_shz"> Remove the shazam-api.com key</label></p>
  </div>
</div></div>
<script>
const $=id=>document.getElementById(id);
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
const LABEL={shazamio:'ShazamIO',shazamapi:'shazam-api.com'};
const src=s=>LABEL[s]||s;
const CLS={matched:'ok',no_match:'warn',silence:'warn',error:'err'};
const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
let cont=false, sig='', curId=null, clipId=0, msgKey='', retryKey='';
const sel=new Set();
$('go').onclick=()=>post('/api/identify');
$('cont').onclick=()=>post('/api/continuous',{on:!cont});
$('retrygo').onclick=()=>post('/api/retry');
$('retryno').onclick=()=>post('/api/dismiss_retry');
function updDel(){const b=$('del');b.hidden=sel.size===0;b.textContent='Delete ('+sel.size+')';}
$('del').onclick=async()=>{
  const ids=[...sel];
  await post('/api/delete',{ids});
  sel.clear();sig='';updDel();tick();
};
const FEAT=/[\\(\\[]\\s*(feat|ft|with)\\b[^\\)\\]]*[\\)\\]]/ig;
function findLinks(c){
  const q=((c.artist||'')+' '+(c.title||'').replace(FEAT,'')).replace(/\\s+/g,' ').trim(), e=encodeURIComponent(q);
  return [['Spotify','https://open.spotify.com/search/'+e],
          ['Bandcamp','https://bandcamp.com/search?q='+e+'&item_type=t'],
          ['SoundCloud','https://soundcloud.com/search/sounds?q='+e],
          ['Discogs','https://www.discogs.com/search/?q='+e+'&type=release']];
}
function keyText(c){return c.key?c.key+(c.camelot?' ('+c.camelot+')':''):'';}
function bpmText(c){return c.bpm?(c.bpm_src==='estimate'?'~':'')+c.bpm+' BPM':'';}
function bpmKeyBlock(c,into){
  if(!c.bpm&&!c.key)return;
  const chip=(text,from)=>{
    const s=el('span','chip',text);
    if(from==='estimate'){s.append(el('small',null,'est.'));s.title='Estimated from the captured clip. Can be wrong: often half or double the real tempo, or the relative major/minor key.';}
    else if(from==='getsongbpm')s.title='Published value from GetSongBPM.com';
    return s;
  };
  const wrap=el('div','chips');
  if(c.bpm)wrap.append(chip(bpmText(c),c.bpm_src));
  if(c.key)wrap.append(chip(keyText(c),c.key_src));
  into.append(wrap);
  if(c.bpm_src==='getsongbpm'||c.key_src==='getsongbpm'){
    const cr=el('p','credit','BPM and key from ');
    cr.append(extLink('GetSongBPM.com','https://getsongbpm.com'));
    into.append(cr);
  }
}
function renderCurrent(c){
  const info=$('info');
  info.replaceChildren();
  if(!c){info.append(el('p','meta','Nothing identified yet.'));$('cover').removeAttribute('src');return;}
  if(c.cover&&c.cover.startsWith('http'))$('cover').src=c.cover;else $('cover').removeAttribute('src');
  info.append(el('p','title',c.title||''),el('p','artist',c.artist||''));
  bpmKeyBlock(c,info);
  const det=[c.album&&('Album: '+c.album),c.label&&('Label: '+c.label),c.genre&&('Genre: '+c.genre),c.isrc&&('ISRC: '+c.isrc)].filter(Boolean);
  if(det.length)info.append(el('p','meta',det.join(' \\u00b7 ')));
  const b=el('p','meta');b.append(el('span','badge',src(c.source)),document.createTextNode(c.time));info.append(b);
  const act=el('div','actions');
  act.append(el('span','meta','Find on'));
  findLinks(c).forEach(([n,u])=>{const a=extLink(n,u);a.title='Search '+n+' for this track';act.append(a);});
  Object.entries(c.links||{}).forEach(([k,v])=>{if(typeof v==='string'&&v.startsWith('http')){const a=el('a',null,k.charAt(0).toUpperCase()+k.slice(1));a.href=v;a.dataset.ext=v;act.append(a)}});
  if(c.cover&&c.cover.startsWith('http')){
    const cb=el('button','small alt','Copy cover');cb.title='Copy the album cover to the clipboard';
    cb.onclick=async()=>{
      cb.disabled=true;
      try{const r=await post('/api/copy_cover',{id:c.id});const j=await r.json();cb.textContent=j.ok?'Copied ✓':'Copy failed';if(!j.ok)cb.title=j.error||'';}
      catch(e){cb.textContent='Copy failed';}
      setTimeout(()=>{cb.textContent='Copy cover';cb.disabled=false;},2000);
    };
    act.append(cb);
  }
  // Placeholder: Spotify OAuth not implemented yet
  const sp=el('button','alt','\\u2665 Add to Spotify');sp.id='spot';sp.disabled=true;sp.title='Spotify integration coming soon';
  act.append(sp);
  info.append(act);
}
function renderMsg(s){
  const key=s.status+'|'+s.message;
  if(key===msgKey)return;   // only touch the DOM when it changes, so text selection survives
  msgKey=key;
  const m=$('msg'),t=s.message||'';
  m.textContent=t.length>220?t.slice(0,220)+'\\u2026':t;
  m.title=t;
  m.className=CLS[s.status]||'muted';
}
function renderRetry(s){
  const r=s.retry,ready=!!s.shazamapi_ready;
  const key=r?(r.time+'|'+ready):'';
  if(key===retryKey)return;
  retryKey=key;
  $('retry').hidden=!r;
  if(!r)return;
  $('retrytxt').textContent='Missed clip from '+r.time+'. Try shazam-api.com? '+(ready?'(uses paid credits)':'Add a shazam-api.com key in Settings to enable.');
  $('retrygo').disabled=!ready;
}
function renderHistory(history){
  const newSig=history.map(h=>h.id).join(',');
  if(newSig===sig)return;
  sig=newSig;
  const ids=new Set(history.map(h=>h.id));
  [...sel].forEach(i=>{if(!ids.has(i))sel.delete(i)});
  $('hist').replaceChildren(...history.map(h=>{
    const li=document.createElement('li');
    const cb=document.createElement('input');cb.type='checkbox';cb.checked=sel.has(h.id);
    cb.onchange=()=>{cb.checked?sel.add(h.id):sel.delete(h.id);updDel()};
    const t=document.createElement('div');
    const bits=[h.time,src(h.source),bpmText(h),keyText(h)].filter(Boolean);
    const rl=el('div','rowlinks');
    findLinks(h).forEach(([n,u])=>{const a=extLink(n,u);a.title='Search '+n+' for this track';rl.append(a);});
    t.append(el('div',null,(h.artist||'')+' \\u2013 '+(h.title||'')),el('span',null,bits.join(' \\u00b7 ')),rl);
    li.append(cb,t);return li;
  }));
  updDel();
}
function render(s){
  cont=s.continuous;
  $('cont').textContent='Continuous: '+(cont?'on':'off');
  $('cont').className=cont?'on':'alt';
  if(s.clip_id){
    const au=$('clipaudio');
    au.hidden=false;
    au.title='Last captured clip (level '+(s.peak==null?'?':s.peak.toFixed(2))+') - play it to check what was recognised';
    if(s.clip_id!==clipId){clipId=s.clip_id;au.src='/api/last_clip?v='+clipId;}
  }
  const id=s.current?s.current.id:null;
  if(id!==curId){curId=id;renderCurrent(s.current);}
  renderMsg(s);
  renderRetry(s);
  renderHistory(s.history);
}
async function tick(){try{render(await (await fetch('/api/state')).json())}catch(e){}}
// ---- Help & legal panel
let legal=null, helpTab='about';
document.addEventListener('click',e=>{
  const a=e.target.closest('a[data-ext]');
  if(a){e.preventDefault();post('/api/open_external',{url:a.dataset.ext});}
});
function para(p){
  if(p.startsWith('## '))return el('h3',null,p.slice(3));
  if(p.startsWith('- ')){const d=el('div','bul');d.append(el('span','dot','\\u2022'),el('span',null,p.slice(2)));return d;}
  return el('p',null,p);
}
function extLink(label,url){const a=el('a',null,label);a.href=url;a.dataset.ext=url;return a;}
function pkgTable(rows){
  const t=el('table','pk'),hr=el('tr');
  ['Package','Version','Licence'].forEach(h=>hr.append(el('th',null,h)));
  t.append(hr);
  rows.forEach(r=>{const tr=el('tr'),td=el('td');td.append(extLink(r.name,r.url));tr.append(td,el('td',null,r.version),el('td',null,r.licence));t.append(tr);});
  return t;
}
function renderCredits(body){
  body.append(el('h3',null,'Bundled software ('+legal.packages.length+')'),pkgTable(legal.packages));
  body.append(el('h3',null,'Build tools'),pkgTable(legal.build_tools));
  body.append(el('p','note','Versions as of '+legal.generated+'.'));
  const d=el('details','full'),pre=el('pre',null,'');
  d.append(el('summary',null,'Show full licence texts'),pre);
  let loaded=false;
  d.addEventListener('toggle',async()=>{
    if(!d.open||loaded)return;
    loaded=true;pre.textContent='Loading...';
    try{const r=await fetch('/legal/notices.txt');pre.textContent=r.ok?await r.text():'The full licence file (THIRD_PARTY_NOTICES.txt) was not found next to the program.';}
    catch(e){pre.textContent='Could not load the licence file.';}
  });
  body.append(d);
}
function renderNotices(body){
  const d=el('details','full');
  d.append(el('summary',null,'Show the MIT Licence'),el('pre',null,legal.mit_text));
  body.append(d);
}
function showTab(id){
  helpTab=id;
  [...$('tabs').children].forEach(b=>b.className='small '+(b.dataset.id===id?'':'alt'));
  const s=legal.sections.find(x=>x.id===id),body=$('helpbody');
  body.replaceChildren();body.scrollTop=0;
  s.paragraphs.forEach(p=>body.append(para(p)));
  (s.links||[]).forEach(l=>{const d=el('div','bul');d.append(extLink(l.label,l.url));body.append(d);});
  if(id==='credits')renderCredits(body);
  if(id==='notices')renderNotices(body);
}
async function openHelp(){
  $('help').hidden=false;
  if(!legal){
    try{legal=await (await fetch('/api/legal')).json();}catch(e){$('helpbody').textContent='Could not load help.';return;}
    $('tabs').replaceChildren(...legal.sections.map(s=>{const b=el('button','small alt',s.title);b.dataset.id=s.id;b.onclick=()=>showTab(s.id);return b;}));
  }
  showTab(helpTab);
}
$('helpbtn').onclick=openHelp;
// ---- Settings panel
function keyStatus(id,k){const e=$(id);e.textContent=k.set?'Saved ('+k.hint+')':'Not set';e.className='status '+(k.set?'ok':'muted');e.style.color=k.set?'#6fcf97':'#9aa';}
async function openSettings(){
  $('settings').hidden=false;$('setmsg').textContent='';
  ['k_gsb','k_shz'].forEach(i=>$(i).value='');['c_gsb','c_shz'].forEach(i=>$(i).checked=false);
  try{const j=await (await fetch('/api/settings')).json();keyStatus('s_gsb',j.getsongbpm_api_key);keyStatus('s_shz',j.shazam_api_key);}catch(e){$('setmsg').textContent='Could not load settings.';}
}
$('setbtn').onclick=openSettings;
$('setclose').onclick=()=>{$('settings').hidden=true;};
$('setsave').onclick=async()=>{
  const body={};
  const g=$('k_gsb').value.trim(),z=$('k_shz').value.trim();
  if($('c_gsb').checked)body.getsongbpm_api_key='';else if(g)body.getsongbpm_api_key=g;
  if($('c_shz').checked)body.shazam_api_key='';else if(z)body.shazam_api_key=z;
  if(!Object.keys(body).length){$('setmsg').textContent='Nothing to save.';return;}
  try{
    const r=await post('/api/settings',body),j=await r.json();
    if(!r.ok||j.ok===false){$('setmsg').textContent=j.error||'Could not save.';return;}
    keyStatus('s_gsb',j.getsongbpm_api_key);keyStatus('s_shz',j.shazam_api_key);
    ['k_gsb','k_shz'].forEach(i=>$(i).value='');['c_gsb','c_shz'].forEach(i=>$(i).checked=false);
    $('setmsg').textContent='Saved.';retryKey='';tick();
  }catch(e){$('setmsg').textContent='Could not save.';}
};
$('helpclose').onclick=()=>{$('help').hidden=true;};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('help').hidden=true;$('settings').hidden=true;}});

setInterval(tick,1000);tick();
</script></body></html>"""


# ------------------------------------------------------------------ launch
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for(port: int, timeout: float = 8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            return
        except OSError:
            time.sleep(0.1)


def main():
    clear_retry_clip()  # a leftover missed clip from a previous session is no longer offered
    load_history()
    port = int(os.getenv("PORT", "0")) or _free_port()
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False,
                               threaded=True, use_reloader=False),
        daemon=True,
    ).start()
    _wait_for(port)
    url = f"http://127.0.0.1:{port}"
    print(f"Serving {url}")
    if "--browser" in sys.argv:
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        import webview
        webview.create_window("What's Playing", url, width=720, height=780, min_size=(520, 700))
        webview.start()
    state["continuous"] = False


if __name__ == "__main__":
    main()
