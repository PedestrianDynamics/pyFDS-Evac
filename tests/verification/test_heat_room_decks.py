"""The uniform heat rooms hold their prescribed temperature (#253).

``assets/fed_incap_heat_{100,150,200}c`` are sealed 30 x 30 x 3 m rooms,
adiabatic on all six faces, set to 100, 150 or 200 C at t = 0. FDS 6.10.1
starts the wall surfaces and the radiation field at TMPA. With
``&MISC TMPA=20.`` ``hrr.csv`` would show Q_RADI = -370 kW and
Q_COND = -98 kW at t = 0 (150 C deck), and the room would settle 0.7-1.8 %
below the deck value within the first minute. A one-mesh 120 s run of the
same room held 150.0004 C with TMPA = 150 and fell to 148.06 C with
TMPA = 20.

Expected values come from the deck name and from SFPE Handbook 5th ed.,
Ch. 63, Eq. 63.44 (t_I,conv = 5e7 T^-3.4 min) written out here, not from
pyFDS-Evac. The stored runs use ``--heat-clothing unclothed``, which selects
that law (ISO 13571:2012 Eq. (10)); the page also lists, as expected values
only, the times of the default law, ISO Eq. (9) (t_I,conv = 4.1e8 T^-3.61
min).
"""

import csv
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
HEAT_DOC = ROOT / "docs" / "testing-heat.md"
DECK_TEMPERATURES_C = (100.0, 150.0, 200.0)
FACES = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")
# 0.01 K moves the Eq. 63.44 dose by at most
# 3.4 * 0.01 / 100 = 3.4e-4, below the 9.4e-4 margin of the hand FED from 1
# at the last update before the stop (200 C, 45 s of 45.04 s).
HOLD_TOLERANCE_K = 0.01
UPDATE_INTERVAL_S = 1.0


def _deck_path(temperature_c: float) -> Path:
    name = f"fed_incap_heat_{temperature_c:.0f}c"
    return ASSETS / name / f"{name}.fds"


def _namelists(text: str, group: str) -> list[str]:
    """Return the bodies of every ``&GROUP ... /`` namelist, comments dropped."""
    code = "\n".join(line.split("!", 1)[0] for line in text.splitlines())
    return re.findall(rf"&{group}\b(.*?)/", code, flags=re.DOTALL)


def _real(body: str, key: str) -> float | None:
    match = re.search(rf"\b{key}\s*=\s*(-?[\d.]+(?:[eEdD][-+]?\d+)?)", body)
    if match is None:
        return None
    return float(match.group(1).replace("d", "e").replace("D", "e"))


def _closed_form_tstar_s(temperature_c: float) -> float:
    """SFPE Eq. 63.44, in seconds: 60 * 5e7 / T^3.4."""
    return 60.0 * 5e7 / temperature_c**3.4


def _first_update_at_or_after(t_s: float) -> float:
    """The first dose update (every 1 s from t = 0) at which FED >= 1."""
    return math.ceil(t_s / UPDATE_INTERVAL_S) * UPDATE_INTERVAL_S


@pytest.mark.parametrize("temperature_c", DECK_TEMPERATURES_C)
def test_deck_is_adiabatic_on_all_six_faces(temperature_c):
    text = _deck_path(temperature_c).read_text()
    adiabatic = {
        re.search(r"ID\s*=\s*'([^']+)'", body).group(1)
        for body in _namelists(text, "SURF")
        if re.search(r"ADIABATIC\s*=\s*\.TRUE\.", body, flags=re.IGNORECASE)
    }
    faces = {}
    for body in _namelists(text, "VENT"):
        mb = re.search(r"MB\s*=\s*'(\w+)'", body)
        surf = re.search(r"SURF_ID\s*=\s*'([^']+)'", body)
        if mb and surf:
            faces[mb.group(1)] = surf.group(1)
    assert set(faces) == set(FACES)
    assert all(faces[face] in adiabatic for face in FACES)


@pytest.mark.parametrize("temperature_c", DECK_TEMPERATURES_C)
def test_deck_init_matches_its_name(temperature_c):
    """Any &INIT TEMPERATURE in the deck is the value the deck is named after."""
    text = _deck_path(temperature_c).read_text()
    for body in _namelists(text, "INIT"):
        value = _real(body, "TEMPERATURE")
        if value is not None:
            assert value == temperature_c


@pytest.mark.parametrize("temperature_c", DECK_TEMPERATURES_C)
def test_deck_ambient_is_the_prescribed_temperature(temperature_c):
    """TMPA sets the initial wall and radiation temperature; it must be T."""
    text = _deck_path(temperature_c).read_text()
    (misc,) = _namelists(text, "MISC")
    assert _real(misc, "TMPA") == temperature_c


def _devc_rows(temperature_c: float) -> tuple[list[str], list[list[float]]]:
    fds_dir = _deck_path(temperature_c).parent / "fds"
    (path,) = sorted(fds_dir.glob("*_devc.csv"))
    with path.open() as handle:
        reader = csv.reader(handle)
        next(reader)  # units
        header = [h.strip().strip('"') for h in next(reader)]
        rows = [[float(v) for v in row] for row in reader if row]
    return header, rows


@pytest.mark.parametrize("temperature_c", DECK_TEMPERATURES_C)
def test_fds_room_holds_the_prescribed_temperature(temperature_c):
    """Every TEMP device, at every output time, reads the deck value.

    Reads FDS's own ``*_devc.csv`` committed under ``assets/<deck>/fds/``.
    """
    header, rows = _devc_rows(temperature_c)
    columns = [i for i, name in enumerate(header) if name.startswith("TEMP")]
    assert len(columns) == 5
    assert rows[-1][0] >= 999.0, "the run must cover T_END = 1000 s"
    worst = max(abs(row[i] - temperature_c) for row in rows for i in columns)
    assert worst <= HOLD_TOLERANCE_K, f"max |T - {temperature_c}| = {worst:.4f} K"


@pytest.mark.parametrize(
    "temperature_c, tstar_s",
    [(100.0, 475.468), (150.0, 119.787), (200.0, 45.042)],
)
def test_closed_form_tstar(temperature_c, tstar_s):
    """Eq. 63.44 at the deck value, against the values quoted in the docs."""
    assert _closed_form_tstar_s(temperature_c) == pytest.approx(tstar_s, abs=1e-3)


@pytest.mark.parametrize("temperature_c", DECK_TEMPERATURES_C)
def test_docs_expect_the_closed_form_stop(temperature_c):
    """docs/testing-heat.md: deterministic stop = first update after t*(deck T)."""
    expected = _first_update_at_or_after(_closed_form_tstar_s(temperature_c))
    pattern = rf"\|\s*deterministic stop, {temperature_c:.0f} °C\s*\|\s*(\d+) s\s*\|"
    match = re.search(pattern, HEAT_DOC.read_text())
    assert match is not None
    assert float(match.group(1)) == expected


@pytest.mark.parametrize(
    "temperature_c, tstar_s",
    [(100.0, 1482.3), (150.0, 343.0), (200.0, 121.4)],
)
def test_docs_list_the_default_law_times(temperature_c, tstar_s):
    """ISO 13571:2012 Eq. (9) at the deck value, as quoted in the docs table."""
    assert 60.0 * 4.1e8 * temperature_c**-3.61 == pytest.approx(tstar_s, abs=0.05)
    pattern = rf"\|\s*{temperature_c:.0f} °C\s*\|[^\n]*\|\s*{tstar_s:.1f} s"
    assert re.search(pattern, HEAT_DOC.read_text()) is not None


def test_docs_runs_select_the_unclothed_law():
    """The page runs Eq. 63.44, so its command must select it explicitly."""
    text = HEAT_DOC.read_text()
    command = text.split("```bash", 2)[2].split("```", 1)[0]
    assert "--heat-clothing unclothed" in command
    assert 60.0 * 4.1e8 * 100.0**-3.61 > 1000.0  # beyond the FDS record
