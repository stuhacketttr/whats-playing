"""Pre-publish gate. Run before making the repo public or tagging a release:

    python tools/check_release_ready.py

Exits 0 only if nothing blocks publishing. Read-only: it changes nothing.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

problems, warnings = [], []


def fail(msg):
    problems.append(msg)


def warn(msg):
    warnings.append(msg)


def read(name):
    p = ROOT / name
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def check_identity():
    import legal
    if legal.identity_is_placeholder():
        fail("legal.py: COPYRIGHT_HOLDER is still the placeholder. Set your GitHub handle or project name, "
             "then run: python tools/build_legal_files.py")
    if not legal.REPO_URL.strip():
        fail("legal.py: REPO_URL is empty. Set it once the repo exists, e.g. https://github.com/<handle>/whats-playing")
    elif not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", legal.REPO_URL):
        fail(f"legal.py: REPO_URL looks wrong: {legal.REPO_URL!r} (no trailing slash, no .git)")
    for name in ("README.md", "TERMS.txt", "LICENSE", "THIRD_PARTY_NOTICES.txt"):
        if "[YOUR GITHUB HANDLE]" in read(name):
            fail(f"{name}: still contains [YOUR GITHUB HANDLE]")
    lic = read("LICENSE")
    if legal.COPYRIGHT_HOLDER not in lic or legal.COPYRIGHT_YEAR not in lic:
        fail("LICENSE does not match legal.py (holder/year). Run: python tools/build_legal_files.py")
    if legal.COPYRIGHT_HOLDER not in read("TERMS.txt"):
        fail("TERMS.txt does not match legal.py. Run: python tools/build_legal_files.py")


def check_versions():
    import legal
    v = legal.APP_VERSION
    if f'#define MyAppVersion "{v}"' not in read("installer.iss"):
        fail(f"installer.iss default MyAppVersion is not {v} (legal.APP_VERSION)")
    if f"set VERSION={v}" not in read("build-installer.bat"):
        fail(f"build-installer.bat default VERSION is not {v} (legal.APP_VERSION)")


def check_secrets():
    for line in read(".env.example").splitlines():
        m = re.match(r"\s*([A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*=\s*(\S+)", line)
        if m:
            fail(f".env.example: {m.group(1)} has a value - it must be blank")
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except Exception:
        warn("Not a git repository (or git missing) - skipped the tracked-files check. Re-run after `git init`.")
        tracked = []
    bad = re.compile(r"(^|/)\.env$|recognitions.*\.csv$|\.wav$|\.log$|(^|/)(dist|build)/|\.exe$")
    for f in tracked:
        if bad.search(f):
            fail(f"tracked file should not be in the repo: {f}")
    # Anything key-shaped in the tracked text files
    for f in tracked:
        p = ROOT / f
        if p.suffix.lower() in {".py", ".md", ".txt", ".bat", ".iss", ".yml", ".ini", ".example"} and p.is_file():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{24,})", txt):
                if "test" not in f.lower():
                    fail(f"{f}: possible secret: {m.group(0)[:40]}...")


def check_notices():
    import legal_packages
    notices = read("THIRD_PARTY_NOTICES.txt")
    for name, version, *_ in legal_packages.PACKAGES + legal_packages.BUILD_TOOLS:
        if not re.search(rf"{re.escape(name)}\s+{re.escape(version)}\b", notices):
            fail(f"THIRD_PARTY_NOTICES.txt is missing {name} {version}")
    req = {l.split("==")[0].split(">=")[0].strip().lower().replace("_", "-") for l in read("requirements.txt").splitlines()
           if l.strip() and not l.startswith("#")}
    known = {n.lower().replace("_", "-") for n, *_ in legal_packages.PACKAGES}
    for r in sorted(req - known):
        warn(f"requirements.txt lists '{r}' which is not in legal_packages.PACKAGES - regenerate notices if it ships")


def check_required_files():
    for f in ("LICENSE", "README.md", "TERMS.txt", "THIRD_PARTY_NOTICES.txt", "constraints.txt", ".gitignore",
              ".gitattributes", "CLAUDE.md", "docs/HANDOFF.md", "docs/RELEASING.md"):
        if not (ROOT / f).exists():
            fail(f"missing {f}")
    if "getsongbpm.com" not in read("README.md").lower():
        fail("README.md must link to getsongbpm.com (their API terms require a visible backlink)")


def check_decisions():
    warn("ShazamIO is an unofficial, reverse-engineered Shazam client. Decide consciously whether to ship it "
         "in a public repo (see docs/HANDOFF.md > Open decisions).")
    warn("GetSongBPM: register with the public repo URL as both Website URL and Backlink URL; they ask private or "
         "in-development projects to contact them first.")


def main():
    for fn in (check_identity, check_versions, check_secrets, check_notices, check_required_files, check_decisions):
        try:
            fn()
        except Exception as e:      # a broken check must not look like a pass
            fail(f"{fn.__name__} crashed: {e!r}")
    for w in warnings:
        print(f"  warn  {w}")
    for p in problems:
        print(f"  FAIL  {p}")
    print(f"\n{len(problems)} blocking problem(s), {len(warnings)} warning(s).")
    print("READY TO PUBLISH" if not problems else "NOT READY - fix the FAIL lines above.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
