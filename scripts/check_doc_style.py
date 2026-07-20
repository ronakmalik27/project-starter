#!/usr/bin/env python3
"""Enforce the writing style in docs/process/05-documentation-standards.md.

Plain, clean, ASCII-first prose. This script fails on typographic Unicode that
creeps in from word processors and AI output: em/en dashes, curly quotes,
ellipsis, math glyphs, and Unicode arrows. Use plain ASCII instead (a hyphen
with spaces, straight quotes, "..", "<=", "->", and so on).

Usage:
    python3 scripts/check_doc_style.py                # scan the default set
    python3 scripts/check_doc_style.py a.md docs/b.md # scan specific files

Exit code 0 if clean, 1 if any violation is found.
"""
from __future__ import annotations

import sys
from pathlib import Path

# char -> what to use instead
BANNED = {
    "—": "em dash -> ' - ' (hyphen with spaces), a comma, or two sentences",
    "–": "en dash -> ' - ' or 'to' (e.g. '1 to 5')",
    "―": "horizontal bar -> ' - '",
    "§": "section sign -> write 'section 6.4'",
    "‘": "left single quote -> straight '",
    "’": "right single quote/apostrophe -> straight '",
    "“": "left double quote -> straight \"",
    "”": "right double quote -> straight \"",
    "…": "ellipsis -> '..'",
    "×": "multiplication sign -> 'x'",
    "≤": "less-than-or-equal -> '<='",
    "≥": "greater-than-or-equal -> '>='",
    "≠": "not-equal -> '!='",
    "±": "plus-minus -> '+/-'",
    "Σ": "sigma -> 'sum(...)'",
    "→": "right arrow -> '->'",
    "←": "left arrow -> '<-'",
}

# Records, not proposals: kept verbatim by design, exempt from the scan.
EXEMPT_DIRS = ("docs/reviews/", "docs/reference/")

# Default scan set when no file arguments are given.
DEFAULT_ROOTS = ("README.md", "CONTRIBUTING.md", "docs", ".claude", ".github")


def iter_default_files() -> list[Path]:
    files: list[Path] = []
    for root in DEFAULT_ROOTS:
        p = Path(root)
        if p.is_file() and p.suffix == ".md":
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
    return files


def is_exempt(path: Path) -> bool:
    posix = path.as_posix()
    return any(seg in posix for seg in EXEMPT_DIRS)


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: could not read ({exc})"]
    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            if ch in BANNED and len(ch) == 1:
                problems.append(f"{path}:{lineno}:{col}: banned character U+{ord(ch):04X} - {BANNED[ch]}")
    return problems


def main(argv: list[str]) -> int:
    if argv:
        files = [Path(a) for a in argv]
    else:
        files = iter_default_files()

    all_problems: list[str] = []
    for path in files:
        if is_exempt(path):
            continue
        all_problems.extend(check_file(path))

    if all_problems:
        print("Doc style check FAILED:\n")
        for p in all_problems:
            print("  " + p)
        print(f"\n{len(all_problems)} violation(s). See docs/process/05-documentation-standards.md.")
        return 1

    print(f"Doc style check passed ({len(files)} file(s) scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
