#!/usr/bin/env python3
"""Validate relative Markdown links point at files that exist.

Catches the classic doc-rot bug: a link to docs/process/06-review-guidelines.md
that no longer exists after a rename. External links (http, https, mailto) and
pure in-page anchors (#heading) are not checked. A link with an anchor
(file.md#section) is validated against the file part only.

Usage:
    python3 scripts/check_doc_links.py                # scan the default set
    python3 scripts/check_doc_links.py a.md docs/b.md # scan specific files

Exit code 0 if all links resolve, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
DEFAULT_ROOTS = (
    "README.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md",
    "SECURITY.md", "CHANGELOG.md", "docs", ".claude", ".github",
)
EXEMPT_DIRS = ("docs/reviews/", "docs/reference/")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")


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
        for target in LINK_RE.findall(line):
            target = target.strip()
            if target.startswith(SKIP_PREFIXES) or not target:
                continue
            file_part = target.split("#", 1)[0]
            if not file_part:  # was a pure anchor
                continue
            resolved = (path.parent / file_part).resolve()
            if not resolved.exists():
                problems.append(f"{path}:{lineno}: broken link -> {target}")
    return problems


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] if argv else iter_default_files()
    problems: list[str] = []
    for path in files:
        if is_exempt(path):
            continue
        problems.extend(check_file(path))
    if problems:
        print("Doc link check FAILED:\n")
        for p in problems:
            print("  " + p)
        print(f"\n{len(problems)} broken link(s).")
        return 1
    print(f"Doc link check passed ({len(files)} file(s) scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
