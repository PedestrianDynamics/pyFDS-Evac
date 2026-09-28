"""Population spread of heat tolerance (#225).

SFPE Handbook 5th ed., Ch. 63 (Purser & McAllister 2016), p. 2382, gives the
only population figures for heat: for infrared radiation, a dose of
10 (kW/m2)^(4/3) min is a 1 % fatality level for the average population and
16.7 (kW/m2)^(4/3) min a 50 % lethal level. No figure is given for the
convective law in use (Eq. 63.44). Hockey & Rew (1996, HSE CRR 97/1996,
ref. [133] of Ch. 63) is a candidate source for probit slopes that would
give a spread directly; it is not in the library and has not been read.

The expected values below are computed from those two published figures with
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

# SFPE Handbook 5th ed., Ch. 63, p. 2382 (radiant dose r, (kW/m2)^(4/3) min).
R_ONE_PERCENT_FATAL = 10.0
R_MEDIAN_LETHAL = 16.7
# Fatal endpoint of the planned total-flux dose (SPEC 016, Ch. 63 p. 2384).
D_FATAL = 16.667
BORROWED_SIGMA = 0.94


def _two_point_lognormal_sigma(r_low, p_low, r_median):
    """Log-scale sigma of a log-normal with median r_median and P(r_low) = p_low."""
    return math.log(r_median / r_low) / -NormalDist().inv_cdf(p_low)


def test_handbook_lethality_figures_imply_sigma_near_0_22():
    """ln(16.7 / 10) / z_0.99 = 0.5128 / 2.3263 = 0.2205 (issue #225)."""
    sigma = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL)
    assert sigma == pytest.approx(0.2205, abs=5e-4)


def test_sigma_is_insensitive_to_16_7_versus_16_667():
    """The spec's D = 16.667 gives the same sigma to two decimals."""
    a = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL)
    b = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, D_FATAL)
    assert round(a, 2) == round(b, 2) == 0.22


def test_one_percent_level_sits_at_fed_0_6_of_the_fatal_dose():
    """With FED = 1 at D = 16.667, the 1 % fatality dose is FED 10/16.667."""
    assert R_ONE_PERCENT_FATAL / D_FATAL == pytest.approx(0.600, abs=1e-3)


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
    for fragment in ("2382", "16.7", "Hockey", ISSUE):
        assert fragment in section, fragment


def test_thresholds_page_cites_refs_133_134_on_p_2382():
    """Refs. [133, 134] for the radiant dose relation are on book p. 2382."""
    section = _heat_section(THRESHOLDS.read_text())
    assert "p. 2381" not in section


def test_thresholds_page_does_not_claim_hockey_rew_contents():
    """Hockey and Rew is unread, so the page does not state what it contains."""
    section = _heat_section(THRESHOLDS.read_text())
    assert "are in Hockey" not in section


def test_thresholds_page_quotes_the_derived_sigma_correctly():
    """Any sigma the heat section quotes other than 0.94 equals 0.22."""
    section = _heat_section(THRESHOLDS.read_text())
    quoted = re.findall(r"(?:σ|\\sigma)\s*(?:≈|=|\\approx)\s*(0\.\d+)", section)
    derived = [float(v) for v in quoted if float(v) != BORROWED_SIGMA]
    assert derived, "no derived sigma quoted"
    expected = _two_point_lognormal_sigma(R_ONE_PERCENT_FATAL, 0.01, R_MEDIAN_LETHAL)
    for value in derived:
        assert value == pytest.approx(expected, abs=0.005)


def test_models_heat_links_the_open_sigma_issue():
    """Models › Heat points to #225 for the unsourced opt-in sigma."""
    assert ISSUE in MODELS_HEAT.read_text()


def test_changelog_unreleased_mentions_225():
    text = CHANGELOG.read_text()
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert ISSUE in unreleased
