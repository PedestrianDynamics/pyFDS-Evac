"""Fail a pull request that changes golden data without re-record evidence (#810).

A change to a stored expected output under ``tests/`` (the artifacts of
``tests/golden/README.md``) needs a ``Golden re-record:`` section in the
pull-request body, as ``docs/TESTING_GUIDELINES.md`` §5 asks. This check
only sees that the section exists and is not empty; whether its argument
holds is for the reviewer.

Added, modified, renamed and deleted files all count. README files and
the Python scripts that build a baseline are not data and do not count.
A section counts only if it has text outside fenced code blocks; a rule
or other formatting alone is empty.

In CI::

    PR_BODY="$BODY" python scripts/check_golden_rerecord.py --base BASE --head HEAD
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

GUARDED = ("tests/golden/", "tests/verification/golden/", "tests/__snapshots__/")
GUARDED_FILES = ("tests/init_decks.tsv", "tests/init_deck_exits.json")
HEADING = "Golden re-record:"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE = re.compile(r"^\s*(```|~~~)")
_TEXT = re.compile(r"\w")
_SECTION = re.compile(r"^\s*(?:#{1,6}\s*)?\**" + re.escape(HEADING) + r"\**(.*)$")
_NEXT_HEADING = re.compile(r"^\s*#{1,6}\s")


def guarded(paths: list[str]) -> list[str]:
    """Return the changed paths that are golden or snapshot data."""
    return [
        path
        for path in paths
        if path in GUARDED_FILES
        or (path.startswith(GUARDED) and not path.endswith(("/README.md", ".py")))
    ]


def _prose_lines(body: str) -> list[str]:
    """*body* without HTML comments and fenced code blocks."""
    lines, fenced = [], False
    for line in _COMMENT.sub("", body).splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append(line)
    return lines


def has_section(body: str) -> bool:
    """Whether *body* has a non-empty ``Golden re-record:`` section."""
    lines = _prose_lines(body)
    for i, line in enumerate(lines):
        match = _SECTION.match(line)
        if not match:
            continue
        if _TEXT.search(match.group(1)):
            return True
        for following in lines[i + 1 :]:
            if _NEXT_HEADING.match(following):
                break
            if _TEXT.search(following):
                return True
    return False


def check(paths: list[str], body: str) -> list[str]:
    """Return the error lines for a pull request; empty means it passes."""
    data = guarded(paths)
    if not data or has_section(body):
        return []
    return [
        f"{len(data)} golden or snapshot file(s) changed without a "
        f"'{HEADING}' section in the pull-request body:",
        *(f"  {path}" for path in data),
        "Add the section with the evidence of docs/TESTING_GUIDELINES.md §5.",
    ]


def changed_paths(base: str, head: str) -> list[str]:
    """Paths changed between the merge base of *base* and *head*, and *head*."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [path for path in out.split("\0") if path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="base commit of the PR")
    parser.add_argument("--head", required=True, help="head commit of the PR")
    args = parser.parse_args(argv)
    errors = check(changed_paths(args.base, args.head), os.environ.get("PR_BODY", ""))
    for line in errors:
        print(line, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
