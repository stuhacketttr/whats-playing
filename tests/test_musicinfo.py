"""BPM / key estimation, key notation, and the GetSongBPM lookup (network mocked).

The audio tests use synthetic tracks (drums + a chord progression in a known key), so they prove the
maths works, NOT that it is accurate on real recordings. See docs/HANDOFF.md for how to tune on real clips.
"""
import numpy as np
import pytest

import musicinfo as mi
from synth import SR, make_track, write


# ---------------------------------------------------------------- key notation
@pytest.mark.parametrize("text,expected", [
    ("Am", (9, True)), ("A♭", (8, False)), ("C♯m", (1, True)), ("F# minor", (6, True)),
    ("Bb major", (10, False)), ("G", (7, False)), ("Ebm", (3, True)), ("E♭m", (3, True)),
    ("Dmaj", (2, False)), ("", None), ("H", None), ("Xm", None), (None, None),
])
def test_parse_key(text, expected):
    assert mi.parse_key(text) == expected


def test_camelot_wheel():
    known = {("A", True): "8A", ("C", False): "8B", ("E", True): "9A", ("G", False): "9B",
             ("C#", True): "12A", ("E", False): "12B", ("G#", True): "1A", ("B", False): "1B",
             ("F", True): "4A", ("Ab", False): "4B", ("D", True): "7A", ("F", False): "7B"}
    for (name, minor), cam in known.items():
        pc, parsed_minor = mi.parse_key(name + ("m" if minor else ""))
        assert mi.key_info(pc, minor)["camelot"] == cam, (name, minor)


def test_key_names():
    assert mi.key_info(9, True) == {"key": "A minor", "camelot": "8A"}
    assert mi.key_info(1, False)["key"] == "Db major"      # C# major is written Db major


# ---------------------------------------------------------- estimates (synthetic)
@pytest.mark.parametrize("bpm", [100, 110, 120, 124, 128, 135, 140, 150, 160, 170, 174, 180])
def test_bpm_synthetic(bpm):
    assert abs(mi.estimate_bpm(make_track(bpm, seed=1), SR) - bpm) <= 1.5


def test_bpm_half_time_pattern():
    assert abs(mi.estimate_bpm(make_track(140, seed=1, halftime=True), SR) - 140) <= 1.5


@pytest.mark.parametrize("tonic", range(12))
@pytest.mark.parametrize("minor", [False, True])
def test_key_synthetic_all_24(tonic, minor):
    got = mi.estimate_key(make_track(124, tonic=tonic, minor=minor, seed=tonic), SR)
    assert got["key"] == mi.key_info(tonic, minor)["key"]


def test_no_rhythm_gives_no_bpm():
    rng = np.random.default_rng(0)
    assert mi.estimate_bpm(np.zeros(SR * 10, dtype=np.float32), SR) is None
    assert mi.estimate_bpm(rng.standard_normal(SR * 10).astype(np.float32) * 0.1, SR) is None
    assert mi.estimate_bpm(np.zeros(SR * 2, dtype=np.float32) + 0.1, SR) is None   # too short
    assert mi.estimate_key(np.zeros(SR * 10, dtype=np.float32), SR) is None


def test_analyse_clip_mono_and_stereo(tmp_path):
    import wave
    x = make_track(174, tonic=9, minor=True)
    mono = tmp_path / "m.wav"
    write(str(mono), x)
    assert mi.analyse_clip(str(mono)) == {"bpm": 174, "key": "A minor", "camelot": "8A"}
    st = tmp_path / "s.wav"
    with wave.open(str(st), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.repeat((x * 32767).astype("<i2")[:, None], 2, axis=1).tobytes())
    assert mi.analyse_clip(str(st))["bpm"] == 174


# ------------------------------------------------------------ GetSongBPM lookup
class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._body = code, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def item(title, artist, tempo, key, camelot=""):
    return {"song_id": "x", "song_title": title, "tempo": tempo, "key_of": key, "camelot": camelot,
            "artist": {"id": "1", "name": artist}}


@pytest.fixture
def http(monkeypatch):
    mi._cache.clear()
    calls = []

    def install(body, code=200):
        def get(url, params=None, timeout=None):
            calls.append((url, dict(params)))
            return Resp(code, body)
        monkeypatch.setattr(mi.requests, "get", get)
    install.calls = calls
    return install


@pytest.mark.parametrize("artist,title,payload,expected", [
    ("Ben Klock", "Subzero", [item("Subzero", "Ben Klock", "132", "A♭m")], (132, "G# minor", "1A")),
    ("Burial", "Archangel (feat. X)", [item("Archangel", "Burial", "136", "F♯m")], (136, "F# minor", "11A")),
    ("Burial", "Archangel", [{"song_title": "Archangel", "tempo": "136", "key_of": "C#m",
                              "artist": [{"name": "Burial"}]}], (136, "C# minor", "12A")),
    ("Daft Punk & Pharrell", "Get Lucky", [item("Get Lucky", "Daft Punk", "116", "F#m")], (116, "F# minor", "11A")),
    ("Adele", "Hello (Club Remix)", [item("Hello", "Adele", "79", "Fm")], None),          # never borrow the original
    ("Adele", "Hello", [item("Hello (Club Remix)", "Adele", "128", "Cm"),
                        item("Hello", "Adele", "79", "Fm")], (79, "F minor", "4A")),      # skip the remix
    ("Adele", "Hello (Club Remix)", [item("Hello (Club Remix)", "Adele", "128", "Cm")], (128, "C minor", "5A")),
    ("Air", "Sexy Boy", [item("Sexy Boy", "Fair", "100", "C")], None),                    # 'Air' is not 'Fair'
    ("Sigur Rós", "Hoppípolla", [item("Hoppípolla", "Sigur Ros", "92", "C#")], (92, "Db major", "3B")),
    ("X", "Y", {"error": "no result"}, None),
    ("X", "Y", [], None),
])
def test_lookup_matching(http, artist, title, payload, expected):
    http({"search": payload})
    got = mi.lookup_getsongbpm(artist, title, "KEY")
    assert (None if got is None else (got["bpm"], got["key"], got["camelot"])) == expected


def test_lookup_request_shape(http):
    http({"search": []})
    mi.lookup_getsongbpm("Sigur Rós", "Hoppípolla (feat. X)", "K")
    url, params = http.calls[0]
    assert url == "https://api.getsongbpm.com/search/"
    assert params == {"api_key": "K", "type": "both", "lookup": "song:Hoppípolla artist:Sigur Rós", "limit": 10}


@pytest.mark.parametrize("code,body,fragment", [
    (403, {}, "rejected the API key"), (401, {}, "rejected the API key"), (429, {}, "rate limit"),
    (500, {}, "HTTP 500"), (200, ValueError("x"), "isn't JSON")])
def test_lookup_errors(http, code, body, fragment):
    http(body, code)
    with pytest.raises(RuntimeError, match=fragment):
        mi.lookup_getsongbpm("A", "B", "K")


def test_lookup_cache(http):
    http({"search": [item("Subzero", "Ben Klock", "132", "Am")]})
    mi.lookup_getsongbpm("Ben Klock", "Subzero", "K")
    mi.lookup_getsongbpm("Ben Klock", "Subzero", "K")
    assert len(http.calls) == 1


# ------------------------------------------------------------ combined strategy
@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "clip.wav"
    write(str(p), make_track(174, tonic=9, minor=True))
    return str(p)


def test_info_no_key_estimates(clip):
    info, notes = mi.get_music_info("A", "B", clip, "")
    assert (info["bpm"], info["bpm_src"], info["key"], info["key_src"]) == (174, "estimate", "A minor", "estimate")
    assert any("No GETSONGBPM_API_KEY" in n for n in notes)


def test_info_lookup_complete_skips_analysis(http, clip, monkeypatch):
    http({"search": [item("B", "A", "172", "C♯m")]})
    monkeypatch.setattr(mi, "analyse_clip", lambda p: pytest.fail("must not analyse when the lookup is complete"))
    info, notes = mi.get_music_info("A", "B", clip, "K")
    assert (info["bpm"], info["bpm_src"], info["key"], info["camelot"]) == (172, "getsongbpm", "C# minor", "12A")
    assert notes == []


def test_info_partial_lookup_filled_by_estimate(http, clip):
    http({"search": [item("B", "A", "170", "")]})
    info, _ = mi.get_music_info("A", "B", clip, "K")
    assert (info["bpm"], info["bpm_src"], info["key"], info["key_src"]) == (170, "getsongbpm", "A minor", "estimate")


def test_info_lookup_failure_falls_back(http, clip):
    http({}, 403)
    info, notes = mi.get_music_info("A", "B", clip, "K")
    assert info["bpm_src"] == "estimate" and any("rejected the API key" in n for n in notes)
