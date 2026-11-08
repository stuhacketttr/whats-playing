"""The app's own behaviour: identify, enrich, history, CSV, retry, delete, and the HTTP routes.
Audio capture, ShazamIO, shazam-api.com and GetSongBPM are all mocked (see conftest.py)."""
import csv
import glob

import pytest

import musicinfo
from conftest import HOME, state_of
from test_musicinfo import Resp, item


def rows():
    with open(HOME / "recognitions.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def http_get(monkeypatch, body, code=200, calls=None):
    def get(url, params=None, timeout=None):
        if calls is not None:
            calls.append(params["lookup"])
        return Resp(code, body)
    monkeypatch.setattr(musicinfo.requests, "get", get)


def wait_until_idle(client):
    """Threads run inline in tests (see conftest), so there is nothing to wait for."""
    assert state_of(client)["status"] != "matching"


# ------------------------------------------------------------------ identify
def test_identify_estimates_and_saves(app, client, match):
    match("Song One")
    app.identify_once()
    s = state_of(client)
    c = s["current"]
    assert (c["bpm"], c["bpm_src"], c["key"], c["camelot"]) == (174, "estimate", "A minor", "8A")
    assert "No GETSONGBPM_API_KEY set." in s["message"] and "Estimated from the clip." in s["message"]
    r = rows()[-1]
    assert (r["title"], r["bpm"], r["key"], r["camelot"], r["bpm_src"], r["key_src"]) == \
           ("Song One", "174", "A minor", "8A", "estimate", "estimate")


def test_identify_uses_published_values(app, client, match, monkeypatch):
    monkeypatch.setenv("GETSONGBPM_API_KEY", "gk")
    http_get(monkeypatch, {"search": [item("Song Two", "Test Artist", "172", "C♯m")]})
    monkeypatch.setattr(musicinfo, "analyse_clip", lambda p: pytest.fail("no analysis expected"))
    match("Song Two")
    app.identify_once()
    s = state_of(client)
    assert s["current"]["bpm_src"] == "getsongbpm" and s["current"]["camelot"] == "12A"
    assert s["message"] == "Matched via ShazamIO."


def test_repeat_of_latest_track_makes_no_new_lookup_or_row(app, client, match, monkeypatch):
    monkeypatch.setenv("GETSONGBPM_API_KEY", "gk")
    calls = []
    http_get(monkeypatch, {"search": [item("Song", "Test Artist", "99", "Am")]}, calls=calls)
    match("Song")
    app.identify_once()
    app.identify_once()
    assert len(calls) == 1 and len(rows()) == 1


def test_lookup_crash_still_records_match(app, client, match, monkeypatch):
    monkeypatch.setattr(musicinfo, "get_music_info", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    match("Song Six")
    app.identify_once()
    s = state_of(client)
    assert s["current"]["title"] == "Song Six" and s["current"]["bpm"] is None
    assert "unavailable: boom" in s["message"]


def test_silence_is_reported(app, client, monkeypatch):
    monkeypatch.setattr(app, "capture_wav", lambda sec, path: 0.0)
    app.identify_once()
    assert state_of(client)["status"] == "silence"


# -------------------------------------------------------------------- retry
def test_miss_then_retry_success(app, client, monkeypatch):
    monkeypatch.setenv("SHAZAM_API_KEY", "k")
    monkeypatch.setattr(app, "rec_shazamio", lambda p: None)
    app.identify_once()
    s = state_of(client)
    assert s["status"] == "no_match" and s["retry"] and s["shazamapi_ready"]
    monkeypatch.setattr(app, "rec_shazamapi", lambda p: {
        "title": "Song Five", "artist": "Other", "album": None, "cover": None, "isrc": None, "links": {}})
    client.post("/api/retry")
    wait_until_idle(client)
    s = state_of(client)
    assert s["current"]["title"] == "Song Five" and s["current"]["bpm"] == 174     # enriched from the missed clip
    assert s["retry"] is None and not app.RETRY_CLIP.exists()


def test_retry_api_error_is_shown_and_clears_prompt(app, client, monkeypatch):
    monkeypatch.setenv("SHAZAM_API_KEY", "k")
    monkeypatch.setattr(app, "rec_shazamio", lambda p: None)
    app.identify_once()
    monkeypatch.setattr(app, "rec_shazamapi", lambda p: (_ for _ in ()).throw(RuntimeError("HTTP 403: Not enough balance")))
    client.post("/api/retry")
    wait_until_idle(client)
    s = state_of(client)
    assert s["status"] == "error" and "403" in s["message"] and s["retry"] is None


def test_retry_without_key_does_nothing(app, client, monkeypatch):
    monkeypatch.setattr(app, "rec_shazamio", lambda p: None)
    app.identify_once()
    assert client.post("/api/retry").get_json() == {"ok": False}
    assert "SHAZAM_API_KEY" in state_of(client)["message"]


def test_dismiss_retry_removes_clip(app, client, monkeypatch):
    monkeypatch.setattr(app, "rec_shazamio", lambda p: None)
    app.identify_once()
    assert app.RETRY_CLIP.exists()
    client.post("/api/dismiss_retry")
    assert state_of(client)["retry"] is None and not app.RETRY_CLIP.exists()


# ---------------------------------------------------------- history and CSV
OLD_CSV = ("\ufeffid,timestamp,artist,title,album,isrc,source,cover,links\n"
           'old1,2026-11-07 19:50:00,Artist A,Song A,Album A,ISRC1,shazamio,,"{}"\n'
           'old2,2026-11-07 19:55:00,Artist B,Song B,,,shazamapi,https://x/y.jpg,"{""shazam"": ""https://s""}"\n')


def test_old_csv_is_backed_up_and_upgraded(app, client):
    (HOME / "recognitions.csv").write_text(OLD_CSV, encoding="utf-8", newline="")
    app.load_history()
    h = state_of(client)["history"]
    assert [x["title"] for x in h] == ["Song B", "Song A"] and h[0]["bpm"] is None
    assert len(glob.glob(str(HOME / "recognitions.*.bak.csv"))) == 1
    assert list(rows()[0].keys()) == app.FIELDS and len(rows()) == 2


def test_delete_keeps_columns_and_reload_round_trips(app, client, match):
    for t in ("One", "Two", "Three"):
        match(t)
        app.identify_once()
    ids = [x["id"] for x in state_of(client)["history"] if x["title"] in ("One", "Three")]
    assert client.post("/api/delete", json={"ids": ids}).get_json()["removed"] == 2
    assert [r["title"] for r in rows()] == ["Two"] and "camelot" in rows()[0]
    assert len(glob.glob(str(HOME / "recognitions.*.bak.csv"))) == 1
    app.state["history"] = []
    app.load_history()
    t = state_of(client)["history"][0]
    assert t["title"] == "Two" and t["bpm"] == 174 and isinstance(t["bpm"], int) and t["camelot"] == "8A"


def test_delete_nothing(client):
    assert client.post("/api/delete", json={"ids": []}).get_json()["removed"] == 0


# ------------------------------------------------------------------- routes
def test_page_and_legal_routes(client):
    assert client.get("/").status_code == 200
    j = client.get("/api/legal").get_json()
    assert [s["id"] for s in j["sections"]] == ["about", "terms", "privacy", "credits", "notices"]
    assert j["packages"] and j["mit_text"].startswith("MIT License")
    r = client.get("/legal/notices.txt")
    assert r.status_code == 200 and b"THIRD-PARTY NOTICES" in r.data


def test_open_external_is_locked_down(client, monkeypatch):
    import app as app_module
    opened = []
    monkeypatch.setattr(app_module.webbrowser, "open", lambda u: opened.append(u) or True)
    assert client.post("/api/open_external", json={"url": "https://getsongbpm.com"}).status_code == 200
    assert client.post("/api/open_external", json={"url": "javascript:alert(1)"}).status_code == 400
    assert client.post("/api/open_external", json={"url": "file:///C:/Windows"}).status_code == 400
    assert client.post("/api/open_external", json={"url": "https://x.com"},
                       headers={"Origin": "https://evil.example"}).status_code == 403
    assert opened == ["https://getsongbpm.com"]


def test_embedded_javascript_has_no_python_escape_damage(app):
    """The page is a normal (non-raw) Python string, so a single backslash in the JS (\\s, \\b ...) gets mangled.
    The regexes and unicode escapes must reach the browser intact."""
    page = app.PAGE
    assert r"const FEAT=/[\(\[]\s*(feat|ft|with)\b[^\)\]]*[\)\]]/ig;" in page
    assert "\\u00b7" in page and "\x08" not in page


# ----------------------------------------------------------------- settings
def test_settings_save_updates_env_backs_up_and_never_returns_the_key(app, client, monkeypatch):
    env = HOME / ".env"
    env.write_text("# comment\nSHAZAM_API_KEY=\nCLIP_SECONDS=10\n", encoding="utf-8")
    monkeypatch.setattr(app, "_env_backup_done", False)
    r = client.post("/api/settings", json={"getsongbpm_api_key": "abcd1234efgh", "shazam_api_key": "zzzz9999yyyy"})
    j = r.get_json()
    assert r.status_code == 200 and j["getsongbpm_api_key"]["set"] and j["shazam_api_key"]["set"]
    assert "abcd1234efgh" not in r.get_data(as_text=True)
    text = env.read_text(encoding="utf-8")
    assert "SHAZAM_API_KEY=zzzz9999yyyy" in text and "GETSONGBPM_API_KEY=abcd1234efgh" in text
    assert "# comment" in text and "CLIP_SECONDS=10" in text
    assert glob.glob(str(HOME / ".env.*.bak"))
    assert client.get("/api/state").get_json()["shazamapi_ready"] is True
    # clearing one key leaves the other alone
    j = client.post("/api/settings", json={"shazam_api_key": ""}).get_json()
    assert not j["shazam_api_key"]["set"] and j["getsongbpm_api_key"]["set"]
    monkeypatch.delenv("GETSONGBPM_API_KEY", raising=False)
    env.unlink()


def test_settings_rejects_bad_values_and_foreign_origin(client):
    assert client.post("/api/settings", json={"shazam_api_key": "a b"}).status_code == 400
    assert client.post("/api/settings", json={"shazam_api_key": "a\nb=c"}).status_code == 400
    assert client.post("/api/settings", json={"shazam_api_key": "x"},
                       headers={"Origin": "https://evil.example"}).status_code == 403


# -------------------------------------------------------------- copy cover
def test_copy_cover(app, client, monkeypatch):
    class R:
        headers = {"Content-Type": "image/jpeg"}
        raw = type("Raw", (), {"read": lambda self, n, decode_content=False: b"\xff\xd8jpeg"})()
        def raise_for_status(self): pass
    got = []
    monkeypatch.setattr(app.requests, "get", lambda url, **kw: R())
    monkeypatch.setattr(app, "copy_image_to_clipboard", lambda data: got.append(data))
    monkeypatch.setattr(app, "rec_shazamio", lambda p: {
        "title": "T", "artist": "A", "album": None, "cover": "https://example.com/c.jpg",
        "isrc": None, "links": {}})
    client.post("/api/identify")
    tid = state_of(client)["current"]["id"]
    assert client.post("/api/copy_cover", json={"id": tid}).get_json()["ok"] and got == [b"\xff\xd8jpeg"]
    assert client.post("/api/copy_cover", json={"id": "nope"}).status_code == 404
    assert client.post("/api/copy_cover", json={"id": tid},
                       headers={"Origin": "https://evil.example"}).status_code == 403


def test_discogs_link_is_offered(app):
    assert "https://www.discogs.com/search/?q=" in app.PAGE


def test_rebound_host_is_refused(client):
    """A DNS-rebinding page reaches the app under its own hostname; that must be rejected."""
    assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/settings", json={"shazam_api_key": "x"},
                       headers={"Host": "evil.example", "Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/settings", headers={"Host": "127.0.0.1:5000"}).status_code == 200


# ------------------------------------------------------------ genre and label
def test_shazamio_genre_and_label_are_parsed_saved_and_reloaded(app, client, monkeypatch):
    import sys, types
    out = {"track": {"title": "T", "subtitle": "A", "genres": {"primary": "Dance"},
                     "sections": [{"metadata": [{"title": "Album", "text": "Alb"},
                                                {"title": "Label", "text": "Some Records"}]}]}}

    class FakeShazam:
        async def recognize(self, path):
            return out

    monkeypatch.setitem(sys.modules, "shazamio", types.SimpleNamespace(Shazam=FakeShazam))
    res = app.rec_shazamio("x.wav")
    assert (res["genre"], res["label"], res["album"]) == ("Dance", "Some Records", "Alb")
    monkeypatch.setattr(app, "rec_shazamio", lambda p: res)
    client.post("/api/identify")
    c = state_of(client)["current"]
    assert (c["genre"], c["label"]) == ("Dance", "Some Records")
    r = rows()[-1]
    assert (r["genre"], r["label"]) == ("Dance", "Some Records")
    app.load_history()                      # round trip through the CSV
    h = state_of(client)["history"][0]
    assert (h["genre"], h["label"]) == ("Dance", "Some Records")


def test_missing_genre_and_label_are_fine(app, client, match):
    match("Plain")
    client.post("/api/identify")
    c = state_of(client)["current"]
    assert not c.get("genre") and not c.get("label")
