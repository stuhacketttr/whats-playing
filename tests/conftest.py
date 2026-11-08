"""Test setup: point the app at a throw-away data folder BEFORE it is imported, and reset its
in-memory state between tests, so tests never touch real history, keys or clips."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

HOME = Path(tempfile.mkdtemp(prefix="whatsplaying-tests-"))
os.environ["WHATSPLAYING_HOME"] = str(HOME)
for k in ("GETSONGBPM_API_KEY", "SHAZAM_API_KEY", "SAVE_LAST_CLIP"):
    os.environ.pop(k, None)

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import app as app_module          # noqa: E402
import musicinfo                  # noqa: E402
from synth import SR, make_track, write   # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_home():
    yield
    shutil.rmtree(HOME, ignore_errors=True)


@pytest.fixture
def app(monkeypatch):
    """The app module, with fresh state, empty data folder and no real audio or network."""
    for f in HOME.iterdir():
        if f.is_file() and f.name != ".env":
            f.unlink()
    monkeypatch.delenv("GETSONGBPM_API_KEY", raising=False)
    monkeypatch.delenv("SHAZAM_API_KEY", raising=False)
    s = app_module.state
    s.update(status="idle", message="Ready.", clip_id=0, peak=None, retry=None, current=None,
             history=[], continuous=False)
    monkeypatch.setattr(app_module, "_backup_done", False)
    musicinfo._cache.clear()

    wav = HOME / "synthetic.wav"          # 174 BPM, A minor
    write(str(wav), make_track(174, tonic=9, minor=True))
    monkeypatch.setattr(app_module, "capture_wav",
                        lambda seconds, path: (shutil.copy(wav, path), 0.4)[1])
    # Run background threads inline so tests never depend on timing.
    class InlineThread:
        def __init__(self, target=None, args=(), kwargs=None, **_):
            self._t, self._a, self._k = target, args, kwargs or {}

        def start(self):
            self._t(*self._a, **self._k)

    monkeypatch.setattr(app_module.threading, "Thread", InlineThread)
    return app_module


@pytest.fixture
def client(app):
    return app.app.test_client()


@pytest.fixture
def match(app, monkeypatch):
    """match('Title') makes ShazamIO 'recognise' that track on the next identify_once()."""
    def _match(title, artist="Test Artist"):
        monkeypatch.setattr(app, "rec_shazamio", lambda p: {
            "title": title, "artist": artist, "album": None, "cover": None, "isrc": None, "links": {}})
    return _match


def state_of(client):
    return client.get("/api/state").get_json()
