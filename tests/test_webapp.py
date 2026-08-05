"""End-to-end tests for the FastHTML web GUI via Starlette's TestClient."""

import pytest

pytest.importorskip("fasthtml")
pytest.importorskip("monsterui")

from starlette.testclient import TestClient  # noqa: E402

from pyfds_evac.webapp.app import app, manager  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_index_renders_form(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/run" in r.text
    assert "ISO-table21" in r.text  # scenario picker populated from assets/
    assert 'id="dir-modal"' in r.text  # directory-browser overlay container
    assert "output_route_cost_history" in r.text  # output fields rendered
    assert "_smoke_history.csv" in r.text  # scenario-name autofill script present
    assert 'data-tab="model"' in r.text  # Model documentation tab present
    assert "Fractional Effective Dose" in r.text  # model docs content rendered


def test_scenario_picker_lists_alternate_json_configs():
    # The picker offers the directory (config.json) plus each alternate *.json,
    # mirroring the CLI --scenario which accepts a JSON file path.
    from pyfds_evac.webapp.params import _scenario_options

    options = dict((value, label) for label, value in _scenario_options())
    assert "t_junction" in options  # directory entry → config.json
    assert "t_junction/config_full.json" in options  # alternate config selectable
    assert "config.json" not in "".join(
        v for v in options if v.endswith("/config.json")
    )  # config.json is not duplicated as a file entry


def test_browse_dir_lists_subfolders(client):
    r = client.get("/browse-dir")
    assert r.status_code == 200
    assert "Select a folder" in r.text
    assert "assets" in r.text  # repo-root subfolders are listed


def test_browse_dir_file_mode_lists_files(client):
    # File mode (used by vis_cache) lists files as well as folders.
    r = client.get("/browse-dir", params={"mode": "file", "field": "vis_cache"})
    assert r.status_code == 200
    assert "Select a file" in r.text
    assert "pyproject.toml" in r.text  # a file at the repo root


def test_browse_dir_clamps_outside_home(client):
    # A path outside the home tree must clamp back to the home root.
    from pathlib import Path

    r = client.get("/browse-dir", params={"path": "/etc"})
    assert r.status_code == 200
    assert str(Path.home()) in r.text
    assert ">/etc<" not in r.text


def test_run_without_scenario_shows_error(client):
    r = client.post("/run", data={})
    assert r.status_code == 200
    assert "Select a scenario first" in r.text


def test_invalid_option_combo_shows_error(client, tmp_path):
    # --vis-cache requires --enable-rerouting; build_run_kwargs must reject it.
    # fds_dir must be a real directory, otherwise the handler rejects it on the
    # earlier "not a directory" check and never reaches the rule under test.
    r = client.post(
        "/run",
        data={
            "scenario": "ISO-table21",
            "vis_cache": "x.pkl",
            "fds_dir": str(tmp_path),
        },
    )
    assert r.status_code == 200
    assert "enable-rerouting" in r.text


def _stream_until_terminal(client, max_lines=2000):
    events = []
    with client.stream("GET", "/progress") as s:
        for i, line in enumerate(s.iter_lines()):
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
                if events[-1] in ("done", "error"):
                    break
            if i > max_lines:
                break
    return events


def test_full_run_streams_progress_and_completes(client):
    r = client.post("/run", data={"scenario": "ISO-table21", "seed": "420"})
    assert r.status_code == 200
    assert 'sse-connect="/progress"' in r.text or "sse_connect" in r.text

    events = _stream_until_terminal(client)
    assert "progress" in events
    assert events[-1] == "done"
    assert manager.status == "done"
    assert manager.result is not None
    assert manager.result.total_agents >= 1
    if manager.result.sqlite_file:
        manager.result.cleanup()


def test_second_run_rejected_while_active(client):
    # Hold the lock by faking an active run, then ensure start() refuses.
    from pyfds_evac.core import load_scenario
    from pyfds_evac.core.run_config import build_run_kwargs
    from argparse import Namespace

    scenario = load_scenario("assets/ISO-table21")
    opts = Namespace(
        seed=420,
        fds_dir=None,
        constant_extinction=None,
        smoke_update_interval=1.0,
        smoke_slice_height=2.0,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        disable_tenability=False,
        fic_alpha=1.2,
        fic_min_factor=0.0,
        fed_threshold=1.0,
        output_route_cost_history=None,
        collect_route_cost_history=True,
    )
    kwargs = build_run_kwargs(scenario, opts)
    manager.start(scenario, kwargs, "ISO-table21")
    with pytest.raises(RuntimeError):
        manager.start(scenario, kwargs, "ISO-table21")
    # Drain to completion so the lock releases for other tests.
    _stream_until_terminal(client)
    if manager.result and manager.result.sqlite_file:
        manager.result.cleanup()
