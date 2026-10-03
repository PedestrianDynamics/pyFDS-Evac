"""One configuration model for the CLI, the GUI and the TUI (#484).

``pyfds_evac.config`` holds every run option once; the parser, the GUI form,
the effective configuration and the equivalent command are built from it.
These tests pin that the model reproduces today's parser and run wiring,
and that the effective configuration predicts what ``build_run_kwargs``
logs and raises.

FDS fixtures: ``assets/iso_table22_coupled/fds/a`` (CO, CO2, O2, soot;
1150 s) and ``assets/heat_only_no_soot/fds`` (one TEMPERATURE slice, 3 s).
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import pickle
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from pyfds_evac import cli
from pyfds_evac.config import (
    DEFAULTS,
    PARAMETERS,
    RUN_OPTIONS,
    effective_configuration,
    events,
    parameter,
    python_script,
)
from pyfds_evac.config.effective import cli_command
from pyfds_evac.config.rules import FdsFacts, check_options
from pyfds_evac.core.run_config import build_run_kwargs, validate_opts

REPO = Path(__file__).resolve().parents[1]
ISO22 = REPO / "assets" / "iso_table22_coupled"
ISO22_A = str(ISO22 / "fds" / "a")
HEAT_ONLY_FDS = str(REPO / "assets" / "heat_only_no_soot" / "fds")
HEAT_150 = str(REPO / "assets" / "fed_incap_heat_150c")
T_JUNCTION_DISCOVERY = str(REPO / "assets" / "t_junction" / "config_discovery.json")
DISCOVERY = str(REPO / "assets" / "familiarity_test_discovery" / "config.json")


def _parse(*argv: str) -> argparse.Namespace:
    return cli._build_parser().parse_args(list(argv))


def _load(path: str):
    from pyfds_evac.core.scenario import load_scenario

    return load_scenario(path)


# --- the parameter table is the parser -------------------------------------


def test_parser_actions_follow_the_parameter_table():
    actions = [a for a in cli._build_parser()._actions if a.dest != "help"]
    assert [a.dest for a in actions] == [p.dest for p in PARAMETERS]
    for action, param in zip(actions, PARAMETERS, strict=True):
        assert tuple(action.option_strings[:1]) == param.flags
        assert action.default == param.default, param.dest
        assert action.help == param.help, param.dest
        if param.choices is not None:
            assert tuple(action.choices) == param.choices


def test_parser_defaults_are_the_model_defaults():
    namespace = vars(_parse("--scenario", "x"))
    assert namespace == {**DEFAULTS, "scenario": "x"}


def test_python_defaults_of_the_model_match_the_code():
    """The Python-API defaults the model reports are the code's (X1-X3)."""
    from pyfds_evac.core.fed import DefaultFedConfig, TenabilityConfig
    from pyfds_evac.core.route_graph import RerouteConfig
    from pyfds_evac.core.visibility import (
        DEFAULT_MAX_SIGN_DISTANCE_M,
        VisibilityModel,
    )

    assert (
        RerouteConfig().reevaluation_interval_s
        == parameter("reroute_interval").python_default
    )
    clear_air = inspect.signature(VisibilityModel.clear_air).parameters
    assert clear_air["cell_size_m"].default == parameter("vis_cell_size").python_default
    assert DEFAULT_MAX_SIGN_DISTANCE_M == parameter("max_sign_distance").default
    tenability = TenabilityConfig()
    for dest in (
        "fic_alpha",
        "fic_min_factor",
        "fed_threshold",
        "incapacitation_mode",
        "susceptibility_sigma",
        "heat_incapacitation_mode",
        "heat_susceptibility_sigma",
    ):
        assert getattr(tenability, dest) == parameter(dest).default, dest
    fed_fields = {
        f.name: f.default for f in DefaultFedConfig.__dataclass_fields__.values()
    }
    assert (
        fed_fields["o2_threshold_percent"] == parameter("o2_threshold_percent").default
    )


def test_gui_metadata_comes_from_the_model():
    from pyfds_evac.config.parameters import GUI_SECTIONS, GUI_UNIT_LABELS
    from pyfds_evac.webapp import params

    assert params.FIELD_GROUPS == [(t, list(d)) for t, d in GUI_SECTIONS]
    assert params._UNITS == {d: parameter(d).unit for d in GUI_UNIT_LABELS}
    assert "show_config" in params._HIDDEN
    form = params.form_to_opts({"scenario": "t_junction"}, baseseed=1, stamp="x")
    assert not hasattr(form, "show_config")


# --- cold start ------------------------------------------------------------

_HEAVY = (
    "jupedsim",
    "fdsreader",
    "fdsvismap",
    "matplotlib",
    "pedpy",
    "pyfds_evac.core.scenario",
)

_PROBE = """\
import argparse, sys
import pyfds_evac.config as config
before = [m for m in {heavy!r} + ("shapely",) if m in sys.modules]
from pyfds_evac.config import effective_configuration
opts = argparse.Namespace(**{{**config.DEFAULTS, "scenario": "s.json",
    "fds_dir": "case", "enable_heat_fed": True}})
raw = {{"distributions": {{"a": {{"parameters": {{"familiarity": 0.0}}}}}},
    "exits": {{"e": {{"sign": {{"x": 0.0, "y": 0.0}}}}}},
    "routing": {{"w_smoke": 2.0}}}}
cfg = effective_configuration(opts, raw, inspect_fds=False)
assert cfg.level == 1, cfg.level
assert cfg._mechanisms.signs == 1 and cfg.routing[0].key == "w_smoke"
after = [m for m in {heavy!r} if m in sys.modules]
print(before, after)
"""


def test_config_and_level_one_load_no_simulation_stack():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(heavy=_HEAVY)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "[] []"


# --- validation parity (T8) ------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--vis-cache", "x.npz", "--no-enable-rerouting"],
        ["--clear-air-visibility", "--fds-dir", "case"],
        ["--no-visibility", "--clear-air-visibility"],
        ["--enable-heat-fed", "--heat-regime", "layer"],
        [
            "--enable-heat-fed",
            "--heat-regime",
            "layer",
            "--heat-fed-method",
            "total-flux",
        ],
        [
            "--enable-heat-fed",
            "--heat-regime",
            "layer",
            "--heat-fed-method",
            "total-flux",
            "--heat-layer-height",
            "inf",
            "--heat-view-factor",
            "1",
            "--heat-layer-emissivity",
            "1",
        ],
    ],
)
def test_option_errors_have_the_cli_message(argv):
    opts = _parse("--scenario", "x", *argv)
    with pytest.raises(ValueError) as raised:
        validate_opts(opts)
    issues = check_options(opts)
    assert issues[0].message == str(raised.value)
    errors = effective_configuration(opts, {}, inspect_fds=False).errors
    assert errors[0].message == str(raised.value)


@pytest.mark.parametrize(
    "argv",
    [
        ["--reroute-interval", "0"],
        ["--susceptibility-sigma", "-1"],
        ["--heat-emissivity", "2"],
        ["--constant-extinction", "-1"],
        ["--seed", "-3"],
    ],
)
def test_values_the_cli_accepts_are_not_errors(argv):
    """X12/M4: the model rejects nothing the CLI accepts."""
    opts = _parse("--scenario", "x", *argv)
    validate_opts(opts)
    assert effective_configuration(opts, {}, inspect_fds=False).ok


# --- options with no effect (X11, M2) --------------------------------------

_NO_FIRE = {"distributions": {}}


def _inactive(*argv: str, raw=None, fds=None) -> dict[str, str]:
    opts = _parse("--scenario", "x", *argv)
    cfg = effective_configuration(
        opts, _NO_FIRE if raw is None else raw, fds=fds, inspect_fds=False
    )
    return {i.option: i.message for i in cfg.inactive}


def test_default_options_have_no_inactive_setting():
    assert _inactive() == {}
    assert _inactive("--fds-dir", "case") == {}


def test_r3_settings_without_fire_data_have_no_effect():
    """R3 of the contract: silent on main, a warning each now."""
    found = _inactive(
        "--constant-extinction",
        "0.5",
        "--enable-fic-speed",
        "--incapacitation-mode",
        "probabilistic",
        "--heat-clothing",
        "unclothed",
    )
    assert found == {
        "enable_fic_speed": "--enable-fic-speed has no effect without --fds-dir.",
        "incapacitation_mode": "--incapacitation-mode has no effect without --fds-dir.",
        "heat_clothing": "--heat-clothing has no effect without --fds-dir.",
    }


@pytest.mark.parametrize(
    ("argv", "dest", "reason"),
    [
        (["--smoke-slice-height", "2.0"], "smoke_slice_height", "without --fds-dir"),
        (
            ["--smoke-update-interval", "2"],
            "smoke_update_interval",
            "without --fds-dir or --constant-extinction",
        ),
        (["--fic-alpha", "0.5"], "fic_alpha", "without --enable-fic-speed"),
        (
            ["--fds-dir", "c", "--susceptibility-sigma", "0.5"],
            "susceptibility_sigma",
            "without --incapacitation-mode probabilistic",
        ),
        (
            ["--fds-dir", "c", "--enable-heat-fed", "--heat-emissivity", "0.9"],
            "heat_emissivity",
            "without --heat-fed-method total-flux",
        ),
        (
            ["--fds-dir", "c", "--enable-heat-fed", "--heat-u-factor", "0.5"],
            "heat_u_factor",
            "without --heat-radiant-source integrated-intensity",
        ),
        (
            ["--fds-dir", "c", "--enable-heat-fed", "--heat-view-factor", "1"],
            "heat_view_factor",
            "without --heat-regime layer",
        ),
        (
            ["--fds-dir", "c", "--heat-fed-threshold", "0.5"],
            "heat_fed_threshold",
            "without --enable-heat-fed",
        ),
        (
            ["--no-enable-rerouting", "--reroute-interval", "5"],
            "reroute_interval",
            "with --no-enable-rerouting",
        ),
        (["--vis-cell-size", "0.5"], "vis_cell_size", "without a visibility model"),
        (
            ["--fds-dir", "c", "--disable-tenability", "--fed-threshold", "0.3"],
            "fed_threshold",
            "with --disable-tenability",
        ),
    ],
)
def test_inactive_reason(argv, dest, reason):
    found = _inactive(*argv)
    assert dest in found, found
    assert reason in found[dest]


def test_reroute_interval_is_the_smoky_vismap_time_step():
    """D23: with rerouting off it still sets the vismap time step."""
    raw = {"distributions": {"a": {"parameters": {"familiarity": 0.0}}}}
    facts = FdsFacts(frozenset({"extinction"}))
    opts = ["--fds-dir", "c", "--no-enable-rerouting", "--reroute-interval", "5"]
    signs = {"exits": {"e": {"sign": {"x": 0.0, "y": 0.0}}}}
    assert "reroute_interval" not in _inactive(*opts, raw={**raw, **signs}, fds=facts)


def test_update_interval_acts_with_a_constant_extinction():
    """D5 exception: the update interval also times a constant K."""
    found = _inactive("--constant-extinction", "0.5", "--smoke-update-interval", "2")
    assert "smoke_update_interval" not in found


# --- the run logs what the model predicts (T7) -----------------------------


class _Collect(logging.Handler):
    def __init__(self, sink: list[str]):
        super().__init__(logging.WARNING)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.append(record.getMessage())


def _setup_warnings(caplog, scenario, opts) -> list[str]:
    """Logger warnings and ``Warning:`` lines of ``build_run_kwargs``, in order."""
    found: list[str] = []
    handler = _Collect(found)
    logger = logging.getLogger("pyfds_evac")
    logger.addHandler(handler)
    try:
        build_run_kwargs(
            scenario,
            opts,
            log=lambda line: (
                found.append(line) if line.startswith("Warning:") else None
            ),
        )
    finally:
        logger.removeHandler(handler)
    return found


@pytest.fixture(scope="module")
def iso22_scenario():
    return _load(str(ISO22 / "config_a.json"))


@pytest.mark.parametrize(
    "argv",
    [
        ["--seed", "7", "--enable-fic-speed", "--incapacitation-mode", "probabilistic"],
        ["--seed", "7", "--enable-heat-fed"],
        ["--heat-clothing", "unclothed", "--heat-endpoint", "fatal"],
        ["--enable-heat-fed", "--heat-u-factor", "0.5", "--fic-alpha", "0.1"],
        ["--disable-tenability", "--o2-threshold-percent", "19.5"],
        ["--smoke-blind", "--enable-fic-speed"],
    ],
)
def test_effective_warnings_are_the_run_warnings(caplog, iso22_scenario, argv):
    opts = _parse("--scenario", "x", "--fds-dir", ISO22_A, *argv)
    predicted = effective_configuration(opts, iso22_scenario).warnings
    assert list(predicted) == _setup_warnings(caplog, iso22_scenario, opts)


def test_r2p_has_no_warning_and_its_mechanisms(iso22_scenario):
    opts = _parse(
        "--scenario",
        str(ISO22 / "config_a.json"),
        "--fds-dir",
        ISO22_A,
        "--seed",
        "7",
        "--enable-fic-speed",
        "--incapacitation-mode",
        "probabilistic",
    )
    cfg = effective_configuration(opts, iso22_scenario)
    assert cfg.level == 2
    assert cfg.fds_slices == ("co", "co2", "extinction", "o2")
    assert cfg.warnings == () and cfg.inactive == () and cfg.ok
    on = {m.name: m.on for m in cfg.mechanisms}
    assert on["smoke_speed"] and on["gas_fed"] and on["tenability"]
    assert not on["heat_fed"] and not on["visibility"]
    assert cfg.inputs["seed"] == 7 and cfg.inputs["seed_origin"] == "option"
    departs = {o.option for o in cfg.options if o.departs_from_fds_evac}
    assert departs == {"enable_fic_speed", "incapacitation_mode"}
    routing = {r.key: r.value for r in cfg.routing if r.overridden}
    assert routing["w_smoke"] == 0.0 and routing["w_fed"] == 0.0


@pytest.fixture(scope="module")
def heat_scenario():
    return _load(HEAT_150)


@pytest.mark.parametrize(
    "argv",
    [
        ["--enable-heat-fed", "--allow-fds-horizon-hold"],
        ["--allow-fds-horizon-hold", "--heat-regime", "layer"],
        [
            "--enable-heat-fed",
            "--allow-fds-horizon-hold",
            "--heat-fed-threshold",
            "0.5",
        ],
    ],
)
def test_heat_only_case_warnings_are_predicted(caplog, heat_scenario, argv):
    """D3, D6, D12-D13, D22, D28, D32 (hold) on a TEMPERATURE-only case."""
    opts = _parse("--scenario", "x", "--fds-dir", HEAT_ONLY_FDS, *argv)
    predicted = effective_configuration(opts, heat_scenario).warnings
    assert list(predicted) == _setup_warnings(caplog, heat_scenario, opts)


def test_horizon_error_is_predicted(heat_scenario):
    """D32: the run stops at setup; the model reports the same message."""
    opts = _parse("--scenario", "x", "--fds-dir", HEAT_ONLY_FDS, "--enable-heat-fed")
    with pytest.raises(ValueError) as raised:
        build_run_kwargs(heat_scenario, opts)
    errors = effective_configuration(opts, heat_scenario).errors
    assert [e.rule for e in errors] == ["D32"]
    assert errors[0].message == str(raised.value)


def test_new_warnings_are_logged_once(caplog):
    scenario = _load(T_JUNCTION_DISCOVERY)
    opts = _parse(
        "--scenario",
        T_JUNCTION_DISCOVERY,
        "--no-visibility",
        "--constant-extinction",
        "0.5",
        "--enable-fic-speed",
        "--heat-clothing",
        "unclothed",
    )
    warnings = _setup_warnings(caplog, scenario, opts)
    assert warnings == [
        "--enable-fic-speed has no effect without --fds-dir.",
        "--heat-clothing has no effect without --fds-dir.",
    ]


# --- equivalent command and script (T8b) -----------------------------------


def _run_options(opts) -> dict:
    return {dest: getattr(opts, dest) for dest in RUN_OPTIONS}


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--seed", "-3", "--no-enable-rerouting", "--reroute-interval", "0.1"],
        ["--fds-dir", "dir with space", "--heat-u-factor", "0.3333333333333333"],
        ["--enable-heat-fed", "--heat-endpoint", "fatal", "--output-sqlite", "o.db"],
    ],
)
def test_cli_command_parses_back_to_the_options(argv):
    opts = _parse("--scenario", "my scenario.json", *argv)
    command = cli_command(opts)
    words = shlex.split(command)
    assert words[0] == "pyfds-evac"
    assert _run_options(_parse(*words[1:])) == _run_options(opts)


def test_gui_form_command_runs_the_same_options():
    """The GUI's opts.scenario is a picker value; the command needs the file."""
    from pyfds_evac.webapp import app

    form = {"scenario": "t_junction", "seed": "7", "enable_rerouting": "off"}
    scenario, opts = app._resolve_form(form, stamp="20260101T000000Z")
    command = effective_configuration(opts, scenario, inspect_fds=False).command
    back = _parse(*shlex.split(command)[1:])
    assert Path(back.scenario).exists()
    assert back.scenario == scenario.source_path
    expected = {**_run_options(opts), "scenario": scenario.source_path}
    assert _run_options(back) == expected


def test_python_script_compiles_and_skips_command_flags():
    code = python_script(_parse("--scenario", "x.json", "--show-config"))
    compile(code, "script.py", "exec")
    assert "show_config" not in code
    assert "build_run_kwargs(scenario, opts" in code


# --- the CLI ---------------------------------------------------------------


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pyfds_evac", *argv],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_show_config_prints_and_exits_without_running():
    proc = _cli("--scenario", DISCOVERY, "--show-config")
    assert proc.returncode == 0, proc.stderr
    assert "Effective configuration (level 2" in proc.stdout
    assert "clear air, 5 signs, 0.25 m grid" in proc.stdout
    assert "Simulation started." not in proc.stdout


def test_show_config_exits_1_on_a_configuration_error():
    proc = _cli(
        "--scenario",
        DISCOVERY,
        "--vis-cache",
        "x.npz",
        "--no-enable-rerouting",
        "--show-config",
    )
    assert proc.returncode == 1
    assert "  --vis-cache requires --enable-rerouting\n" in proc.stdout


def test_show_config_keeps_the_check_order():
    """--export-only still returns first; a missing scenario still raises."""
    proc = _cli("--scenario", DISCOVERY, "--export-only", "--show-config")
    assert proc.returncode == 0 and "Effective configuration" not in proc.stdout
    proc = _cli("--scenario", "nope.json", "--show-config")
    assert proc.returncode == 1 and "FileNotFoundError" in proc.stderr


def test_manifest_records_the_configuration(tmp_path):
    """The copied manifest gains a ``configuration`` section, nothing else."""
    scenario = _load(DISCOVERY)
    source = tmp_path / "run.sqlite"
    source.write_bytes(b"")
    manifest = tmp_path / "run.manifest.json"
    original = {"seed": 420, "scenario_path": DISCOVERY}
    manifest.write_text(json.dumps(original))

    class Result:
        sqlite_file = str(source)
        manifest_file = str(manifest)
        smoke_history = fed_history = route_history = None
        route_cost_history = exit_history = None

    opts = _parse(
        "--scenario", DISCOVERY, "--output-sqlite", str(tmp_path / "o" / "r.sqlite")
    )
    cli.apply_outputs(Result(), scenario, opts, log=lambda _m: None)
    written = json.loads((tmp_path / "o" / "r.manifest.json").read_text())
    section = written.pop("configuration")
    assert written == original
    assert section["schema"] == 1 and section["provisional"] is True
    assert section["mechanisms"]["visibility"]["on"] is True
    assert section["command"].startswith("pyfds-evac --scenario ")


# --- run events (#485) -----------------------------------------------------


def test_events_pickle_across_processes():
    for event in (
        events.PhaseEvent(events.PHASE_RUNNING),
        events.WarningEvent("text", logger="pyfds_evac.core.run_config"),
        events.ResultEvent(events.STATUS_INCOMPLETE, 2, files=("a.sqlite",)),
    ):
        assert pickle.loads(pickle.dumps(event)) == event
    assert events.EXIT_CODES[events.result_status(False)] == cli.EXIT_INCOMPLETE


def test_progress_events_count_incapacitated_agents(iso22_scenario):
    from pyfds_evac.core import ProgressEvent, run_scenario

    opts = _parse("--scenario", "x", "--fds-dir", ISO22_A, "--seed", "7")
    seen: list[ProgressEvent] = []
    result = run_scenario(
        iso22_scenario,
        progress_callback=seen.append,
        **build_run_kwargs(iso22_scenario, opts),
    )
    result.cleanup()
    incapacitated = {r["agent_id"] for r in result.fed_history if r["incapacitated"]}
    assert len(incapacitated) == 1  # the occupant of R2p, at 982 s
    assert seen[-1].incapacitated == 1
    assert all(e.not_spawned == 0 for e in seen)
