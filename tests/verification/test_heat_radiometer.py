"""L3 radiometer validation decks for the heat dose (#224, spec 016).

These tests define "done" for #224. They check the FDS decks under
``assets/heat_radiometer`` and, when the FDS output is available, the output
itself. Nothing here uses the heat model in ``pyfds_evac.core.fed``; every
expected value comes from the FDS User's Guide 6.10.1 or from radiation
geometry, written out below.

Decks, told apart by content, not by file name:

- **hot layer**: an adiabatic room with a hot, sooty upper layer set by
  ``&INIT`` above head height and no fire. Clear hot air is almost
  transparent in FDS, so without soot the "layer" only heats the ceiling.
- **uniform control**: the whole room hot and sooty. Its radiation field is
  isotropic, which anchors the U/4 end of the range.
- **burner**: a fire in view of the devices, for the q -> U end.

Device layout each deck must have (spec 016, L3):

- ``GAUGE HEAT FLUX GAS`` and ``RADIOMETER GAS`` arrays (``POINTS``,
  ``TIME_HISTORY=T``) at z = 1.6 and 1.8 m, facing up (0, 0, 1) and sideways
  (a horizontal ``ORIENTATION``), with a ``&PROP`` that sets
  ``GAUGE_TEMPERATURE=35`` (skin) and ``HEAT_TRANSFER_COEFFICIENT=8`` as in
  the issue, and leaves ``GAUGE_EMISSIVITY`` at 1. The radiometer uses the
  same gauge temperature, so the two differ by convection only.
- ``TEMPERATURE`` and ``INTEGRATED INTENSITY`` arrays at the same points,
  for Eq. 22.35 and for the ratio q/U.
- ``INTEGRATED INTENSITY`` slices at 1.6 and 1.8 m, on a z-grid with cell
  faces at both heights so neither slice is moved to another height.

Relations used (FDS User's Guide 6.10.1, Sec. 22.10.12; T in K):

- Eq. 22.35: gauge = eps (q_inc - sigma T_gauge^4) + h (T_g - T_gauge).
- Eq. 22.36: radiometer = eps (q_inc - sigma T_gauge^4).
- With eps = 1 the incident flux is q_inc = radiometer + sigma T_gauge^4,
  and gauge - radiometer = h (T_g - T_gauge).
- U = integral of I over all directions; a flat plate receives
  q = integral over its hemisphere of I cos(theta), so 0 <= q <= U, and two
  opposite plates together receive at most U.
- Isotropic field: q = pi I, U = 4 pi I, q/U = 1/4; black enclosure at T:
  U = 4 sigma T^4.
- Uniform upper hemisphere, nothing below: q/U = 1/2 for a plate facing up.
  A compact source seen face-on: q/U -> 1.

The FDS output is not in the repository. The output tests look for
``<CHID>_devc.csv`` under ``$HEAT_RADIOMETER_DATA`` or the project's data
folder ``fds-evac-data/heat_radiometer`` and skip when it is not there.

Tolerances. The CSV carries 8 significant digits, so Eq. 22.35 holds to
1e-5 kW/m2 (measured residual 1e-7 in a calibration run). The ray effect of
the 100 default radiation angles moved q/U in an isotropic 300 C sooty room
by up to 5 % from 1/4 and U by up to 3 % from 4 sigma T^4 (tester calibration
run, 4 x 4 x 3 m, 0.2 m cells); the bands below are twice that.
"""

from __future__ import annotations

import csv
import importlib.util
import os
import re
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
DECK_DIR = REPO / "assets" / "heat_radiometer"
SCRIPT = REPO / "scripts" / "verification" / "heat_radiometer.py"
SCIEBO = Path(
    "/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
)
DATA_ROOT = Path(
    os.environ.get("HEAT_RADIOMETER_DATA", SCIEBO / "fds-evac-data" / "heat_radiometer")
)

SIGMA = 5.670374419e-8  # W m^-2 K^-4, CODATA 2018
T_SKIN_C = 35.0  # GAUGE_TEMPERATURE, issue #224
H_GAUGE = 8.0  # HEAT_TRANSFER_COEFFICIENT, issue #224
HEIGHTS = (1.6, 1.8)
EQ_22_35_ABS = 1e-5  # kW/m2
ISO_BAND = 0.1  # relative, around 1/4 and 4 sigma T^4
BOUND_BAND = 0.1  # relative slack on q <= U for the ray effect
T_SETTLE = 1.0  # s; FDS writes the first radiation solution after t = 0

pending = pytest.mark.xfail(strict=True, reason="#224")


# --- FDS namelist reading (independent of pyFDS-Evac) ----------------------

_NAMELIST = re.compile(r"&(\w+)\b(.*?)/", re.S)
_KEY = re.compile(r"([A-Za-z_][\w]*(?:\([\d:,]+\))?)\s*=")


def _value(text: str):
    text = text.strip().rstrip(",").strip()
    items = [s.strip() for s in re.findall(r"'[^']*'|\"[^\"]*\"|[^,]+", text)]
    out = []
    for s in items:
        if not s:
            continue
        if s[0] in "'\"":
            out.append(s[1:-1])
        elif s.upper() in (".TRUE.", "T", ".T."):
            out.append(True)
        elif s.upper() in (".FALSE.", "F", ".F."):
            out.append(False)
        else:
            try:
                out.append(float(s))
            except ValueError:
                out.append(s)
    return out[0] if len(out) == 1 else out


def _parse(text: str) -> list[tuple[str, dict]]:
    """Return (group, params) for each namelist in a deck."""
    # Quoted strings may contain '/', which ends a namelist; mask them first.
    masked = re.sub(r"'[^']*'", lambda m: m.group(0).replace("/", "\0"), text)
    groups = []
    for m in _NAMELIST.finditer(masked):
        body = m.group(2).replace("\0", "/")
        keys = list(_KEY.finditer(body))
        params = {}
        for k, nxt in zip(keys, keys[1:] + [None]):
            end = nxt.start() if nxt else len(body)
            params[k.group(1).upper()] = _value(body[k.end() : end])
        groups.append((m.group(1).upper(), params))
    return groups


def _decks() -> dict[Path, list[tuple[str, dict]]]:
    if not DECK_DIR.is_dir():
        return {}
    return {p: _parse(p.read_text()) for p in sorted(DECK_DIR.glob("*.fds"))}


def _all(nml, group):
    return [p for g, p in nml if g == group]


def _floats(v):
    return [float(x) for x in (v if isinstance(v, list) else [v])]


def _domain(nml):
    xbs = np.array([_floats(m["XB"]) for m in _all(nml, "MESH")])
    return (
        xbs[:, 0].min(),
        xbs[:, 1].max(),
        xbs[:, 2].min(),
        xbs[:, 3].max(),
        xbs[:, 4].min(),
        xbs[:, 5].max(),
    )


def _has_fire(nml):
    return bool(_all(nml, "REAC")) or any("HRRPUA" in s for s in _all(nml, "SURF"))


def _hot_inits(nml):
    tmpa = float(next((m.get("TMPA", 20.0) for m in _all(nml, "MISC")), 20.0))
    return [
        i
        for i in _all(nml, "INIT")
        if "XB" in i and float(i.get("TEMPERATURE", tmpa)) > tmpa
    ]


def _is_sooty(nml, init):
    soot = {
        s["ID"]
        for s in _all(nml, "SPEC")
        if str(s.get("RADCAL_ID", "")).upper() == "SOOT"
        or str(s.get("ID", "")).upper() == "SOOT"
    }
    ids = [v for k, v in init.items() if k.startswith("SPEC_ID")]
    ids = [x for v in ids for x in (v if isinstance(v, list) else [v])]
    return bool(soot & set(ids))


def _kind(nml) -> str | None:
    if _has_fire(nml):
        return "burner"
    x0, x1, y0, y1, z0, z1 = _domain(nml)
    for i in _hot_inits(nml):
        xb = _floats(i["XB"])
        if xb[4] > max(HEIGHTS):
            return "hot_layer"
        if np.allclose(xb, [x0, x1, y0, y1, z0, z1]):
            return "uniform"
    return None


def _deck(kind):
    for path, nml in _decks().items():
        if _kind(nml) == kind:
            return path, nml
    pytest.fail(f"no {kind} deck in {DECK_DIR.relative_to(REPO)}")


def _prop(nml, prop_id):
    return next((p for p in _all(nml, "PROP") if p.get("ID") == prop_id), {})


def _arrays(nml, quantity):
    """DEVC arrays of a quantity: (devc, z, unit orientation)."""
    out = []
    for d in _all(nml, "DEVC"):
        if str(d.get("QUANTITY", "")).upper() != quantity:
            continue
        xbp = _floats(d.get("XBP", [np.nan] * 6))
        o = np.array(_floats(d.get("ORIENTATION", [0.0, 0.0, 1.0])))
        out.append((d, xbp, o / np.linalg.norm(o)))
    return out


def _is_up(o):
    return np.allclose(o, [0, 0, 1])


def _is_side(o):
    return abs(o[2]) < 1e-9


# --- Static checks on the decks --------------------------------------------


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
def test_deck_exists(kind):
    _deck(kind)


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform"])
def test_room_is_adiabatic_on_all_six_faces(kind):
    _, nml = _deck(kind)
    adiabatic = {s["ID"] for s in _all(nml, "SURF") if s.get("ADIABATIC") is True}
    default = any(
        s.get("DEFAULT") is True and s.get("ADIABATIC") is True
        for s in _all(nml, "SURF")
    )
    faces = {
        str(v["MB"]).upper()
        for v in _all(nml, "VENT")
        if "MB" in v and v.get("SURF_ID") in adiabatic
    }
    assert default or faces == {"XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"}


@pending
def test_hot_layer_is_above_the_heads_and_sooty():
    """A clear layer is nearly transparent: it must hold an absorbing species."""
    _, nml = _deck("hot_layer")
    layers = [i for i in _hot_inits(nml) if _floats(i["XB"])[4] > max(HEIGHTS)]
    assert layers
    assert all(_is_sooty(nml, i) for i in layers)


@pending
def test_uniform_room_is_sooty():
    _, nml = _deck("uniform")
    assert all(_is_sooty(nml, i) for i in _hot_inits(nml))


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
@pytest.mark.parametrize("quantity", ["GAUGE HEAT FLUX GAS", "RADIOMETER GAS"])
@pytest.mark.parametrize("z", HEIGHTS)
@pytest.mark.parametrize("facing", ["up", "side"])
def test_skin_gauges_on_point_arrays(kind, quantity, z, facing):
    _, nml = _deck(kind)
    is_facing = _is_up if facing == "up" else _is_side
    found = [
        d
        for d, xbp, o in _arrays(nml, quantity)
        if is_facing(o) and np.isclose(xbp[4], z) and np.isclose(xbp[5], z)
    ]
    assert found, f"no {quantity} array at z={z} facing {facing}"
    for d in found:
        assert float(d.get("POINTS", 1)) > 1
        assert d.get("TIME_HISTORY") is True
        prop = _prop(nml, d.get("PROP_ID"))
        assert float(prop.get("GAUGE_TEMPERATURE", np.nan)) == T_SKIN_C
        assert float(prop.get("GAUGE_EMISSIVITY", 1.0)) == 1.0
        if quantity == "GAUGE HEAT FLUX GAS":
            assert float(prop.get("HEAT_TRANSFER_COEFFICIENT", np.nan)) == H_GAUGE


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
@pytest.mark.parametrize("quantity", ["TEMPERATURE", "INTEGRATED INTENSITY"])
def test_temperature_and_intensity_at_every_gauge_point(kind, quantity):
    _, nml = _deck(kind)
    have = {
        (tuple(xbp), float(d.get("POINTS", 1)))
        for d, xbp, _ in _arrays(nml, quantity)
        if d.get("TIME_HISTORY") is True
    }
    need = {
        (tuple(xbp), float(d.get("POINTS", 1)))
        for d, xbp, _ in _arrays(nml, "GAUGE HEAT FLUX GAS")
        + _arrays(nml, "RADIOMETER GAS")
    }
    assert need <= have


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
@pytest.mark.parametrize("z", HEIGHTS)
def test_integrated_intensity_slice_on_a_cell_face(kind, z):
    _, nml = _deck(kind)
    slices = [
        s
        for s in _all(nml, "SLCF")
        if str(s.get("QUANTITY", "")).upper() == "INTEGRATED INTENSITY"
        and np.isclose(float(s.get("PBZ", np.nan)), z)
    ]
    assert slices
    for m in _all(nml, "MESH"):
        xb, nz = _floats(m["XB"]), _floats(m["IJK"])[2]
        if not xb[4] <= z <= xb[5]:
            continue
        k = (z - xb[4]) / ((xb[5] - xb[4]) / nz)
        assert np.isclose(k, round(k)), f"z={z} is not a cell face of {m}"


# --- Checks on the FDS output ----------------------------------------------


def _devc_csv(chid: str) -> Path:
    if not DATA_ROOT.is_dir():
        pytest.skip(f"no FDS output at {DATA_ROOT}")
    found = sorted(DATA_ROOT.rglob(f"{chid}_devc.csv"))
    if not found:
        pytest.skip(f"no {chid}_devc.csv under {DATA_ROOT}")
    return found[0]


def _read_devc(path: Path) -> dict[str, np.ndarray]:
    with path.open() as f:
        rows = list(csv.reader(f))
    ids = [c.strip().strip('"') for c in rows[1]]
    data = np.array([[float(x) for x in r] for r in rows[2:] if r])
    keep = data[:, 0] >= T_SETTLE
    return {k: data[keep, j] for j, k in enumerate(ids)}


def _points(nml, quantity):
    """Column ids and orientation of each device of a quantity, by position."""
    out = {}
    for d, xbp, o in _arrays(nml, quantity):
        n = int(float(d.get("POINTS", 1)))
        p0, p1 = np.array(xbp[0::2]), np.array(xbp[1::2])
        for i in range(n):
            pos = p0 + (p1 - p0) * (i / (n - 1) if n > 1 else 0.0)
            key = tuple(np.round(pos, 6))
            out.setdefault(key, []).append((f"{d['ID']}-{i + 1}", o))
    return out


def _output(kind):
    _, nml = _deck(kind)
    chid = _all(nml, "HEAD")[0]["CHID"]
    return nml, _read_devc(_devc_csv(chid))


def _incident(radiometer_kw):
    return radiometer_kw + SIGMA * (T_SKIN_C + 273.15) ** 4 / 1000.0


def _plates(nml, dev):
    """(position, orientation, q_inc, U, T) for every radiometer."""
    temp = _points(nml, "TEMPERATURE")
    u = _points(nml, "INTEGRATED INTENSITY")
    for pos, devs in _points(nml, "RADIOMETER GAS").items():
        for col, o in devs:
            yield (
                pos,
                o,
                _incident(dev[col]),
                dev[u[pos][0][0]],
                dev[temp[pos][0][0]],
            )


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
def test_gauge_minus_radiometer_is_convection(kind):
    """FDS UG Eqs. 22.35 - 22.36 with eps = 1: difference = h (T_g - T_gauge)."""
    nml, dev = _output(kind)
    gauges, radios = _points(nml, "GAUGE HEAT FLUX GAS"), _points(nml, "RADIOMETER GAS")
    temp = _points(nml, "TEMPERATURE")
    checked = 0
    for pos, gs in gauges.items():
        tg = dev[temp[pos][0][0]]
        for gcol, go in gs:
            rcol = next(c for c, o in radios[pos] if np.allclose(o, go))
            expected = H_GAUGE * (tg - T_SKIN_C) / 1000.0
            np.testing.assert_allclose(
                dev[gcol] - dev[rcol], expected, rtol=0, atol=EQ_22_35_ABS
            )
            checked += 1
    assert checked


@pending
@pytest.mark.parametrize("kind", ["hot_layer", "uniform", "burner"])
def test_incident_flux_is_between_zero_and_u(kind):
    nml, dev = _output(kind)
    plates = list(_plates(nml, dev))
    assert plates
    for pos, o, q, u, _ in plates:
        assert np.all(q >= -BOUND_BAND * u), (pos, o)
        assert np.all(q <= (1 + BOUND_BAND) * u), (pos, o)
    by_pos = {}
    for pos, o, q, u, _ in plates:
        by_pos.setdefault(pos, []).append((o, q, u))
    for pos, ps in by_pos.items():
        for o1, q1, u in ps:
            for o2, q2, _ in ps:
                if np.allclose(o1, -o2):
                    assert np.all(q1 + q2 <= (1 + BOUND_BAND) * u), (pos, o1)


@pending
def test_uniform_room_gives_a_quarter_of_u():
    """Isotropic field: q = U/4 for every orientation, U = 4 sigma T^4."""
    nml, dev = _output("uniform")
    for pos, o, q, u, t in _plates(nml, dev):
        np.testing.assert_allclose(q / u, 0.25, rtol=ISO_BAND, err_msg=str((pos, o)))
        black = 4 * SIGMA * (t + 273.15) ** 4 / 1000.0
        np.testing.assert_allclose(u, black, rtol=ISO_BAND, err_msg=str(pos))


@pending
def test_under_the_layer_the_crown_sees_more_than_the_face():
    """Radiation comes from above: q/U facing up exceeds 1/4 and the side value."""
    nml, dev = _output("hot_layer")
    by_pos = {}
    for pos, o, q, u, _ in _plates(nml, dev):
        by_pos.setdefault(pos, {})[
            "up" if _is_up(o) else "side" if _is_side(o) else "x"
        ] = q[-1] / u[-1]
    both = {p: r for p, r in by_pos.items() if {"up", "side"} <= r.keys()}
    assert both
    for pos, r in both.items():
        assert r["up"] > 0.25 * (1 + ISO_BAND), pos
        assert r["up"] > r["side"], pos


@pending
def test_a_flame_in_view_approaches_u():
    """Excess over the ambient field: a compact source face-on gives cos(theta)
    near 1, above the 1/2 of a uniform upper hemisphere."""
    nml, dev = _output("burner")
    tmpa = float(next((m.get("TMPA", 20.0) for m in _all(nml, "MISC")), 20.0))
    q_amb = SIGMA * (tmpa + 273.15) ** 4 / 1000.0
    best = max(
        (q[-1] - q_amb) / (u[-1] - 4 * q_amb) for _, _, q, u, _ in _plates(nml, dev)
    )
    assert best > 0.5


# --- Analysis script -------------------------------------------------------


def _script():
    if not SCRIPT.is_file():
        pytest.fail(f"missing {SCRIPT.relative_to(REPO)}")
    spec = importlib.util.spec_from_file_location("heat_radiometer", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pending
@pytest.mark.parametrize(
    "q_over_i, u_over_i, expected",
    [
        (np.pi, 4 * np.pi, 0.25),  # isotropic field, any plate
        (np.pi, 2 * np.pi, 0.5),  # uniform upper hemisphere, plate facing up
        (np.pi / 2, 2 * np.pi, 0.25),  # same field, vertical plate
        (1.0, 1.0, 1.0),  # collimated beam, plate face-on
    ],
)
def test_script_flux_ratio(q_over_i, u_over_i, expected):
    """flux_ratio(radiometer_kw, integrated_intensity_kw, gauge_temperature_c)
    inverts Eq. 22.36 (eps = 1) and divides by U."""
    mod = _script()
    intensity = 3.0  # kW/m2/sr
    radiometer = q_over_i * intensity - SIGMA * (T_SKIN_C + 273.15) ** 4 / 1000.0
    got = mod.flux_ratio(radiometer, u_over_i * intensity, T_SKIN_C)
    assert got == pytest.approx(expected, rel=1e-12)
