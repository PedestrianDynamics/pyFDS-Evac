"""Population spread of heat tolerance (#225).

SFPE Handbook 6th ed., Ch. 70 (Purser & McAllister 2026), p. 2318, gives the
only population figures for heat: for infrared radiation, a dose of
10 (kW/m2)^(4/3) min is a 1 % lethal level for the average population and
16.7 (kW/m2)^(4/3) min a 50 % lethal level. No figure is given for the
convective law in use (Eq. 70.42). Hockey & Rew (1996, HSE CRR 97/1996,
ref. [125] of Ch. 70) review the radiant probits, all in ln(I^(4/3) t) with
the dose in (kW/m2)^(4/3) s: Eisenberg's lethality probit
Y = -14.9 + 2.56 ln V (sect. 4.2.2, pp. 15-16) and the 3.0186 slopes of Tsao
& Perry and the TNO Green Book (p. 17); Table 5.1 (p. 23) gives Eisenberg's
1 % and 50 % lethal doses, 960 and 2380. A probit slope b in ln dose is a
log-normal with sigma = 1/b. The report gives 1000 (kW/m2)^(4/3) s, the
Handbook's 16.7, as a 1 % level, so the earlier two-point reading of the
Handbook figures (sigma 0.22) is withdrawn on the page.

The expected values below are computed from those published figures with
the standard normal quantile of the Python standard library, not from the
code under test. The docs checks define "done" for the documentation part of
the issue. The code defaults (heat
deterministic, opt-in sigma 0.94) are pinned in test_docs_defaults.py and
tests/verification/test_heat_fed_verif.py.
"""

import math
import re
from pathlib import Path
from statistics import NormalDist

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODELS_HEAT = ROOT / "site" / "content" / "models" / "heat.md"
THRESHOLDS = ROOT / "site" / "content" / "fundamentals" / "incapacitation-thresholds.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ISSUE = "issues/225"

# SFPE Handbook 6th ed., Ch. 70, p. 2318 (radiant dose r, (kW/m2)^(4/3) min).
R_ONE_PERCENT_FATAL = 10.0
R_MEDIAN_LETHAL = 16.7
# Fatal dose D of the total-flux method, as printed on Ch. 70 p. 2319.
D_FATAL = 16.7
# Purser's spreadsheet value (personal communication); not used by the code.
D_SPREADSHEET = 16.667
BORROWED_SIGMA = 0.94
# Hockey & Rew (1996): probit slopes in ln dose, and Eisenberg's lethal doses.
EISENBERG_SLOPE = 2.56
INJURY_SLOPE = 3.0186
EISENBERG_LD01 = 960.0
EISENBERG_LD50 = 2380.0


def _two_point_lognormal_sigma(r_low, p_low, r_median):
    """Log-scale sigma of a log-normal with median r_median and P(r_low) = p_low."""
    return math.log(r_median / r_low) / -NormalDist().inv_cdf(p_low)


def test_handbook_lethality_figures_imply_sigma_near_0_22():
    """ln(16.7 / 10) / z_0.99 = 0.5128 / 2.3263 = 0.2205, the withdrawn reading."""
    sigma = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL)
    assert sigma == pytest.approx(0.2205, abs=5e-4)


def test_sigma_is_insensitive_to_16_7_versus_16_667():
    """Purser's spreadsheet D = 16.667 gives the same sigma to two decimals."""
    a = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL)
    b = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, D_SPREADSHEET)
    assert round(a, 2) == round(b, 2) == 0.22


def test_one_percent_level_sits_at_fed_0_6_of_the_fatal_dose():
    """With FED = 1 at D = 16.7 (p. 2319), the 1 % fatality dose is FED 10/16.7."""
    assert R_ONE_PERCENT_FATAL / D_FATAL == pytest.approx(0.599, abs=1e-3)


def test_borrowed_gas_sigma_contradicts_the_lethality_figures():
    """With sigma 0.94, 29 % (not 1 %) fall below FED 0.6: Phi(ln 0.6 / 0.94)."""
    fed = R_ONE_PERCENT_FATAL / R_MEDIAN_LETHAL
    fraction = NormalDist().cdf(math.log(fed) / BORROWED_SIGMA)
    assert fraction == pytest.approx(0.293, abs=2e-3)
    assert fraction > 20 * 0.01


def _heat_section(text):
    """The part of the thresholds page from a heading naming heat onward."""
    match = re.search(r"^#{2,3} [^\n]*[Hh]eat[^\n]*$", text, re.MULTILINE)
    assert match, "no heading naming heat"
    return text[match.start() :]


def test_thresholds_page_states_what_is_known_for_heat():
    """Fundamentals › Incapacitation thresholds covers heat with sources."""
    section = _heat_section(THRESHOLDS.read_text())
    for fragment in ("2318", "16.7", "Hockey", ISSUE):
        assert fragment in section, fragment


def test_thresholds_page_cites_refs_125_126_on_p_2318():
    """Refs. [125, 126] for the radiant dose relation are on book p. 2318."""
    section = _heat_section(THRESHOLDS.read_text())
    assert "p. 2317" not in section


def test_eisenberg_slope_and_lethal_doses_give_the_same_sigma():
    """1/2.56 = 0.39, and ln(2380/960)/z_0.99 = 0.39 from Table 5.1."""
    from_slope = 1.0 / EISENBERG_SLOPE
    from_doses = _two_point_lognormal_sigma(EISENBERG_LD01, 0.01, EISENBERG_LD50)
    assert round(from_slope, 2) == round(from_doses, 2) == 0.39


def test_thresholds_page_quotes_the_hockey_rew_probits():
    """The heat section gives Eisenberg's probit, its sigma and Table 5.1."""
    section = _heat_section(THRESHOLDS.read_text())
    for fragment in ("−14.9 + 2.56 ln", "Table 5.1", "960", "2380", "withdrawn"):
        assert fragment in section, fragment


def test_thresholds_page_quotes_the_derived_sigma_correctly():
    """Every sigma the heat section quotes, other than 0.94, follows a source.

    Allowed: 1/2.56 and 1/3.0186 from the probits, and the withdrawn 0.22.
    """
    section = _heat_section(THRESHOLDS.read_text())
    quoted = re.findall(r"(?:σ|\\sigma)\s*(?:≈|=|\\approx)\s*(0\.\d+)", section)
    derived = [float(v) for v in quoted if float(v) != BORROWED_SIGMA]
    assert derived, "no derived sigma quoted"
    allowed = (
        1.0 / EISENBERG_SLOPE,
        1.0 / INJURY_SLOPE,
        _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL),
    )
    for value in derived:
        assert any(value == pytest.approx(a, abs=0.005) for a in allowed), value
    assert any(v == pytest.approx(1.0 / EISENBERG_SLOPE, abs=0.005) for v in derived)


def test_models_heat_links_the_open_sigma_issue():
    """Models › Heat points to #225 for the unsourced opt-in sigma."""
    assert ISSUE in MODELS_HEAT.read_text()


def test_changelog_unreleased_mentions_225():
    text = CHANGELOG.read_text()
    unreleased = text.split("## [0.2.0]", 1)[1].split("\n## [", 1)[0]
    assert ISSUE in unreleased
