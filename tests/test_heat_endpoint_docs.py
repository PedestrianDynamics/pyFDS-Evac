"""Docs checks for the heat dose's endpoint and flux type (#218).

Three things the heat pages must state:

- which kind of flux each formula takes: the radiant tolerance data
  (Eq. 63.43) are incident flux, the total-flux form (Eq. 63.49) is a net
  exchange with the skin, and the convective laws take air temperature, no
  flux at all (SFPE Handbook 5th ed., Ch. 63, pp. 2382-2384);
- that heat FED = 1 and gas FED = 1 are different endpoints although both set
  the same ``incapacitated`` flag and ``incapacitation_cause`` column;
- ``fed.py:N`` line references that point at the code they name.

The line-reference check resolves each citation against the symbol named
next to it, so it does not hard-code the current line numbers. A citation
written without a line number passes.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FED_PY = ROOT / "pyfds_evac" / "core" / "fed.py"
MODELS_FED = ROOT / "site" / "content" / "models" / "fed.md"
MODELS_HEAT = ROOT / "site" / "content" / "models" / "heat.md"
FUND_HEAT = ROOT / "site" / "content" / "fundamentals" / "heat.md"
LIMITATIONS = ROOT / "docs" / "limitations.md"

_XFAIL = pytest.mark.xfail(strict=True, reason="#218")

_CITE = r"`(?:pyfds_evac/core/)?fed\.py:(\d+)`"


def _section(path: Path, heading: str) -> str:
    """Return the text under ``## heading`` up to the next ``## `` heading."""
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"{path.name}: no section '## {heading}'"
    return match.group(1)


def _paragraph_with(path: Path, needle: str) -> str:
    """Return the blank-line-delimited paragraph of ``path`` containing ``needle``."""
    for para in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        if needle in para:
            return para
    raise AssertionError(f"{path.name}: no paragraph containing {needle!r}")


# --- Line references -------------------------------------------------------

# (id, doc, anchor regex with one group per cited line, code regex per group).
# The anchor is the text naming what the citation points at; the code regex
# must match the cited line of fed.py.
_REFS = [
    (
        "fed-total-rate",
        MODELS_FED,
        r"`FedComponents\.total_rate_per_min` \(" + _CITE,
        [r"def total_rate_per_min\b"],
    ),
    (
        "fed-heat-rate",
        MODELS_FED,
        r"`_heat_fed_rate_per_minute` \(" + _CITE,
        [r"_heat_fed_rate_per_minute\b|\*\*\s*3\.4"],
    ),
    (
        "fed-tenability-config",
        MODELS_FED,
        r"`TenabilityConfig` \(" + _CITE,
        [r"class TenabilityConfig\b"],
    ),
    (
        "fed-guide-structure",
        MODELS_FED,
        r"guide structure \(" + _CITE,
        [r"def total_rate_per_min\b"],
    ),
    (
        "fed-co2-hyperventilation",
        MODELS_FED,
        r"Eq\. 63\.34 \(" + _CITE,
        [r"_hyperventilation_factor\b|0\.1903"],
    ),
    (
        "fed-co-light-work",
        MODELS_FED,
        r"light work \(" + _CITE,
        [r"_co_fed_rate_per_minute\b|2\.764e-5"],
    ),
    (
        "fed-irritant-slowdown",
        MODELS_FED,
        r"irritant slowdown \\\(g\\\), when enabled \(" + _CITE + r"(?:–`(\d+)`)?",
        [r"\bfic_(?:alpha|min_factor)\b", r"\bfic_(?:alpha|min_factor)\b"],
    ),
    (
        "fed-heat-only",
        MODELS_FED,
        r"Eq\. 63\.44 only \(" + _CITE,
        [r"_heat_fed_rate_per_minute\b|\*\*\s*3\.4"],
    ),
    (
        "fed-sigmas",
        MODELS_FED,
        r"thresholds \(" + _CITE + r"(?:, `:(\d+)`)?",
        [
            r"^\s*susceptibility_sigma\s*:",
            r"^\s*heat_susceptibility_sigma\s*:",
        ],
    ),
    (
        "heat-rate",
        MODELS_HEAT,
        r"`_heat_fed_rate_per_minute` \(" + _CITE,
        [r"_heat_fed_rate_per_minute\b|\*\*\s*3\.4"],
    ),
]


@pytest.mark.parametrize(
    ("doc", "anchor", "code_patterns"),
    [pytest.param(d, a, c, id=i, marks=_XFAIL) for i, d, a, c in _REFS],
)
def test_fed_line_reference_points_at_named_code(doc, anchor, code_patterns):
    """Each ``fed.py:N`` citation lands on the code the sentence names."""
    lines = FED_PY.read_text(encoding="utf-8").splitlines()
    match = re.search(anchor, doc.read_text(encoding="utf-8"))
    if match is None:
        return  # citation rewritten without a line number
    for group, pattern in zip(match.groups(), code_patterns):
        if group is None:
            continue
        number = int(group)
        assert 1 <= number <= len(lines), f"{doc.name}: fed.py:{number} past EOF"
        assert re.search(pattern, lines[number - 1]), (
            f"{doc.name}: fed.py:{number} is {lines[number - 1].strip()!r}, "
            f"expected a line matching {pattern!r}"
        )


def test_every_fed_line_reference_is_checked():
    """No ``fed.py:N`` citation in the site or docs escapes the table above."""
    covered: dict[Path, int] = {}
    for _, doc, anchor, _ in _REFS:
        match = re.search(anchor, doc.read_text(encoding="utf-8"))
        if match is not None:
            covered[doc] = covered.get(doc, 0) + sum(
                g is not None for g in match.groups()
            )
    pages = [*(ROOT / "site" / "content").rglob("*.md"), *(ROOT / "docs").glob("*.md")]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        found = len(re.findall(r"fed\.py:\d+", text))
        found += len(re.findall(r"fed\.py:\d+`(?:–`|, `:)\d+", text))
        assert found == covered.get(page, 0), (
            f"{page.relative_to(ROOT)}: {found} fed.py line citations, "
            f"{covered.get(page, 0)} checked; add the new ones to _REFS"
        )


# --- Incident vs net flux --------------------------------------------------


@_XFAIL
def test_fundamentals_radiant_section_says_incident():
    """Eq. 63.43 and the 2.5 kW/m² limit are incident flux (Table 63.19)."""
    assert re.search(r"\bincident\b", _section(FUND_HEAT, "Radiant heat"))


@_XFAIL
def test_fundamentals_combining_section_says_net():
    """Eq. 63.49 is written as a net exchange with the skin surface."""
    assert re.search(r"\bnet\b", _section(FUND_HEAT, "Combining the two"))


@_XFAIL
def test_fundamentals_convective_section_says_no_flux():
    """Eqs. 63.44-63.47 take air temperature; the page must say no flux enters."""
    assert re.search(r"\bflux\b", _section(FUND_HEAT, "Convective heat"))


@_XFAIL
def test_models_heat_states_what_enters_the_implemented_law():
    """The implemented law takes the gas temperature, not a heat flux."""
    assert re.search(r"\bflux\b", _section(MODELS_HEAT, "What is computed"))


# --- Endpoints of the two doses --------------------------------------------


def _heat_incapacitation_and_output() -> str:
    return _section(MODELS_HEAT, "Incapacitation") + _section(MODELS_HEAT, "Output")


@_XFAIL
def test_models_heat_says_heat_and_gas_endpoints_differ():
    """Heat FED = 1 is not the gas dose's incapacitation endpoint."""
    text = _heat_incapacitation_and_output()
    assert re.search(r"\bendpoints?\b", text)
    assert re.search(r"\bgas\b", text)


def test_models_heat_names_the_shared_output_columns():
    """Both doses report through ``incapacitation_cause``; pins the column name."""
    assert "`incapacitation_cause`" in _section(MODELS_HEAT, "Output")


@_XFAIL
def test_limitations_says_heat_and_gas_endpoints_differ():
    """The OR rule on Limitations must not present the two doses as one endpoint."""
    para = _paragraph_with(LIMITATIONS, "either dose reaches its threshold")
    assert re.search(r"\bendpoints?\b", para)


def test_models_heat_does_not_call_the_implemented_law_fatal():
    """FED = 1 = fatal belongs to the unimplemented total-flux form (#223).

    The implemented law is Eq. 63.44, whose times lie near the tolerance
    curve, so the Incapacitation and Output sections must not call it fatal
    unless they also say that it is not.
    """
    text = _heat_incapacitation_and_output()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\bfatal\b", sentence, flags=re.IGNORECASE):
            assert re.search(
                r"\bnot\b|#223|total-flux|planned", sentence, flags=re.IGNORECASE
            ), f"implemented heat law called fatal: {sentence!r}"
