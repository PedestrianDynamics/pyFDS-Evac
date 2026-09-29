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
        r"Eq\. 63\.44(?: only)? \(" + _CITE,
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
    [pytest.param(d, a, c, id=i) for i, d, a, c in _REFS],
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
#
# Each check asserts the relation, not a keyword: a sentence that names the
# right flux for the right equation. The negative cases are wrong wordings
# that must fail, so a sentence with the opposite meaning cannot pass.


def _sentences(text: str) -> list[str]:
    """Split on sentence ends; line breaks inside a sentence become spaces."""
    flat = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+(?=[A-Z`\\])", flat)


def _negated(sentence: str, word: str) -> bool:
    """True if ``word`` follows a negation in ``sentence``."""
    return bool(
        re.search(rf"\b(?:not|no|nor|neither)\b[^.;:]*\b{word}\b", sentence, re.I)
    )


def _radiant_limit_is_incident(text: str) -> bool:
    """A sentence ties the radiant limit or Eq. 63.43 to incident flux."""
    return any(
        re.search(r"\bradiant\b", s, re.I)
        and re.search(r"\bincident\b", s)
        and not re.search(r"\bnet\b", s)
        and not _negated(s, "incident")
        for s in _sentences(text)
    )


def _eq_63_49_is_net(text: str) -> bool:
    """A sentence names Eq. 63.49 and says it is written as a net exchange."""
    return any(
        "63.49" in s and re.search(r"\bnet exchange\b", s) and not _negated(s, "net")
        for s in _sentences(text)
    )


def _takes_temperature_not_flux(text: str) -> bool:
    """A sentence says no heat flux enters and only the temperature does."""
    return any(
        re.search(r"\bNo heat flux enters\b", s)
        and re.search(r"\b(?:air|gas) temperature only\b", s)
        for s in _sentences(text)
    )


def _fds_radiative_flux_is_net_with_emissivity(text: str) -> bool:
    """FDS RADIATIVE HEAT FLUX is net, εs(q_inc − σTs⁴), with the emissivity."""
    return any(
        "`RADIATIVE HEAT FLUX`" in s
        and re.search(r"\bnet\b", s)
        and re.search(r"\\varepsilon_s\s*\\left\(|\\varepsilon_s\s*\(", s)
        and re.search(r"\\sigma\s*T_s\^4", s)
        for s in _sentences(text)
    )


_FLUX_CHECKS = [
    (
        "radiant-incident",
        _radiant_limit_is_incident,
        lambda: _section(FUND_HEAT, "Radiant heat"),
        [
            "The tenability limit for net radiant flux on skin is 2.5 kW/m².",
            "The radiant limit is not incident flux.",
        ],
    ),
    (
        "eq-63-49-net",
        _eq_63_49_is_net,
        lambda: _section(FUND_HEAT, "Combining the two"),
        [
            "The total heat flux to the skin (Eq. 63.49) is the incident flux.",
            "Eq. 63.49 is not a net exchange with the skin surface.",
        ],
    ),
    (
        "convective-fundamentals",
        _takes_temperature_not_flux,
        lambda: _section(FUND_HEAT, "Convective heat"),
        [
            "These convective equations take incident heat flux.",
            "They take the heat flux only, not the air temperature.",
        ],
    ),
    (
        "convective-models",
        _takes_temperature_not_flux,
        lambda: _section(MODELS_HEAT, "What is computed"),
        [
            "The law takes the net heat flux at the agent.",
            "No gas temperature enters the law: it takes the heat flux only.",
        ],
    ),
    (
        "fds-radiative-net",
        _fds_radiative_flux_is_net_with_emissivity,
        lambda: FUND_HEAT.read_text(encoding="utf-8"),
        [
            "FDS's `RADIATIVE HEAT FLUX` output is net (absorbed incident flux "
            r"minus \(\sigma T_s^4\)).",
            "FDS's `RADIATIVE HEAT FLUX` output is the incident flux.",
        ],
    ),
]


@pytest.mark.parametrize(
    ("check", "text"),
    [pytest.param(c, t, id=i) for i, c, t, _ in _FLUX_CHECKS],
)
def test_docs_state_the_flux_each_formula_takes(check, text):
    """Eq. 63.43 incident, Eq. 63.49 net, Eqs. 63.44-63.47 temperature only."""
    assert check(text()), f"{check.__name__} not stated"


@pytest.mark.parametrize(
    ("check", "wrong"),
    [
        pytest.param(c, w, id=f"{i}-{n}")
        for i, c, _, wrongs in _FLUX_CHECKS
        for n, w in enumerate(wrongs)
    ],
)
def test_flux_checks_reject_wrong_wording(check, wrong):
    """Each flux check fails on a sentence with the wrong or opposite meaning."""
    assert not check(wrong), f"{check.__name__} accepted {wrong!r}"


# --- Endpoints of the two doses --------------------------------------------


def _heat_incapacitation_and_output() -> str:
    return _section(MODELS_HEAT, "Incapacitation") + _section(MODELS_HEAT, "Output")


def _says_endpoints_differ(text: str) -> bool:
    """Heat and gas FED = 1 are stated as different endpoints, never the same."""
    flat = re.sub(r"\s+", " ", text)
    differ = re.search(r"\bdo not share an endpoint\b|\bdifferent endpoints\b", flat)
    same = re.search(
        r"(?<!not )\bshare an endpoint\b|\bsame endpoint\b|\bone endpoint\b", flat
    )
    return bool(differ) and not same


def _says_cause_separates_the_endpoints(text: str) -> bool:
    """``incapacitated`` mixes the endpoints; ``incapacitation_cause`` tells them apart."""
    flat = re.sub(r"\s+", " ", text)
    return bool(
        re.search(r"`incapacitated` column is true whichever dose", flat)
        and re.search(r"filter on `incapacitation_cause`", flat)
    )


def _says_later_crossing_not_recorded(text: str) -> bool:
    """``gas+heat`` is the same update; a later crossing leaves the cause alone."""
    flat = re.sub(r"\s+", " ", text)
    return bool(
        re.search(r"`gas\+heat` means both doses crossed[^.]*same update", flat)
        and re.search(r"after the agent has stopped is not recorded", flat)
    )


_ENDPOINT_CHECKS = [
    (
        "models-heat-differ",
        _says_endpoints_differ,
        _heat_incapacitation_and_output,
        [
            "Heat and gas have the same endpoint.",
            "The two doses share an endpoint, FED = 1.",
            "Gas FED = 1 and heat FED = 1 are one endpoint.",
        ],
    ),
    (
        "limitations-differ",
        _says_endpoints_differ,
        lambda: _paragraph_with(LIMITATIONS, "either dose reaches its threshold"),
        ["An agent is incapacitated when either dose reaches the same endpoint."],
    ),
    (
        "models-heat-cause",
        _says_cause_separates_the_endpoints,
        lambda: _section(MODELS_HEAT, "Output"),
        [
            "The `incapacitated` column is true only for the gas dose.",
            "Filter on `incapacitated` to count them apart.",
        ],
    ),
    (
        "models-heat-later-crossing",
        _says_later_crossing_not_recorded,
        lambda: _section(MODELS_HEAT, "Output"),
        [
            "`gas+heat` means both doses crossed at some time during the run.",
            "`gas+heat` means both doses crossed their thresholds on the same "
            "update; a later crossing by the other dose is recorded as well.",
        ],
    ),
]


@pytest.mark.parametrize(
    ("check", "text"),
    [pytest.param(c, t, id=i) for i, c, t, _ in _ENDPOINT_CHECKS],
)
def test_docs_separate_heat_and_gas_endpoints(check, text):
    """Heat FED = 1 is not the gas dose's incapacitation endpoint."""
    assert check(text()), f"{check.__name__} not stated"


@pytest.mark.parametrize(
    ("check", "wrong"),
    [
        pytest.param(c, w, id=f"{i}-{n}")
        for i, c, _, wrongs in _ENDPOINT_CHECKS
        for n, w in enumerate(wrongs)
    ],
)
def test_endpoint_checks_reject_wrong_wording(check, wrong):
    """Each endpoint check fails on a sentence with the opposite meaning."""
    assert not check(wrong), f"{check.__name__} accepted {wrong!r}"


def test_models_heat_names_the_shared_output_columns():
    """Both doses report through ``incapacitation_cause``; pins the column name."""
    assert "`incapacitation_cause`" in _section(MODELS_HEAT, "Output")


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
