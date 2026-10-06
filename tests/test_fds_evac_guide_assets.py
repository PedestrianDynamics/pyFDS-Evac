"""The FDS+Evac guide decks in ``assets/fds_evac_guide/`` stay unmodified.

The decks are GPL-3.0-only and copied byte for byte from
tkorhon1/FDS-Evac-Guide; ``SHA256SUMS`` was computed from that repository at
the pinned commit, not from the copy. A changed, added or removed deck fails
here: a modified deck belongs in a new location with a modification notice
(GPLv3 section 5), see ``assets/fds_evac_guide/README.md``.
"""

import hashlib
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[1] / "assets" / "fds_evac_guide"


def _manifest() -> dict[str, str]:
    lines = (GUIDE / "SHA256SUMS").read_text().splitlines()
    return {name: digest for digest, name in (line.split("  ", 1) for line in lines)}


def test_guide_deck_set_matches_manifest():
    on_disk = {p.relative_to(GUIDE).as_posix() for p in GUIDE.rglob("*.fds")}
    assert on_disk == set(_manifest())


def test_guide_decks_are_unmodified():
    changed = [
        name
        for name, digest in _manifest().items()
        if hashlib.sha256((GUIDE / name).read_bytes()).hexdigest() != digest
    ]
    assert changed == []
