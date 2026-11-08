"""BPM and musical key for a track.

Two sources, tried in this order by get_music_info():
  1. Published values from GetSongBPM (https://getsongbpm.com), looked up by artist and title.
     Needs a free API key (GETSONGBPM_API_KEY); the site requires a visible link back to it.
  2. An estimate made on this PC from the captured audio clip (numpy only, nothing is sent anywhere).

Estimates are rough: the commonest mistakes are half/double tempo and relative major/minor keys.
"""
import difflib
import re
import unicodedata
import wave

import numpy as np
import requests

GETSONGBPM_URL = "https://getsongbpm.com"
API_BASE = "https://api.getsongbpm.com"

# ------------------------------------------------------------------ keys
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def key_info(pc: int, minor: bool) -> dict:
    """pc = tonic pitch class 0-11 (C=0). Returns {'key': 'A minor', 'camelot': '8A'}."""
    pc %= 12
    if minor:
        return {"key": f"{MINOR_NAMES[pc]} minor", "camelot": CAMELOT_MINOR[pc]}
    return {"key": f"{MAJOR_NAMES[pc]} major", "camelot": CAMELOT_MAJOR[pc]}


def parse_key(text):
    """Parse 'C#m', 'A♭', 'Gm', 'F# minor', 'Bb major' ... -> (pitch_class, is_minor) or None."""
    s = (text or "").strip().replace("♯", "#").replace("♭", "b")
    m = re.fullmatch(r"([A-G])([#b]?)\s*([A-Za-z]*)", s)
    if not m:
        return None
    letter, acc, mode = m.groups()
    if mode == "m" or mode.lower() in ("min", "minor"):
        minor = True
    elif mode in ("", "M") or mode.lower() in ("maj", "major"):
        minor = False
    else:
        return None
    pc = _LETTER_PC[letter] + (1 if acc == "#" else -1 if acc == "b" else 0)
    return pc % 12, minor


# --------------------------------------------------- estimate from audio
def read_wav_mono(path: str):
    with wave.open(path, "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("expected 16-bit audio")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def _frames(x, n, hop):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    count = 1 + (len(x) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(count)[:, None]
    return x[idx]


def _tempo_scores(x, sr):
    """Score every tempo from 60 to 200 BPM (0.25 steps) from the clip's rhythm. None if no rhythm."""
    hop, n = 512, 2048
    mag = np.abs(np.fft.rfft(_frames(x, n, hop) * np.hanning(n).astype(np.float32), axis=1))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    band = (freqs >= 30) & (freqs <= 9000)
    flux = np.maximum(0.0, np.diff(np.log1p(mag[:, band] * 10.0), axis=0)).sum(axis=1)   # spectral flux
    env = np.maximum(flux - np.convolve(flux, np.ones(43) / 43, mode="same"), 0.0)      # onset strength
    env = env - env.mean()
    if env.std() < 1e-6:
        return None
    size = len(env)
    spec = np.fft.rfft(env, 2 * size)
    ac = np.fft.irfft(spec * np.conj(spec))[:size]
    ac = ac / (size - np.arange(size))                                                     # unbiased
    ac = ac / (ac[0] if ac[0] > 0 else 1.0)
    fs = sr / hop                                                                          # frames per second
    grid = np.arange(60.0, 200.01, 0.25)
    score = np.zeros_like(grid)
    for k, w in ((1, 1.0), (2, 0.7), (3, 0.5), (4, 0.35)):
        lag = k * 60.0 * fs / grid
        ok = lag < size / 2
        score[ok] += w * np.interp(lag[ok], np.arange(size), ac)
    return grid, score - score.min()


def _pick_tempo(grid, score):
    """Find the strongest tempo, then settle half/double time: favour 160-185 for fast drum music
    (jungle / drum & bass), otherwise the octave nearest typical dance-music tempi."""
    i0 = int(np.argmax(score))
    t0, r0 = float(grid[i0]), float(score[i0])
    family = []
    for j in (-2, -1, 0, 1, 2):
        t = t0 * 2 ** j
        if 65 <= t <= 190:
            k = int(np.argmin(np.abs(grid - t)))
            lo, hi = max(0, k - 4), min(len(grid), k + 5)       # allow +-1 BPM of jitter
            m = lo + int(np.argmax(score[lo:hi]))
            family.append((float(grid[m]), float(score[m])))
    for t, v in sorted(family, reverse=True):
        if 160 <= t <= 185 and v >= 0.45 * r0:
            return int(round(t))
    prior = lambda t: np.exp(-0.5 * (np.log2(t / 125.0) / 0.7) ** 2)
    return int(round(max(family, key=lambda f: f[1] * prior(f[0]))[0]))


def estimate_bpm(x, sr):
    """Tempo estimate (int BPM) or None. Half/double-time mistakes are the usual failure."""
    if len(x) < sr * 4:
        return None
    scored = _tempo_scores(x, sr)
    if scored is None:
        return None
    grid, score = scored
    if float(score.max() - np.median(score)) < 0.3:     # no clear rhythm (noise, a held tone, speech)
        return None
    return _pick_tempo(grid, score)


# Krumhansl-Kessler key profiles
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def estimate_key(x, sr):
    """Key from a pitch-class profile matched against the 24 Krumhansl-Kessler profiles."""
    n, hop = 16384, 8192
    if len(x) < sr * 3:
        return None
    mag = np.abs(np.fft.rfft(_frames(x, n, hop) * np.hanning(n).astype(np.float32), axis=1))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    sel = (freqs >= 60) & (freqs <= 2500)
    m = mag[:, sel]
    f = freqs[sel]
    peak = np.zeros_like(m, dtype=bool)                              # keep spectral peaks only, so
    peak[:, 1:-1] = (m[:, 1:-1] > m[:, :-2]) & (m[:, 1:-1] > m[:, 2:])   # dense high bins don't dominate
    peak &= m > 0.05 * m.max(axis=1, keepdims=True)
    pc = np.round(69 + 12 * np.log2(f / 440.0)).astype(int) % 12
    weight = np.sqrt(m) * peak
    chroma = np.array([weight[:, pc == p].sum() for p in range(12)])
    if chroma.sum() <= 0 or np.ptp(chroma) < 1e-9:
        return None
    scored = []
    for tonic in range(12):
        for minor, prof in ((False, _KK_MAJOR), (True, _KK_MINOR)):
            scored.append((float(np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]), tonic, minor))
    scored.sort(reverse=True)
    r, tonic, minor = scored[0]
    out = key_info(tonic, minor)
    out["confidence"] = round(r, 2)
    return out


def analyse_clip(path: str) -> dict:
    """{'bpm': int|None, 'key': str, 'camelot': str} estimated from a 16-bit WAV file."""
    x, sr = read_wav_mono(path)
    out = {"bpm": None, "key": "", "camelot": ""}
    try:
        out["bpm"] = estimate_bpm(x, sr)
    except Exception:
        pass
    try:
        k = estimate_key(x, sr)
        if k:
            out["key"], out["camelot"] = k["key"], k["camelot"]
    except Exception:
        pass
    return out


# ------------------------------------------------- GetSongBPM lookup
_VARIANT = re.compile(r"\b(remix|rework|bootleg|vip|dub|acoustic|live|flip|cover|sped up|slowed)\b", re.I)
_cache = {}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _strip(title: str) -> str:
    """Title without (brackets), 'feat.' credits and ' - suffix' parts, original characters kept."""
    s = re.sub(r"[\(\[].*?[\)\]]", " ", title or "")
    s = re.split(r"\s+-\s+", s)[0]
    s = re.split(r"\b(?:feat|ft|featuring)\b\.?", s, flags=re.I)[0]
    return re.sub(r"\s+", " ", s).strip()


def _core(title: str) -> str:
    return _fold(_strip(title))


def _variant(title: str) -> bool:
    return bool(_VARIANT.search(title or ""))


def _first_artist(artist: str) -> str:
    return re.split(r"\s*(?:,|&|\bfeat\b|\bft\b|\bx\b|\bvs\b|\band\b)\s*", artist or "", flags=re.I)[0].strip()


def _artist_ok(ours: str, names) -> bool:
    o = f" {_fold(ours)} "
    for n in names:
        n = _fold(n)
        if n and (f" {n} " in o or o.strip() == n or difflib.SequenceMatcher(None, o.strip(), n).ratio() >= 0.88):
            return True
    return False


def _title_ok(ours: str, cand: str) -> bool:
    if _variant(ours) != _variant(cand):
        return False                                   # never borrow a remix's tempo for the original
    if _variant(ours):
        a, b = _fold(ours), _fold(cand)
    else:
        a, b = _core(ours), _core(cand)
    return bool(a) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.92)


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def pick_match(artist: str, title: str, items):
    """Choose the first search hit whose artist and title both match, else None."""
    for it in _as_list(items):
        if not isinstance(it, dict):
            continue
        names = [a.get("name", "") for a in _as_list(it.get("artist")) if isinstance(a, dict)]
        if _artist_ok(artist, names) and _title_ok(title, it.get("song_title") or it.get("title") or ""):
            return it
    return None


def _hit_to_info(it: dict):
    try:
        bpm = int(round(float(it.get("tempo"))))
    except (TypeError, ValueError):
        bpm = None
    if bpm is not None and not 30 <= bpm <= 300:
        bpm = None
    key_text = (it.get("key_of") or "").strip()
    parsed = parse_key(key_text)
    if parsed:
        k = key_info(*parsed)
    elif key_text:
        k = {"key": key_text, "camelot": str(it.get("camelot") or "")}
    else:
        k = {"key": "", "camelot": ""}
    if bpm is None and not k["key"]:
        return None
    return {"bpm": bpm, **k}


def lookup_getsongbpm(artist: str, title: str, api_key: str, timeout: float = 8.0):
    """Published BPM/key from GetSongBPM, or None if not found. Raises RuntimeError on failures."""
    ck = (_fold(artist), _core(title) if not _variant(title) else _fold(title))
    if ck in _cache:
        return _cache[ck]
    query = f"song:{_strip(title) if not _variant(title) else title} artist:{_first_artist(artist)}"
    r = requests.get(f"{API_BASE}/search/",
                     params={"api_key": api_key, "type": "both", "lookup": query, "limit": 10},
                     timeout=timeout)
    if r.status_code in (401, 403):
        raise RuntimeError(f"GetSongBPM rejected the API key (HTTP {r.status_code})")
    if r.status_code == 429:
        raise RuntimeError("GetSongBPM rate limit reached (HTTP 429)")
    if r.status_code >= 400:
        raise RuntimeError(f"GetSongBPM HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("GetSongBPM returned something that isn't JSON")
    hit = pick_match(artist, title, data.get("search") if isinstance(data, dict) else None)
    info = _hit_to_info(hit) if hit else None
    _cache[ck] = info
    return info


# ------------------------------------------------------- combined
def get_music_info(artist: str, title: str, clip_path, api_key: str = ""):
    """Returns (info, notes). info keys: bpm, bpm_src, key, camelot, key_src.
    Sources are 'getsongbpm' or 'estimate'. notes explains anything noteworthy, in one line each."""
    info = {"bpm": None, "bpm_src": "", "key": "", "camelot": "", "key_src": ""}
    notes = []
    if api_key:
        try:
            hit = lookup_getsongbpm(artist, title, api_key)
        except Exception as exc:
            hit = None
            notes.append(f"Lookup failed: {exc}.")
        else:
            if hit is None:
                notes.append("Not found on GetSongBPM.")
        if hit:
            if hit["bpm"] is not None:
                info["bpm"], info["bpm_src"] = hit["bpm"], "getsongbpm"
            if hit["key"]:
                info["key"], info["camelot"], info["key_src"] = hit["key"], hit["camelot"], "getsongbpm"
    else:
        notes.append("No GETSONGBPM_API_KEY set.")
    if (info["bpm"] is None or not info["key"]) and clip_path:
        try:
            est = analyse_clip(clip_path)
        except Exception as exc:
            est = {}
            notes.append(f"Clip analysis failed: {exc}.")
        if info["bpm"] is None and est.get("bpm"):
            info["bpm"], info["bpm_src"] = est["bpm"], "estimate"
        if not info["key"] and est.get("key"):
            info["key"], info["camelot"], info["key_src"] = est["key"], est["camelot"], "estimate"
        if "estimate" in (info["bpm_src"], info["key_src"]):
            notes.append("Estimated from the clip.")
    return info, notes
