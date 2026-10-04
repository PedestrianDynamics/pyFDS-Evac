"""Values shared by the GUI and TUI round-trip tests (#532).

Not a test module: ``tests/test_webapp.py`` and ``tests/test_tui.py``
import it, so both front ends are checked with the same settings.
"""

from __future__ import annotations

# One non-default value the parser accepts for each option a front end
# shows, "on"/"off" for a switch. No single form passes validate_opts with
# all of them (--vis-cache requires rerouting), so they are split into two
# valid profiles. The None-default options get an
# explicit 0 where the parser accepts it, so 0 stays apart from "unset".
ZERO = (
    "seed",
    "constant_extinction",
    "heat_layer_height",
    "heat_view_factor",
    "heat_layer_emissivity",
    "heat_fed_threshold",
)
PROFILE_A = {
    "seed": "0",
    "constant_extinction": "0",
    "smoke_update_interval": "2.5",
    "smoke_slice_height": "1.8",
    "allow_fds_horizon_hold": "on",
    "require_fds_coverage": "on",
    "debug": "on",
    "enable_rerouting": "off",
    "disable_tenability": "on",
    "clear_air_visibility": "on",
    "vis_cell_size": "0.5",
    "max_sign_distance": "20.0",
    "incapacitation_mode": "probabilistic",
    "susceptibility_sigma": "0.5",
    "fed_threshold": "0.3",
    "o2_threshold_percent": "15.0",
    "enable_fic_speed": "on",
    "fic_alpha": "0.5",
    "fic_min_factor": "0.2",
}
PROFILE_B = {
    "smoke_blind": "on",
    "replay_exits": "exits/replay.csv",
    "vis_cache": "cache/vis.npz",
    "reroute_interval": "3.0",
    "no_visibility": "on",
    "enable_heat_fed": "on",
    "heat_clothing": "unclothed",
    "heat_endpoint": "injury",
    "heat_fed_method": "total-flux",
    "heat_emissivity": "0.9",
    "heat_convective_coefficient": "8.0",
    "heat_skin_temperature": "34.0",
    "heat_radiant_source": "integrated-intensity",
    "heat_u_factor": "0.5",
    "heat_regime": "layer",
    "heat_layer_height": "0",
    "heat_view_factor": "0",
    "heat_layer_emissivity": "0",
    "heat_fed_threshold": "0",
    "heat_incapacitation_mode": "probabilistic",
    "heat_susceptibility_sigma": "0.5",
}
# Path options the script resolves (PATHS block) or should resolve (#558).
PATHS = ("fds_dir", "vis_cache", "replay_exits")
# Options the layer regime needs: the stale-note test changes their value
# instead of removing them, since the form would no longer resolve.
ALT = {
    "heat_layer_height": "1.0",
    "heat_view_factor": "0.5",
    "heat_layer_emissivity": "0.5",
}
LAYER = ("heat_regime", *ALT)


def shown() -> set[str]:
    """Run options a front end shows and the user sets (not output paths)."""
    from pyfds_evac.config.parameters import GUI_HIDDEN, RUN_OPTIONS
    from pyfds_evac.config.script import OMITTED_OUTPUT_KEYS

    return set(RUN_OPTIONS) - GUI_HIDDEN - set(OMITTED_OUTPUT_KEYS) - {"scenario"}


def hidden() -> set[str]:
    """Run options no front end shows; they must stay at the default."""
    from pyfds_evac.config.parameters import GUI_HIDDEN, RUN_OPTIONS

    return set(RUN_OPTIONS) & GUI_HIDDEN


def script_literals(code: str) -> dict:
    """PATHS and OPTIONS of a generated script, read without running it."""
    import ast

    from pyfds_evac.config.script import _PATH_KEYS

    names = {"OPTIONS", *(key.upper() for key in _PATH_KEYS)}
    tree = ast.parse(code)
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", None)
        if name in names:
            found[name] = ast.literal_eval(node.value)
    return found


def argv(form: dict) -> list[str]:
    """The pyfds-evac arguments that set what *form* sets."""
    from pyfds_evac.cli import _build_parser

    actions = {a.dest: a for a in _build_parser()._actions}
    words: list[str] = []
    for dest, value in form.items():
        flags = actions[dest].option_strings
        if value == "on":
            words.append(flags[0])
        elif value == "off":
            words.append(next(f for f in flags if f.startswith("--no-")))
        else:
            words += [flags[0], value]
    return words


def same_path(a, b) -> bool:
    """Whether *a* and *b* name the same file, as this process resolves them."""
    from pathlib import Path

    return Path(a).resolve() == Path(b).resolve()
