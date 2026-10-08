"""``pyfds-evac init DECK.fds [-o DIR]``: start a scenario from an FDS deck.

Writes ``config.json``, ``geometry.wkt`` and ``import_report.json`` into DIR
(default: ``<deck stem>_scenario/`` next to the deck), prints the import
summary and the next steps: run FDS if its output is missing, run the
scenario, refine it in JuPedSim Web or the TUI.

Exit status: 0 runnable; 3 written but not runnable (no exit, or no agents),
or runnable with an input dropped at error level (an exit, a spawn area); 1
the deck could not be imported, or an argument error (nothing written).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from pyfds_evac.init_summary import summary_lines

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
exit status: 0 runnable; 3 written, but not runnable or an input dropped
with an error; 1 error (nothing written)

examples:
  pyfds-evac init room.fds            # writes room_scenario/ next to room.fds
  pyfds-evac init room.fds --walkable room.wkt --agents 40
  pyfds-evac init room.fds -o out/ --exit 0,4.4,0,5.6,-1"""


def _exit_spec(text: str) -> tuple[float, ...]:
    try:
        values = tuple(float(v) for v in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not numbers: {text!r}") from exc
    if len(values) not in (4, 5):
        raise argparse.ArgumentTypeError(f"need x0,y0,x1,y1[,ior], got {text!r}")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="pyfds-evac init",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=RawDescriptionRichHelpFormatter,
    )
    parser.add_argument("deck", help="the FDS input file (.fds)")
    parser.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        help="directory for config.json, geometry.wkt, import_report.json "
        "(default: <deck stem>_scenario/ next to the deck)",
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
        "--force",
        action="store_true",
        help="overwrite a config.json in the -o folder that the importer did not write",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print every line of the import report, not the summary",
    )
    parser.add_argument(
        "--no-fds",
        action="store_true",
        help="leave --fds-dir out of the run command even when "
        "<CHID>.smv is next to the deck",
    )
    return parser


class _UsageError(Exception):
    """An argument error, reported with exit status 1 instead of argparse's 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise _UsageError(f"{self.format_usage()}{self.prog}: error: {message}")


def main(argv: list[str] | None = None) -> int:
    """Run the init subcommand; returns the exit status."""
    try:
        args = build_parser().parse_args(argv)
    except _UsageError as exc:
        print(exc, file=sys.stderr)
        return EXIT_ERROR
    if args.output is None:
        args.output = str(default_output(args.deck))
    from pyfds_evac.core.fds_import import check_output_folder, import_fds_deck

    try:
        check_output_folder(args.output, force=args.force)
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
        )
    except (ValueError, OSError) as exc:
        print(f"pyfds-evac init: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.no_fds:
        result.report.recommendations["fds_dir"] = None
    try:
        result.write(args.output)
    except OSError as exc:
        print(
            f"pyfds-evac init: error: cannot write {args.output}: {exc}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    _emit(summary_lines(result, args.output, args.no_fds, args.verbose))
    return _status(result.report)


def default_output(deck: str) -> Path:
    """``<deck stem>_scenario/`` next to the deck."""
    path = Path(deck)
    return path.with_name(f"{path.stem}_scenario")


def _status(report) -> int:
    """0 runnable and clean; 3 not runnable or an input dropped as error."""
    if not report.runnable or report.errors:
        return EXIT_NOT_RUNNABLE
    return EXIT_OK


def _emit(lines: list[str]) -> None:
    """Print, falling back to ASCII on a console that cannot encode UTF-8."""
    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        for fancy, plain in (("→", "->"), ("✗", "x"), ("²", "2"), ("…", "...")):
            text = text.replace(fancy, plain)
        print(text.encode("ascii", "replace").decode("ascii"))


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()
