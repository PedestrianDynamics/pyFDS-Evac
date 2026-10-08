#!/usr/bin/env python3
"""Write the walkable area of an FDS deck as WKT.

A thin wrapper around the deck importer: it writes the polygon that
``pyfds-evac init`` writes to ``geometry.wkt``. The rule is in
``pyfds_evac/core/walkable_provider.py``: the union of the floor's mesh
footprints, its edge a wall, minus the ``&OBST`` records (less their
``&HOLE`` cuts) in the walking band; the components that hold a spawn area,
or without one an exit, are kept.

Usage:
    uv run python scripts/generate_walkable_from_fds.py DECK.fds -o out.wkt \
        [--z-band 0.1 1.8]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyfds_evac.core.fds_import import import_fds_deck


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("deck", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument(
        "--z-band",
        nargs=2,
        type=float,
        default=None,
        metavar=("LO", "HI"),
        help="absolute height band an upright occupant occupies [m] (default: "
        "the evacuation mesh slab, or 0.1 1.8 m above the lowest mesh)",
    )
    args = parser.parse_args(argv)
    band = tuple(args.z_band) if args.z_band else None
    try:
        result = import_fds_deck(args.deck, z_band=band)
    except (ValueError, OSError) as exc:
        print(f"{args.deck}: {exc}", file=sys.stderr)
        return 1
    args.out.write_text(result.walkable_wkt + "\n", encoding="utf-8")
    walkable = result.report.walkable
    print(
        f"{args.deck.name}: walkable {walkable['area_m2']} m2, "
        f"{walkable['components']} component(s), {walkable['holes']} hole(s)"
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
