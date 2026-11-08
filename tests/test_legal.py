"""Legal files stay consistent with the code."""
import re
from pathlib import Path

import legal
import legal_packages

ROOT = Path(__file__).parent.parent


def test_every_bundled_package_is_in_the_notices():
    notices = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    for name, version, licence, url in legal_packages.PACKAGES + legal_packages.BUILD_TOOLS:
        assert re.search(rf"{re.escape(name)}\s+{re.escape(version)}\b", notices), \
            f"{name} {version} missing from THIRD_PARTY_NOTICES.txt - regenerate the notices"


def test_packages_are_pinned():
    pins = (ROOT / "constraints.txt").read_text(encoding="utf-8").lower().replace("_", "-")
    for name, version, *_ in legal_packages.PACKAGES:
        if name.lower() in ("setuptools",):
            continue
        assert f"{name.lower().replace('_', '-')}=={version}".lower() in pins, f"{name}=={version} not pinned"


def test_sections_are_well_formed():
    for s in legal.sections():
        assert s["id"] and s["title"] and s["paragraphs"]
        assert all(isinstance(p, str) and p for p in s["paragraphs"])


def test_getsongbpm_credit_is_present_everywhere_it_must_be():
    text = " ".join(" ".join(s["paragraphs"]) for s in legal.sections())
    assert "GetSongBPM" in text
    assert "getsongbpm.com" in (ROOT / "README.md").read_text(encoding="utf-8").lower()
    import app
    assert "getsongbpm.com" in app.PAGE.lower()


def test_license_matches_legal_py():
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert legal.COPYRIGHT_HOLDER in lic and legal.COPYRIGHT_YEAR in lic
