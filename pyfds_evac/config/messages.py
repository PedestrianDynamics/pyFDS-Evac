"""Wording of the setup warnings and configuration errors of a run.

``pyfds_evac.core.run_config`` logs and raises with these texts, and the
effective configuration predicts them with the same functions, so the two
cannot word a message differently. Rule numbers (``D…``) refer to the
dependency table of the configuration model (#484).
"""

from __future__ import annotations

from collections.abc import Iterable

# The published page on what an FDS case must write (docs/fds-case-requirements.md).
FDS_CASE_DOCS = (
    "https://pedestriandynamics.org/pyFDS-Evac/docs/using/fds-case-requirements/"
)


def no_effect(flag: str, reason: str) -> str:
    """An option set to a value that changes nothing in this run."""
    return f"{flag} has no effect {reason}."


# --- warnings (logger) -----------------------------------------------------


def smoke_without_extinction(fds_dir: str) -> str:
    """D3: no SOOT EXTINCTION COEFFICIENT slice and no constant K."""
    return (
        f"Smoke speed reduction is disabled for {fds_dir}: it has no SOOT "
        "EXTINCTION COEFFICIENT slice, so agents walk at clear-air speed. "
        "Pass --constant-extinction to set a uniform extinction instead."
    )


def fed_without_gases(fds_dir: str, missing: Iterable[str]) -> str:
    """D6: the case lacks one of the CO, CO2 and O2 slices."""
    missing = sorted(missing)
    named = ", ".join(m.upper() for m in missing)
    noun = "slice" if len(missing) == 1 else "slices"
    return (
        f"FED is disabled for {fds_dir}: it has no {named} {noun}, and all "
        "three of CO, CO2 and O2 are needed. Results will report zero dose and "
        "no incapacitation. FDS only writes these species when the &REAC line "
        f"asks for them (CO needs CO_YIELD); see {FDS_CASE_DOCS}"
    )


def heat_without_temperature(fds_dir: str) -> str:
    """D12: --enable-heat-fed on a case with no TEMPERATURE slice."""
    return (
        f"Heat FED is disabled for {fds_dir}: it has no TEMPERATURE slice. "
        "Results will report zero heat dose and no thermal "
        "incapacitation. Add `&SLCF QUANTITY='TEMPERATURE'` to the FDS "
        f"deck; see {FDS_CASE_DOCS}"
    )


def heat_option_without_enable(flag: str) -> str:
    """D13: a heat law option given with --fds-dir but no --enable-heat-fed."""
    return f"{flag} has no effect without --enable-heat-fed."


HEAT_CLOTHING_OVERRIDDEN = (
    "--heat-clothing has no effect with --heat-endpoint or "
    "--heat-fed-method total-flux."
)
"""D15: the clothing law is replaced by an endpoint or total-flux law."""


def heat_threshold_departs(value: object) -> str:
    """D22: a heat threshold apart from the gas threshold."""
    return (
        f"--heat-fed-threshold {value} departs from ISO 13571:2012, which uses "
        "one threshold for FED and FEC (5.4) and treats heat in the same manner "
        "(8.5); the manifest records it."
    )


def visibility_without_extinction(fds_dir: str) -> str:
    """D28: the smoke-aware vismap falls back to clear air."""
    return (
        f"Visibility falls back to clear air for {fds_dir}: it has no SOOT "
        "EXTINCTION COEFFICIENT slice, so smoke hides no sign; geometry "
        "and sign facing still do."
    )


REPLAY_WITH_REROUTING = (
    "--replay-exits with rerouting on: agents start at the replayed exit "
    "but may switch. Pass --no-enable-rerouting to keep every exit."
)
"""D30: rerouting may undo a replayed exit."""


# --- warnings (status log lines) -------------------------------------------

NO_SIGNS = "Warning: visibility gating requested but the config has no signs."
"""D27: gating asked for, but the scenario has no sign."""


def horizon_overrun(max_time: float, fds_dir: str, last: float, interval: float) -> str:
    """D32: how max_simulation_time outlasts the FDS output."""
    return (
        f"max_simulation_time={float(max_time):.1f} s runs past the FDS output "
        f"of {fds_dir}, which ends at t={last:.1f} s (output interval "
        f"{interval:.1f} s)"
    )


def horizon_hold(overrun: str) -> str:
    """D32 with --allow-fds-horizon-hold: the status line."""
    return f"Warning: {overrun}; holding the last frame from there on."


# --- errors ----------------------------------------------------------------


def horizon_error(overrun: str) -> str:
    """D32 without --allow-fds-horizon-hold."""
    return (
        f"{overrun}. Lower max_simulation_time, extend T_END in the FDS run, "
        "or pass --allow-fds-horizon-hold to hold the last frame."
    )


INSPECT_NEEDS_FDS = "--inspect-fds requires --fds-dir"
VIS_CACHE_NEEDS_REROUTING = "--vis-cache requires --enable-rerouting"
CLEAR_AIR_CONTRADICTS_FDS = (
    "--clear-air-visibility contradicts --fds-dir: the deck has a fire, "
    "so its smoke is what decides what an agent can see"
)
NO_VISIBILITY_CONFLICT = "--no-visibility and --clear-air-visibility conflict"
LAYER_NEEDS_TOTAL_FLUX = "--heat-regime layer needs --heat-fed-method total-flux"
LAYER_HEIGHT_NOT_FINITE = "--heat-layer-height must be finite"


def layer_needs(flag: str) -> str:
    """D19: a layer value is missing."""
    return f"--heat-regime layer needs {flag}"


INTEGRATED_INTENSITY_NEEDS_TOTAL_FLUX = (
    "--heat-radiant-source integrated-intensity needs --heat-fed-method total-flux."
)
INTEGRATED_INTENSITY_NEEDS_U = (
    "--heat-radiant-source integrated-intensity needs --heat-u-factor "
    "in [0.25, 1]; there is no default."
)


def integrated_intensity_slice_missing(fds_dir: str) -> str:
    """D17: the case has no INTEGRATED INTENSITY slice."""
    return (
        f"{fds_dir} has no INTEGRATED INTENSITY slice. Add "
        "`&SLCF QUANTITY='INTEGRATED INTENSITY'` at the slice height."
    )
