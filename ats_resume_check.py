"""ats-resume-check: find the résumé PDFs an applicant tracking system cannot read.

An ATS reads the PDF's text layer, not the page you see. A résumé can look
perfect and still reach the recruiter as one long run of letters. This tool
reads the text layer the way an ATS does and reports what will go wrong.

Needs poppler on the PATH (`pdftotext`, `pdffonts`).
  macOS:  brew install poppler
  Debian: apt install poppler-utils
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
YEAR = r"(?:19|20)\d{2}"
DASH = r"\s*(?:-|–|—|to)\s*"
YEAR_ONLY_RANGE = re.compile(rf"(?<![a-z/.\d])({YEAR}){DASH}({YEAR}|present|current|now)\b", re.I)
MONTH_RANGE = re.compile(rf"{MONTH}\s+{YEAR}{DASH}(?:{MONTH}\s+{YEAR}|present|current|now)", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\s.()-]*){10,}")
NUMBERED_HEADING = re.compile(r"^\s*\d{1,2}[\s.)/-]+[A-Z][A-Za-z ]{3,}$", re.M)
SECTIONS = {
    "experience": re.compile(r"^\s*(?:work |professional )?experience\s*$", re.I | re.M),
    "education": re.compile(r"^\s*education\s*$", re.I | re.M),
    "skills": re.compile(r"^\s*(?:skills|core skills|key skills)\s*$", re.I | re.M),
}


@dataclass
class Finding:
    level: str
    check: str
    detail: str


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"{cmd[0]} failed")
    return out.stdout


def read_text(pdf: str) -> str:
    """The text layer in reading order, as most ATS parsers see it."""
    return _run(["pdftotext", "-raw", "-enc", "UTF-8", pdf, "-"])


def read_fonts(pdf: str) -> list[tuple[str, str]]:
    """(font name, font type) for every font in the PDF."""
    lines = _run(["pdffonts", pdf]).splitlines()[2:]
    fonts = []
    for line in lines:
        m = re.match(r"(\S+)\s+(Type 3|Type 1C?|TrueType|CID \S+(?: \S+)?|Type 1)\s", line)
        if m:
            fonts.append((m.group(1), m.group(2)))
    return fonts


def check_text_layer(text: str) -> Finding:
    words = len(text.split())
    if words < 50:
        return Finding(FAIL, "text layer", f"only {words} words can be read. The PDF is probably an image or a scan. Export it from the source file instead.")
    return Finding(PASS, "text layer", f"{words} words can be read")


def check_word_spaces(text: str) -> Finding:
    tokens = [t for t in text.split() if t.isalpha() or re.fullmatch(r"[A-Za-z][A-Za-z'’-]+", t)]
    long = [t for t in tokens if len(t) >= 20]
    share = len(long) / max(len(tokens), 1)
    if share > 0.05:
        sample = ", ".join(long[:3])
        return Finding(FAIL, "word spaces", f"{len(long)} words run together (for example: {sample}). The ATS will not find your keywords.")
    return Finding(PASS, "word spaces", "words are separated")


def check_fonts(fonts: list[tuple[str, str]]) -> Finding:
    type3 = sorted({name for name, kind in fonts if kind == "Type 3"})
    if type3:
        return Finding(WARN, "fonts", f"Type 3 fonts: {', '.join(type3[:3])}. These often lose the spaces between words. Variable fonts usually cause this; use the static font files.")
    return Finding(PASS, "fonts", "no Type 3 fonts")


def check_dates(text: str) -> Finding:
    year_only = [m.group(0) for m in YEAR_ONLY_RANGE.finditer(text)
                 if not re.search(MONTH + r"\s*$", text[max(0, m.start() - 12):m.start()], re.I)]
    if year_only and not MONTH_RANGE.search(text):
        return Finding(WARN, "dates", f"dates show the year only ({year_only[0]}). Some ATS (Workday among them) then guess January, or drop the job. Use month and year.")
    return Finding(PASS, "dates", "dates include the month")


def check_contact(text: str) -> Finding:
    missing = [name for name, rx in (("email", EMAIL), ("phone", PHONE)) if not rx.search(text)]
    if missing:
        return Finding(WARN, "contact", f"no {' or '.join(missing)} found in the text layer")
    return Finding(PASS, "contact", "email and phone found")


def check_headings(text: str) -> Finding:
    missing = [name for name, rx in SECTIONS.items() if not rx.search(text)]
    numbered = NUMBERED_HEADING.findall(text)
    if numbered:
        return Finding(WARN, "headings", f"numbered headings such as '{numbered[0].strip()}'. Many parsers only know plain names: Experience, Education, Skills.")
    if missing:
        return Finding(WARN, "headings", f"no plain heading for: {', '.join(missing)}")
    return Finding(PASS, "headings", "standard section headings found")


def check_text(text: str) -> list[Finding]:
    """Every check that needs only the text layer."""
    first = check_text_layer(text)
    if first.level == FAIL:
        return [first]
    return [first, check_word_spaces(text), check_dates(text), check_contact(text), check_headings(text)]


def check_pdf(pdf: str) -> list[Finding]:
    return check_text(read_text(pdf)) + [check_fonts(read_fonts(pdf))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check that an applicant tracking system can read your résumé PDF.")
    ap.add_argument("pdf", nargs="+", help="one or more résumé PDFs")
    ap.add_argument("--text", action="store_true", help="also print the text layer the ATS will see")
    args = ap.parse_args(argv)

    for tool in ("pdftotext", "pdffonts"):
        if not shutil.which(tool):
            print(f"{tool} not found. Install poppler (macOS: brew install poppler).", file=sys.stderr)
            return 2

    worst = 0
    for pdf in args.pdf:
        print(pdf)
        try:
            findings = check_pdf(pdf)
        except RuntimeError as e:
            print(f"  {FAIL}  read: {e}")
            worst = 1
            continue
        for f in findings:
            print(f"  {f.level}  {f.check}: {f.detail}")
            if f.level == FAIL:
                worst = 1
        if args.text:
            print("  --- text layer ---")
            print(read_text(pdf))
    return worst


if __name__ == "__main__":
    sys.exit(main())
