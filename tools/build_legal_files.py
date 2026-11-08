"""Regenerates LICENSE and TERMS.txt from legal.py (the single source of truth).
Run by the build scripts; can also be run by hand:  python tools\\build_legal_files.py
"""
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import legal  # noqa: E402

WIDTH = 78


def render(section: dict) -> str:
    out = [section["title"].upper(), "=" * len(section["title"])]
    for p in section["paragraphs"]:
        if p.startswith("## "):
            out += ["", p[3:]]
        elif p.startswith("- "):
            out.append(textwrap.fill(p[2:], WIDTH, initial_indent="  * ", subsequent_indent="    "))
        else:
            out += ["", textwrap.fill(p, WIDTH)]
    for link in section.get("links", []):
        out.append(f"  {link['label']}: {link['url']}")
    return "\n".join(out)


def main():
    if legal.identity_is_placeholder():
        print("WARNING: legal.py still has the placeholder copyright holder. Set COPYRIGHT_HOLDER "
              "(and REPO_URL) before publishing.")
    wanted = {"terms", "privacy", "notices"}
    parts = [f"{legal.APP_NAME} {legal.APP_VERSION} - terms of use, privacy and notices",
             "Third-party software licences are listed in the Credits section of the program's Help "
             "and in full in THIRD_PARTY_NOTICES.txt.",
             "This text is provided for information and is not legal advice."]
    parts = [textwrap.fill(p, WIDTH) for p in parts]
    body = [render(s) for s in legal.sections() if s["id"] in wanted]
    text = "\n\n".join(parts + body) + "\n\n" + "MIT LICENCE\n===========\n\n" + legal.mit_text()
    # CRLF so the installer's licence page and Windows Notepad both display it cleanly
    (ROOT / "TERMS.txt").write_text(text, encoding="utf-8", newline="\r\n")
    (ROOT / "LICENSE").write_text(legal.mit_text(), encoding="utf-8", newline="\r\n")
    print("Wrote TERMS.txt and LICENSE")


if __name__ == "__main__":
    main()
