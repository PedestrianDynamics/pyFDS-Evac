"""Read an FDS input deck into namelist records.

FDS reads its input as Fortran namelists, and so does this module:

- a record starts at ``&NAME`` as the first non-blank text of a line and
  ends at the first ``/`` outside quotes; text outside records is a
  comment, so a record may span lines and anything after ``/`` is ignored;
- values are separated by commas and/or whitespace (``XB= 0,40 0,20, 0,4``);
- strings take ``'`` or ``"``; logicals are ``.TRUE.``/``.FALSE.``/``T``/``F``;
  ``n*v`` repeats ``v`` n times; keys are case-insensitive;
- a repeated key keeps the last value, with a warning.

``MULT_ID`` on ``&MESH``, ``&OBST``, ``&HOLE`` and ``&VENT`` is expanded into
copies. ``&CATF`` (included files) is an error; ``&GEOM`` is kept with a
warning, since the importer does not represent unstructured solids.

Only the standard library is used, so the parser is cheap to import.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

#: Groups whose ``MULT_ID`` is expanded.
MULT_GROUPS = frozenset({"MESH", "OBST", "HOLE", "VENT"})
#: Groups whose ``DEVC_ID``/``CTRL_ID`` makes the solid time-dependent.
_CONTROLLED_GROUPS = frozenset({"OBST", "HOLE", "VENT"})

_RECORD_START = re.compile(r"^[ \t]*&([A-Za-z][A-Za-z0-9_]*)", re.MULTILINE)
_TOKEN = re.compile(
    r"""(?P<str>'[^']*'|"[^"]*")"""
    r"""|(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?)\s*="""
    r"""|(?P<sep>[\s,]+)"""
    r"""|(?P<val>[^\s,'"=]+)"""
)
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$")
_REPEAT = re.compile(r"^(\d+)\*(.+)$")
_TRUE = {".TRUE.", "T", ".T.", "TRUE"}
_FALSE = {".FALSE.", "F", ".F.", "FALSE"}


class FdsDeckError(ValueError):
    """The deck cannot be read; the message names the record and line."""


@dataclass(frozen=True)
class DeckIssue:
    """A parser warning tied to one record."""

    group: str
    id: str | None
    line: int
    message: str
    status: str = "A"


@dataclass(frozen=True)
class NamelistRecord:
    """One ``&GROUP ... /`` record; ``params`` maps upper-case keys to lists."""

    group: str
    params: dict[str, list[Any]]
    line: int
    copy_index: int | None = None

    @property
    def id(self) -> str | None:
        value = self.value("ID")
        return None if value is None else str(value)

    def has(self, key: str) -> bool:
        return key.upper() in self.params

    def values(self, key: str) -> list[Any]:
        return list(self.params.get(key.upper(), []))

    def value(self, key: str, default: Any = None) -> Any:
        values = self.params.get(key.upper())
        if not values:
            return default
        return values[0] if len(values) == 1 else list(values)

    def number(self, key: str, default: float | None = None) -> float | None:
        value = self.value(key)
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FdsDeckError(
                f"&{self.group} {self.label} (line {self.line}): "
                f"{key.upper()} must be one number, got {value!r}"
            )
        return float(value)

    def text(self, key: str, default: str | None = None) -> str | None:
        value = self.value(key)
        return default if value is None else str(value)

    def flag(self, key: str, default: bool | None = None) -> bool | None:
        value = self.value(key)
        if value is None:
            return default
        if not isinstance(value, bool):
            raise FdsDeckError(
                f"&{self.group} {self.label} (line {self.line}): "
                f"{key.upper()} must be a logical, got {value!r}"
            )
        return value

    def xb(self) -> tuple[float, float, float, float, float, float] | None:
        """``XB`` as (x0, x1, y0, y1, z0, z1), each axis pair sorted."""
        values = self.values("XB")
        if not values:
            return None
        if len(values) != 6 or not all(_is_number(v) for v in values):
            raise FdsDeckError(
                f"&{self.group} {self.label} (line {self.line}): "
                f"XB needs six numbers, got {values!r}"
            )
        x0, x1, y0, y1, z0, z1 = (float(v) for v in values)
        return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), *_sorted(z0, z1))

    def box6(self) -> tuple[float, float, float, float, float, float]:
        """:meth:`xb` for a record that must have one."""
        xb = self.xb()
        if xb is None:
            raise FdsDeckError(
                f"&{self.group} {self.label} (line {self.line}): XB is required"
            )
        return xb

    def num(self, key: str, default: float) -> float:
        """:meth:`number` with a default, so never None."""
        value = self.number(key, default)
        return default if value is None else value

    @property
    def label(self) -> str:
        return repr(self.id) if self.id is not None else "(no ID)"


@dataclass(frozen=True)
class FdsDeck:
    """A parsed deck: its records in file order and the parser's warnings."""

    path: Path | None
    records: tuple[NamelistRecord, ...]
    issues: tuple[DeckIssue, ...] = field(default_factory=tuple)

    def group(self, name: str) -> list[NamelistRecord]:
        upper = name.upper()
        return [r for r in self.records if r.group == upper]

    def first(self, name: str) -> NamelistRecord | None:
        found = self.group(name)
        return found[0] if found else None

    @property
    def chid(self) -> str | None:
        head = self.first("HEAD")
        return None if head is None else head.text("CHID")


def parse_fds_deck(path: str | Path) -> FdsDeck:
    """Parse the FDS deck at *path*."""
    deck_path = Path(path)
    try:
        text = deck_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FdsDeckError(f"cannot read FDS deck {deck_path}: {exc}") from exc
    return parse_fds_text(text, path=deck_path)


def parse_fds_text(text: str, path: Path | None = None) -> FdsDeck:
    """Parse deck *text*; *path* is kept for messages and the provider."""
    issues: list[DeckIssue] = []
    records = [_read_record(text, m, issues) for m in _RECORD_START.finditer(text)]
    records = [r for r in records if r is not None]
    _check_unsupported(records, issues)
    expanded = _expand_mult(records)
    return FdsDeck(path=path, records=tuple(expanded), issues=tuple(issues))


def _read_record(text: str, match: re.Match, issues: list[DeckIssue]):
    group = match.group(1).upper()
    line = text.count("\n", 0, match.start()) + 1
    body_start = match.end()
    end = _record_end(text, body_start)
    if end is None:
        raise FdsDeckError(f"&{group} (line {line}): no closing '/' found")
    if group == "TAIL":
        return None
    params = _parse_body(text[body_start:end], group, line, issues)
    return NamelistRecord(group=group, params=params, line=line)


def _record_end(text: str, start: int) -> int | None:
    quote = None
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "/":
            return index
    return None


def _parse_body(body: str, group: str, line: int, issues: list[DeckIssue]):
    params: dict[str, list[Any]] = {}
    key: str | None = None
    for token in _TOKEN.finditer(body):
        kind = token.lastgroup or "sep"
        if kind == "sep":
            continue
        if kind == "key":
            key = re.sub(r"\s+", "", token.group("key")).upper()
            _start_key(params, key, group, line, issues)
            continue
        if key is None:
            continue
        params[key].extend(_convert(token.group(kind), kind))
    return params


def _start_key(params, key, group, line, issues) -> None:
    if key in params:
        record_id = _scalar(params.get("ID"))
        issues.append(
            DeckIssue(group, record_id, line, f"{key} given twice; the last wins")
        )
    params[key] = []


def _scalar(values: list[Any] | None) -> str | None:
    return None if not values else str(values[0])


def _convert(raw: str, kind: str) -> list[Any]:
    if kind == "str":
        return [raw[1:-1]]
    repeat = _REPEAT.match(raw)
    if repeat:
        return [_atom(repeat.group(2))] * int(repeat.group(1))
    return [_atom(raw)]


def _atom(raw: str) -> Any:
    upper = raw.upper()
    if upper in _TRUE:
        return True
    if upper in _FALSE:
        return False
    if not _NUMBER.match(raw):
        return raw
    value = float(upper.replace("D", "E"))
    return (
        int(value)
        if value.is_integer() and "." not in raw and "E" not in upper
        else value
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _sorted(a: float, b: float) -> tuple[float, float]:
    return (a, b) if a <= b else (b, a)


def _check_unsupported(records: list[NamelistRecord], issues: list[DeckIssue]):
    for record in records:
        if record.group == "CATF":
            files = record.values("OTHER_FILES")
            raise FdsDeckError(
                f"&CATF (line {record.line}): included files are not supported "
                f"({', '.join(map(str, files)) or 'no OTHER_FILES'}); "
                "concatenate them into one deck first"
            )
        issue = _record_issue(record)
        if issue:
            issues.append(DeckIssue(record.group, record.id, record.line, *issue))


def _record_issue(record: NamelistRecord) -> tuple[str, str] | None:
    if record.group == "GEOM":
        return "unstructured &GEOM solid not represented", "D"
    if record.group not in _CONTROLLED_GROUPS:
        return None
    if record.has("DEVC_ID") or record.has("CTRL_ID"):
        return "controlled by DEVC_ID/CTRL_ID; taken as written in the deck", "A"
    return None


# --- MULT ------------------------------------------------------------------

_MULT_IJK = {"DX", "DY", "DZ", "I_LOWER", "I_UPPER", "J_LOWER", "J_UPPER"}
_MULT_IJK |= {"K_LOWER", "K_UPPER"}
_MULT_N = {"N_LOWER", "N_UPPER", "DXB"}
_MULT_COMMON = {"ID", "FYI", "DX0", "DY0", "DZ0"}


def _expand_mult(records: list[NamelistRecord]) -> list[NamelistRecord]:
    mults = {r.id: r for r in records if r.group == "MULT" and r.id is not None}
    out: list[NamelistRecord] = []
    for record in records:
        if record.group not in MULT_GROUPS or not record.has("MULT_ID"):
            out.append(record)
            continue
        out.extend(_copies(record, _mult_for(record, mults)))
    return out


def _mult_for(record: NamelistRecord, mults: dict) -> NamelistRecord:
    mult_id = record.text("MULT_ID")
    if mult_id not in mults:
        raise FdsDeckError(
            f"&{record.group} {record.label} (line {record.line}): "
            f"MULT_ID {mult_id!r} names no &MULT record"
        )
    return mults[mult_id]


def _copies(record: NamelistRecord, mult: NamelistRecord) -> list[NamelistRecord]:
    """Shifted copies of *record*, as FDS makes them."""
    if record.xb() is None:
        raise FdsDeckError(
            f"&{record.group} {record.label} (line {record.line}): "
            "MULT_ID needs XB on the record"
        )
    shifts = _mult_shifts(record, mult)
    base = record.values("XB")
    out = []
    for index, shift in enumerate(shifts):
        params = dict(record.params)
        params["XB"] = [float(v) + s for v, s in zip(base, shift, strict=True)]
        out.append(replace(record, params=params, copy_index=index))
    return out


def _mult_shifts(record: NamelistRecord, mult: NamelistRecord) -> list[tuple]:
    keys = set(mult.params)
    unknown = keys - _MULT_IJK - _MULT_N - _MULT_COMMON
    uses_n = bool(keys & _MULT_N)
    if unknown or (uses_n and keys & _MULT_IJK):
        raise FdsDeckError(
            f"&{record.group} {record.label} (line {record.line}): unsupported "
            f"&MULT {mult.label} form (line {mult.line}); supported are "
            "DX0/DY0/DZ0 with either DX/DY/DZ and I/J/K_LOWER/UPPER, or "
            "N_LOWER/N_UPPER with DXB"
        )
    x0, y0, z0 = (mult.num(k, 0.0) for k in ("DX0", "DY0", "DZ0"))
    if uses_n:
        return _n_shifts(record, mult, (x0, y0, z0))
    return _ijk_shifts(mult, (x0, y0, z0))


def _ijk_shifts(mult: NamelistRecord, origin: tuple) -> list[tuple]:
    x0, y0, z0 = origin
    dx, dy, dz = (mult.num(k, 0.0) for k in ("DX", "DY", "DZ"))
    ranges = [
        range(int(mult.num(f"{a}_LOWER", 0)), int(mult.num(f"{a}_UPPER", 0)) + 1)
        for a in "KJI"
    ]
    shifts = []
    for k, j, i in itertools.product(*ranges):
        sx, sy, sz = x0 + i * dx, y0 + j * dy, z0 + k * dz
        shifts.append((sx, sx, sy, sy, sz, sz))
    return shifts


def _n_shifts(record: NamelistRecord, mult: NamelistRecord, origin: tuple):
    dxb = [float(v) for v in mult.values("DXB")] or [0.0] * 6
    if len(dxb) != 6:
        raise FdsDeckError(
            f"&{record.group} {record.label} (line {record.line}): "
            f"&MULT {mult.label} DXB needs six numbers"
        )
    x0, y0, z0 = origin
    lo, hi = int(mult.num("N_LOWER", 0)), int(mult.num("N_UPPER", 0))
    base = (x0, x0, y0, y0, z0, z0)
    return [
        tuple(b + n * d for b, d in zip(base, dxb, strict=True))
        for n in range(lo, hi + 1)
    ]
