"""``pyfds-evac import DECK.fds -o DIR``: start a scenario from an FDS deck.

Writes ``config.json``, ``geometry.wkt`` and ``import_report.json`` into DIR,
prints the import summary and the command that runs the scenario.

Exit status: 0 runnable; 3 written but not runnable (no exit, or no agents);
1 the deck could not be imported (nothing written).
"""

from __future__ import annotations

import argparse
import sys

from rich_argparse import RawDescriptionRichHelpFormatter

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_RUNNABLE = 3

_DESCRIPTION = """\
Start a pyFDS-Evac scenario from an FDS deck. An FDS+Evac deck keeps its
&EXIT, &DOOR, &EVAC, &EVHO, &ENTR and &PERS records (one floor). A plain FDS
deck gets exits from SURF_ID='OPEN' vents on the outside of the meshes, and a
placeholder of 100 agents unless --agents is given. Every approximation is
listed in import_report.json and on the screen."""

_EPILOG = """\
exit status: 0 runnable, 3 written but not runnable, 1 error (nothing written)

examples:
  pyfds-evac import room.fds -o room_scenario/
  pyfds-evac import room.fds -o room_scenario/ --walkable room.wkt --agents 40
  pyfds-evac import room.fds -o out/ --exit 0,4.4,0,5.6,-1"""


def _exit_spec(text: str) -> tuple[float, ...]:
    try:
        values = tuple(float(v) for v in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from exc
    if len(values) not in (4, 5):
        raise argparse.ArgumentTypeError(f"need x0,y0,x1,y1[,ior], got {text!r}")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfds-evac import",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=RawDescriptionRichHelpFormatter,
    )
    parser.add_argument("deck", help="the FDS input file (.fds)")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="DIR",
        help="directory for config.json, geometry.wkt, import_report.json",
    )
    parser.add_argument(
        "--walkable",
        metavar="FILE.wkt",
        help="use this walkable area instead of deriving it from the deck",
    )
    parser.add_argument(
        "--floor",
        metavar="MESH_ID",
        help="FDS+Evac deck: import the floor of this evacuation mesh "
        "(default: the lowest floor)",
    )
    parser.add_argument(
        "--floor-z",
        type=float,
        metavar="Z",
        help="plain FDS deck: floor level [m] (default: lowest mesh z)",
    )
    parser.add_argument(
        "--z-band",
        type=float,
        nargs=2,
        metavar=("LO", "HI"),
        help="absolute height band [m] whose obstructions block walking",
    )
    parser.add_argument(
        "--agents",
        type=int,
        metavar="N",
        help="plain FDS deck: number of agents (default: a flagged placeholder of 100)",
    )
    parser.add_argument(
        "--exit",
        action="append",
        type=_exit_spec,
        default=[],
        dest="exits",
        metavar="x0,y0,x1,y1[,ior]",
        help="add an exit line (repeatable); ior as in FDS &EXIT",
    )
    parser.add_argument(
        "--exit-depth",
        type=float,
        default=0.5,
        metavar="D",
        help="depth of an exit strip on the room side [m] (default 0.5)",
    )
    parser.add_argument(
        "--layer-rules",
        choices=("none", "station"),
        default="none",
        help="obstruction layer rules of the walkable derivation; "
        "'station' treats the Station deck's floor/door layers as free",
    )
    parser.add_argument(
        "--no-fds",
        action="store_true",
        help="leave --fds-dir out of the run command even when "
        "<CHID>.smv is next to the deck",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the import subcommand; returns the exit status."""
    args = build_parser().parse_args(argv)
    from pyfds_evac.core.fds_import import import_fds_deck

    try:
        walkable = None if args.walkable is None else _read(args.walkable)
        result = import_fds_deck(
            args.deck,
            floor=args.floor,
            floor_z=args.floor_z,
            z_band=tuple(args.z_band) if args.z_band else None,
            walkable_wkt=walkable,
            agents=args.agents,
            exits=args.exits,
            exit_depth=args.exit_depth,
            layer_rules=args.layer_rules,
        )
    except (ValueError, OSError) as exc:
        print(f"pyfds-evac import: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.no_fds:
        result.report.recommendations["fds_dir"] = None
    result.write(args.output)
    print(result.report.summary_text())
    _announce_fds(result.report.recommendations, args.no_fds)
    print(f"Wrote {args.output}/config.json, geometry.wkt, import_report.json")
    print(f"Run: {result.run_command(args.output)}")
    return EXIT_OK if result.report.runnable else EXIT_NOT_RUNNABLE


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _announce_fds(rec: dict, opted_out: bool) -> None:
    found = rec.get("fds_output_found")
    if not found:
        print("FDS output: none next to the deck; the run command is clear air.")
        return
    if rec.get("fds_dir"):
        print(
            f"FDS OUTPUT FOUND: {found}. The run command uses --fds-dir "
            f"{rec['fds_dir']}, so the run includes the fire; pass --no-fds to "
            "leave it out."
        )
        return
    reason = "--no-fds given" if opted_out else rec.get("fds_dir_note", "")
    print(f"FDS OUTPUT FOUND: {found}, not used ({reason}).")
