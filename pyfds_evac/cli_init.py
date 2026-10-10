"""``pyfds-evac init DECK.fds [-o DIR]``: start a scenario from an FDS deck.

Writes ``config.json``, ``geometry.wkt`` and ``import_report.json`` into DIR
(default: ``<deck stem>_scenario/`` next to the deck), prints the import
summary and the next steps: run FDS if its output is missing, run the
scenario, refine it in JuPedSim Web or the TUI. The summary includes the
check of the FDS output the run reads (slices, T_END); it never changes the
files or the exit status.

Exit status: 0 runnable; 3 written but not runnable (no exit, or no agents),
or runnable with an input dropped at error level (an exit, a spawn area); 1
the deck could not be imported, or an argument error (nothing written).

``pyfds-evac init DECK.fds --check`` checks the deck only, before FDS runs,
and writes nothing: exit 0 when the run will find the extinction, CO, CO2
and O2 slices and ``&TIME T_END``; 3 when one is missing; 1 when the deck
cannot be read or an argument is wrong.
"""

from __future__ import annotations

import argparse
import math
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
deck (no EVACUATION=.TRUE. mesh) gets exits from SURF_ID='OPEN' vents on the
outside of the meshes, &EVHO holes in its walkable area, and a placeholder of
100 agents unless --agents is given. Every approximation is
listed in import_report.json and on the screen."""

_EPILOG = """\
exit status: 0 runnable; 3 written, but not runnable or an input dropped
with an error; 1 error (nothing written)
with --check: 0 the deck has what the run reads; 3 a slice or T_END is
missing; 1 error (nothing is ever written)

examples:
  pyfds-evac init room.fds --check    # before running FDS: check the slices
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the deck for the slices and T_END the run reads, before "
        "running FDS; write nothing (exit 0 ready, 3 not ready)",
    )
    parser.add_argument(
        "--smoke-slice-height",
        type=float,
        metavar="Z",
        help="with --check: absolute height [m] to check the slices at "
        "(default: the one init writes, floor + HUMAN_SMOKE_HEIGHT or 1.6 m)",
    )
    return parser


#: Options that only shape the written scenario, so --check refuses them.
_WRITE_ONLY = (
    ("output", "-o/--output"),
    ("walkable", "--walkable"),
    ("exits", "--exit"),
    ("agents", "--agents"),
    ("exit_depth", "--exit-depth"),
    ("force", "--force"),
    ("no_fds", "--no-fds"),
    ("verbose", "-v/--verbose"),
)


def _check_combination(args: argparse.Namespace) -> str | None:
    """Why the options cannot go together, or None."""
    if not args.check:
        if args.smoke_slice_height is not None:
            return "--smoke-slice-height needs --check"
        return None
    height = args.smoke_slice_height
    if height is not None and not math.isfinite(height):
        return f"--smoke-slice-height must be a finite number, got {height}"
    given = [flag for name, flag in _WRITE_ONLY if _given(getattr(args, name))]
    if given:
        return f"--check writes nothing, so {', '.join(given)} cannot go with it"
    return None


def _given(value) -> bool:
    """Whether an option was passed: a set flag, a non-empty list, any value.

    Numbers count whatever their value, so ``--agents 0`` is given.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return bool(value)
    return value is not None


class _UsageError(Exception):
    """An argument error, reported with exit status 1 instead of argparse's 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise _UsageError(f"{self.format_usage()}{self.prog}: error: {message}")


def main(argv: list[str] | None = None) -> int:
    """Run the init subcommand; returns the exit status."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        print(exc, file=sys.stderr)
        return EXIT_ERROR
    problem = _check_combination(args)
    if problem is not None:
        print(
            f"{parser.format_usage()}{parser.prog}: error: {problem}", file=sys.stderr
        )
        return EXIT_ERROR
    if args.check:
        return _check_only(args)
    if args.output is None:
        args.output = str(default_output(args.deck))
    from pyfds_evac.core.fds_import import (
        EXIT_DEPTH_M,
        check_output_folder,
        import_fds_deck,
    )

    slices: list[str] = []
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
            exit_depth=EXIT_DEPTH_M if args.exit_depth is None else args.exit_depth,
            on_slice_check=lambda check: slices.extend(check.lines(compact=True)),
        )
    except (ValueError, OSError) as exc:
        if slices:
            _emit(slices)
            sys.stdout.flush()
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
    _emit(summary_lines(result, args.output, args.no_fds, args.verbose, slices))
    return _status(result.report)


def _check_only(args: argparse.Namespace) -> int:
    """``init --check``: the deck's slice check, nothing written."""
    from pyfds_evac.core.fds_import import check_fds_deck

    try:
        check = check_fds_deck(
            args.deck,
            floor=args.floor,
            floor_z=args.floor_z,
            z_band=tuple(args.z_band) if args.z_band else None,
            smoke_slice_height=args.smoke_slice_height,
        )
    except (ValueError, OSError) as exc:
        print(f"pyfds-evac init: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    lines = check.lines()
    failed = len(check.failed)
    if failed:
        lines.append(
            f"✗ {failed} item{'s' if failed != 1 else ''} missing: the deck is "
            "not ready for a pyFDS-Evac run; fix it before running FDS."
        )
    else:
        lines.append("✓ The deck has what a pyFDS-Evac run reads.")
    _emit(lines)
    return EXIT_NOT_RUNNABLE if failed else EXIT_OK


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
        for fancy, plain in (
            ("→", "->"),
            ("✗", "x"),
            ("✓", "+"),
            ("·", "-"),
            ("²", "2"),
            ("…", "..."),
        ):
            text = text.replace(fancy, plain)
        print(text.encode("ascii", "replace").decode("ascii"))


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()
