"""End-to-end tests for the FastHTML web GUI via Starlette's TestClient."""

import io
import pathlib
import re
import shutil
import zipfile
from types import SimpleNamespace

import pytest

pytest.importorskip("fasthtml")
pytest.importorskip("monsterui")

from starlette.testclient import TestClient

from pyfds_evac.webapp.app import app, manager


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def results_root(tmp_path, monkeypatch):
    """Derived output folders go to a temp root, not the repository."""
    from pyfds_evac.webapp.params import RESULTS_ENV

    root = tmp_path / "results"
    monkeypatch.setenv(RESULTS_ENV, str(root))
    return root


@pytest.fixture(autouse=True)
def idle_manager():
    """Each test starts from, and leaves, an idle run panel.

    The page renders the server's run state, so a finished run left behind
    by one test would otherwise show up on the next test's page.
    """
    manager.join(10.0)
    manager.reset()
    yield
    manager.join(10.0)
    manager.reset()


def test_index_renders_form(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/run" in r.text
    assert "ISO-table21" in r.text  # scenario picker populated from assets/
    assert 'id="dir-modal"' in r.text  # directory-browser overlay container
    assert 'id="output_base"' in r.text  # output folder rendered
    assert "_smoke_history.csv" in r.text  # file-name preview present
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
            "enable_rerouting": "off",  # the switch's unchecked sentinel
        },
    )
    assert r.status_code == 200
    assert "enable-rerouting" in r.text


def _drop_temp_trajectory():
    """Delete the run's temp sqlite, tolerating a Windows file lock.

    Building the finished view reads the trajectory through pedpy, and on
    Windows that handle can outlive the read, so unlink raises PermissionError.
    It's a temp file either way, and the lock is not what any test is asserting.
    """
    result = manager.result
    if result and result.sqlite_file:
        try:
            result.cleanup()
        except OSError:
            pass


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
    assert 'sse-connect="/progress' in r.text or "sse_connect" in r.text

    events = _stream_until_terminal(client)
    assert "progress" in events
    assert events[-1] == "done"
    assert manager.status == "done"
    assert manager.result is not None
    assert manager.result.total_agents >= 1
    _drop_temp_trajectory()


def test_second_run_rejected_while_active(client):
    # Hold the lock by faking an active run, then ensure start() refuses.
    from argparse import Namespace

    from pyfds_evac.core import load_scenario
    from pyfds_evac.core.run_config import build_run_kwargs

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
    # start() takes a builder, not the kwargs themselves: the expensive part of
    # build_run_kwargs runs on the worker thread so /run can answer straight
    # away. Prebuilt here, since this test is about the second-run guard; the
    # builder holds the worker until the guard has been checked, otherwise a
    # fast run can finish and release the lock first.
    import threading

    release = threading.Event()

    def hold_then_build():
        release.wait(5.0)
        return kwargs

    manager.start(scenario, hold_then_build, "ISO-table21")
    try:
        with pytest.raises(RuntimeError):
            manager.start(scenario, lambda: kwargs, "ISO-table21")
    finally:
        release.set()
    # Drain to completion so the lock releases for other tests.
    _stream_until_terminal(client)
    _drop_temp_trajectory()


class TestCancelLifecycle:
    """A cancel is honoured at every phase and the UI waits for the worker.

    ``run_scenario`` is replaced by a stub and each phase is held open on an
    Event, so the tests decide exactly where the cancel lands.
    """

    @pytest.fixture
    def rm(self, monkeypatch):
        import pyfds_evac.webapp.app as app_module
        from pyfds_evac.webapp.runner import RunManager

        calls = {"run": 0, "post": 0}
        gate = {"build": None, "post": None}

        def fake_run_scenario(scenario, progress_callback=None, **kwargs):
            calls["run"] += 1
            return SimpleNamespace(sqlite_file=None)

        monkeypatch.setattr("pyfds_evac.webapp.runner.run_scenario", fake_run_scenario)
        fresh = RunManager()
        monkeypatch.setattr(app_module, "manager", fresh)
        monkeypatch.setattr(app_module, "_CANCEL_WAIT_S", 0.05)
        yield fresh, calls, gate
        for ev in gate.values():
            if ev is not None:
                ev.set()
        fresh.join(5.0)

    @staticmethod
    def _blocking(gate, key, entered):
        import threading

        gate[key] = threading.Event()

        def wait(*_a):
            entered.set()
            gate[key].wait(5.0)
            return {}

        return wait

    def test_cancel_while_building_kwargs_skips_the_run(self, rm):
        import threading

        mgr, calls, gate = rm
        entered = threading.Event()
        post = []
        mgr.start(
            None,
            self._blocking(gate, "build", entered),
            "stub",
            post_run=lambda r: post.append(r) or [],
        )
        assert entered.wait(5.0)
        assert mgr.cancel() is True
        assert mgr.status == "cancelling"
        assert mgr.running
        gate["build"].set()
        assert mgr.join(5.0)
        assert mgr.status == "cancelled"
        assert calls["run"] == 0
        assert post == []

    def test_cancel_during_post_run_ends_cancelled(self, rm):
        import threading

        mgr, calls, gate = rm
        entered = threading.Event()
        blocking_post = self._blocking(gate, "post", entered)
        mgr.start(None, dict, "stub", post_run=lambda r: blocking_post() and [])
        assert entered.wait(5.0)
        assert mgr.cancel() is True
        gate["post"].set()
        assert mgr.join(5.0)
        assert mgr.status == "cancelled"
        assert mgr.result is None
        assert calls["run"] == 1

    def test_reset_is_refused_while_cancelling(self, rm):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.cancel()
        mgr.reset()
        assert mgr.status == "cancelling"

    def test_cancel_route_keeps_the_run_panel_until_the_worker_stops(self, rm, client):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        r = client.post("/cancel")
        assert r.status_code == 200
        # Still unwinding: the standby panel would re-enable Run over a live
        # worker, so the response keeps the progress stream instead.
        assert "Choose a scenario and" not in r.text
        assert 'sse-connect="/progress' in r.text
        assert mgr.running
        gate["build"].set()
        assert mgr.join(5.0)
        assert _stream_until_terminal(client)[-1] == "done"

    def test_cancel_route_returns_standby_once_the_worker_stops(self, rm, client):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.cancel()
        gate["build"].set()  # the worker unwinds within /cancel's wait
        r = client.post("/cancel")
        assert "was cancelled. No results were produced" in r.text
        assert 'hx-post="/clear"' in r.text
        assert mgr.status == "cancelled"
        r = client.post("/clear")
        assert "Choose a scenario and" in r.text
        assert mgr.status == "idle"

    def test_cancelled_run_keeps_its_code_until_clear(self, rm, client):
        import threading

        import pyfds_evac.webapp.app as app_module
        from pyfds_evac.webapp.runner import make_run_spec

        mgr, _calls, gate = rm
        form = {"scenario": "ISO-table21", "seed": "5"}
        scenario, opts = app_module._resolve_form(form)
        spec = make_run_spec(opts, scenario, "ISO-table21", "ISO-table21")
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub", spec=spec)
        assert entered.wait(5.0)
        mgr.cancel()
        gate["build"].set()
        r = client.post("/cancel")
        run_id = mgr.spec.run_id
        assert f'data-pyexport-run="{run_id}"' in r.text
        code = client.post(f"/export/run?run={run_id}", data=form, headers=_HX)
        assert f"Configuration of the cancelled run #{run_id}" in code.text
        assert "Status: cancelled" in code.text
        # No result, so the seed used stays unrecorded.
        assert "the seed used was not recorded" in _code_of(code.text)
        client.post("/clear")
        stale = client.post(f"/export/run?run={run_id}", data=form, headers=_HX)
        assert "<code>" not in stale.text

    def test_progress_stream_ends_with_done_after_a_cancel(self, rm, client):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.cancel()
        gate["build"].set()
        assert mgr.join(5.0)
        # Every connected client needs a terminal event; a stream that just
        # closes is reopened by EventSource and never settles.
        with client.stream("GET", "/progress") as s:
            body = "".join(s.iter_text())
        assert "event: done" in body
        assert "was cancelled. No results were produced" in body
        assert 'hx-post="/clear"' in body

    def test_progress_stream_does_not_follow_a_later_run(self, rm):
        import asyncio
        import threading

        import pyfds_evac.webapp.app as app_module

        mgr, _calls, gate = rm
        first = threading.Event()
        mgr.start(None, self._blocking(gate, "build", first), "stub")
        assert first.wait(5.0)
        pinned = mgr.run_id

        async def drive():
            resp = await app_module.progress(run=pinned)
            events = resp.body_iterator
            assert "event: console" in await anext(events)
            # The first run ends and a second starts between two polls.
            gate["build"].set()
            assert mgr.join(5.0)
            mgr.reset()
            second = threading.Event()
            mgr.start(None, self._blocking(gate, "build", second), "stub")
            assert second.wait(5.0)
            seen = []
            while not seen or "event: done" not in seen[-1]:
                seen.append(await asyncio.wait_for(anext(events), 2.0))
            return seen

        seen = asyncio.run(drive())
        assert mgr.running  # the stream settled without the second run ending
        assert "event: progress" not in "".join(seen)

    @pytest.mark.parametrize("offset", [-1, 1])
    def test_stale_or_unknown_run_gets_only_the_final_event(self, rm, client, offset):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.log_lines.append("current-run-log")
        mgr.fed_snapshots.append((1.0, 0.25, 0.1))
        other = mgr.run_id + offset
        with client.stream("GET", f"/progress?run={other}") as s:
            body = "".join(s.iter_text())
        assert body.count("event:") == 1
        assert "event: done" in body
        assert "current-run-log" not in body
        with client.stream("GET", f"/fed-progress?run={other}") as s:
            body = "".join(s.iter_text())
        assert body.count("event:") == 1
        assert "event: close" in body

    def test_fed_stream_pinned_over_http_sends_its_run(self, rm, client):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.fed_snapshots.append((1.0, 0.25, 0.1))
        gate["build"].set()
        assert mgr.join(5.0)
        with client.stream("GET", f"/fed-progress?run={mgr.run_id}") as s:
            body = "".join(s.iter_text())
        assert "event: fed" in body
        assert "0.25" in body
        assert body.rstrip().endswith("data: {}")
        assert "event: close" in body

    def test_fed_stream_sends_the_last_points_of_a_run_that_ends(self, rm):
        import asyncio
        import threading

        import pyfds_evac.webapp.app as app_module

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        mgr.fed_snapshots.append((1.0, 0.25, 0.1))

        async def drive():
            resp = await app_module.fed_progress(run=mgr.run_id)
            events = resp.body_iterator
            assert "event: fed" in await anext(events)
            # The run records a last point and ends between two polls.
            mgr.fed_snapshots.append((2.0, 0.625, 0.3))
            gate["build"].set()
            assert mgr.join(5.0)
            seen = []
            while not seen or "event: close" not in seen[-1]:
                seen.append(await asyncio.wait_for(anext(events), 2.0))
            return seen

        seen = asyncio.run(drive())
        assert "event: fed" in seen[0]
        assert "0.625" in seen[0]
        assert "event: close" in seen[-1]

    def test_fed_stream_does_not_follow_a_later_run(self, rm):
        import asyncio
        import threading

        import pyfds_evac.webapp.app as app_module

        mgr, _calls, gate = rm
        first = threading.Event()
        mgr.start(None, self._blocking(gate, "build", first), "stub")
        assert first.wait(5.0)
        mgr.fed_snapshots.append((1.0, 0.25, 0.1))
        pinned = mgr.run_id

        async def drive():
            resp = await app_module.fed_progress(run=pinned)
            events = resp.body_iterator
            assert "event: fed" in await anext(events)
            # The first run ends and a second starts between two polls.
            gate["build"].set()
            assert mgr.join(5.0)
            mgr.reset()
            second = threading.Event()
            mgr.start(None, self._blocking(gate, "build", second), "stub")
            assert second.wait(5.0)
            mgr.fed_snapshots.append((2.0, 0.875, 0.5))
            seen = []
            while not seen or "event: close" not in seen[-1]:
                seen.append(await asyncio.wait_for(anext(events), 2.0))
            return seen

        seen = asyncio.run(drive())
        assert mgr.running
        assert "event: fed" not in "".join(seen)
        assert "0.875" not in "".join(seen)

    @staticmethod
    def _run_to(mgr, name, outcome):
        """Start ``name`` and leave it in ``outcome``: done, error or running."""
        import threading

        gate = threading.Event()

        def build():
            if outcome == "running":
                gate.wait(5.0)
            if outcome == "error":
                raise RuntimeError(f"{name} failed")
            return {}

        mgr.start(None, build, name)
        if outcome == "running":
            mgr.last_event = SimpleNamespace(
                evacuated=1, total=2, sim_time=1.0, wall_time=1.0, pct=50
            )
        else:
            assert mgr.join(5.0)
        mgr.log_lines.append(f"{name}-log")
        return gate

    @pytest.mark.parametrize("pin", [True, False])
    @pytest.mark.parametrize("outcome", ["done", "error", "running"])
    def test_progress_iteration_emits_one_run_only(self, rm, monkeypatch, outcome, pin):
        import asyncio

        import pyfds_evac.webapp.app as app_module

        mgr, _calls, gate = rm
        monkeypatch.setattr(
            app_module,
            "_finished_view",
            lambda: app_module.Div(f"results of {app_module.manager.scenario_name}"),
        )
        gate["a"] = self._run_to(mgr, "run-A", outcome)
        pinned = mgr.run_id if pin else None

        async def drive():
            resp = await app_module.progress(run=pinned)
            events = resp.body_iterator
            assert "run-A-log" in await anext(events)
            # Run A gives way to run B while the stream sits on the console
            # event; the rest of that iteration must still describe run A.
            gate["a"].set()
            assert mgr.join(5.0)
            mgr.reset()
            gate["b"] = self._run_to(mgr, "run-B", outcome)
            seen = []
            while not seen or "event: done" not in seen[-1]:
                seen.append(await asyncio.wait_for(anext(events), 2.0))
            return "".join(seen)

        body = asyncio.run(drive())
        assert "run-B" not in body
        expected = {
            "done": "results of run-A",
            "error": "RuntimeError: run-A failed",
            "running": "Running: run-A",
        }[outcome]
        assert expected in body

    @pytest.mark.parametrize("pin", [True, False])
    @pytest.mark.parametrize("outcome", ["done", "error", "running"])
    def test_fed_iteration_emits_one_run_only(self, rm, outcome, pin):
        import asyncio

        import pyfds_evac.webapp.app as app_module

        mgr, _calls, gate = rm
        gate["a"] = self._run_to(mgr, "run-A", outcome)
        mgr.fed_snapshots.append((1.0, 0.25, 0.1))
        pinned = mgr.run_id if pin else None

        async def drive():
            resp = await app_module.fed_progress(run=pinned)
            events = resp.body_iterator
            assert "0.25" in await anext(events)
            gate["a"].set()
            assert mgr.join(5.0)
            mgr.reset()
            gate["b"] = self._run_to(mgr, "run-B", outcome)
            mgr.fed_snapshots.append((2.0, 0.875, 0.5))
            seen = []
            while not seen or "event: close" not in seen[-1]:
                seen.append(await asyncio.wait_for(anext(events), 2.0))
            return "".join(seen)

        body = asyncio.run(drive())
        assert "0.875" not in body
        assert "event: fed" not in body

    def test_clear_keeps_the_run_panel_while_a_worker_is_active(self, rm, client):
        import threading

        mgr, _calls, gate = rm
        entered = threading.Event()
        mgr.start(None, self._blocking(gate, "build", entered), "stub")
        assert entered.wait(5.0)
        r = client.post("/clear")
        assert "Choose a scenario and" not in r.text
        assert 'sse-connect="/progress' in r.text
        assert mgr.running

    def test_terminal_status_is_published_after_the_lock_is_released(self, rm):
        mgr, _calls, _gate = rm
        seen = []
        real = mgr._lock

        class SpyLock:
            def acquire(self, *a, **k):
                return real.acquire(*a, **k)

            def release(self):
                seen.append(mgr.status)
                real.release()

        mgr._lock = SpyLock()
        mgr.start(None, dict, "stub")
        assert mgr.join(5.0)
        assert mgr.status == "done"
        # A client that sees ``done`` may start the next run at once.
        assert seen == ["running"]


class TestScenarioPath:
    """The picker value reaches load_scenario as a path, so it must be clamped.

    It arrives in a plain form field, not necessarily from the <select> we
    rendered, so a crafted value must not be able to walk out of assets/.
    """

    @staticmethod
    def _fn():
        from pyfds_evac.webapp.params import scenario_path

        return scenario_path

    def test_resolves_bundled_scenario(self):
        assert self._fn()("t_junction").name == "t_junction"

    def test_resolves_alternate_json(self):
        assert self._fn()("t_junction/config_full.json").name == "config_full.json"

    @pytest.mark.parametrize(
        "value",
        [
            "../etc",
            "t_junction/../../etc",
            "uploads/../assets",
            "/etc/passwd",
            "",
        ],
    )
    def test_rejects_traversal(self, value):
        with pytest.raises(ValueError):
            self._fn()(value)


class TestScenarioUpload:
    """Uploading a scenario's non-FDS files (config JSON + WKT, or a zip)."""

    WKT = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"

    @staticmethod
    def _config():
        import json
        from pathlib import Path

        return Path("assets/t_junction/config.json").read_text(), json

    @staticmethod
    def _uploads_root():
        from pyfds_evac.webapp.params import _UPLOAD_ROOT

        return _UPLOAD_ROOT

    def _post(self, client, files, name="pytest-upload"):
        return client.post("/upload-scenario", data={"upload_name": name}, files=files)

    def test_json_and_wkt_pair_becomes_selectable(self, client):
        cfg, _ = self._config()
        r = self._post(
            client,
            [
                ("files", ("config.json", cfg, "application/json")),
                ("files", ("geometry.wkt", self.WKT, "text/plain")),
            ],
        )
        assert r.status_code == 200
        assert "uploads/pytest-upload" in r.text
        assert "Uploaded" in r.text  # optgroup separating it from bundled
        created = self._uploads_root() / "pytest-upload"
        try:
            assert (created / "config.json").exists()
            assert (created / "geometry.wkt").exists()
            # And it is now a runnable choice.
            from pyfds_evac.webapp.params import _upload_options

            assert "uploads/pytest-upload" in [v for _, v in _upload_options()]
        finally:
            shutil.rmtree(created, ignore_errors=True)

    def test_zip_bundle_is_accepted(self, client):
        cfg, _ = self._config()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("config.json", cfg)
            zf.writestr("geometry.wkt", self.WKT)
        r = self._post(
            client,
            [("files", ("bundle.zip", buf.getvalue(), "application/zip"))],
            name="pytest-zip",
        )
        assert r.status_code == 200
        assert "uploads/pytest-zip" in r.text
        created = self._uploads_root() / "pytest-zip"
        try:
            assert (created / "config.json").exists()
        finally:
            shutil.rmtree(created, ignore_errors=True)

    def test_zip_slip_member_is_rejected_not_flattened(self, client):
        """A '../' member must not escape, and must not be kept at all.

        Flattening it to a basename would leave a stray .json inside the
        scenario dir, which the picker then offers as an alternate config.
        """
        cfg, _ = self._config()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("config.json", cfg)
            zf.writestr("geometry.wkt", self.WKT)
            zf.writestr("../../pwned.json", '{"evil": true}')
        escaped = self._uploads_root().parent / "pwned.json"
        r = self._post(
            client,
            [("files", ("evil.zip", buf.getvalue(), "application/zip"))],
            name="pytest-slip",
        )
        created = self._uploads_root() / "pytest-slip"
        try:
            assert r.status_code == 200
            assert not escaped.exists()  # nothing written outside uploads/
            assert not (created / "pwned.json").exists()  # nor kept inside
            assert sorted(p.name for p in created.iterdir()) == [
                "config.json",
                "geometry.wkt",
            ]
        finally:
            shutil.rmtree(created, ignore_errors=True)
            escaped.unlink(missing_ok=True)

    def test_zip_of_a_folder_is_flattened(self, client):
        """The common case: zipping the scenario folder, not its contents."""
        cfg, _ = self._config()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("t_junction/config.json", cfg)
            zf.writestr("t_junction/geometry.wkt", self.WKT)
            zf.writestr("t_junction/t_junction.fds", "&HEAD /")
        r = self._post(
            client,
            [("files", ("folder.zip", buf.getvalue(), "application/zip"))],
            name="pytest-folder",
        )
        created = self._uploads_root() / "pytest-folder"
        try:
            assert r.status_code == 200
            # Nested members keep their basename; the FDS deck is not a
            # scenario file and is left out.
            assert sorted(p.name for p in created.iterdir()) == [
                "config.json",
                "geometry.wkt",
            ]
        finally:
            shutil.rmtree(created, ignore_errors=True)

    def test_non_scenario_files_are_ignored_and_reported(self, client):
        cfg, _ = self._config()
        r = self._post(
            client,
            [
                ("files", ("config.json", cfg, "application/json")),
                ("files", ("geometry.wkt", self.WKT, "text/plain")),
                ("files", ("case.fds", "&HEAD /", "text/plain")),
            ],
            name="pytest-extra",
        )
        created = self._uploads_root() / "pytest-extra"
        try:
            assert r.status_code == 200
            assert "ignored" in r.text and "case.fds" in r.text
            assert not (created / "case.fds").exists()
        finally:
            shutil.rmtree(created, ignore_errors=True)

    def test_unusable_upload_errors_and_leaves_nothing_behind(self, client):
        r = self._post(
            client,
            [("files", ("notes.txt", "hello", "text/plain"))],
            name="pytest-junk",
        )
        assert r.status_code == 200
        assert "Nothing usable" in r.text
        assert not (self._uploads_root() / "pytest-junk").exists()

    def test_wkt_without_config_is_rejected_and_cleaned_up(self, client):
        r = self._post(
            client,
            [("files", ("geometry.wkt", self.WKT, "text/plain"))],
            name="pytest-nocfg",
        )
        assert r.status_code == 200
        assert "Could not load that scenario" in r.text
        assert not (self._uploads_root() / "pytest-nocfg").exists()

    def test_empty_submission_is_rejected(self, client):
        r = client.post("/upload-scenario", data={"upload_name": "x"})
        assert r.status_code == 200
        assert "Pick a config JSON" in r.text

    def test_failed_upload_keeps_the_current_scenario_selected(self, client):
        """A rejected upload must not silently reset the picker."""
        r = client.post(
            "/upload-scenario",
            data={"upload_name": "x", "scenario": "t_junction/config_full.json"},
            files=[("files", ("notes.txt", "hello", "text/plain"))],
        )
        assert r.status_code == 200
        assert "Nothing usable" in r.text
        # The still-selected option carries the selected attribute.
        marker = 'value="t_junction/config_full.json" selected'
        assert (
            marker in r.text or 'selected value="t_junction/config_full.json"' in r.text
        )

    def test_uploaded_scenario_can_actually_be_run(self, client, tmp_path):
        """The whole point: an upload has to be runnable, not just listed."""
        cfg = pathlib.Path("assets/ISO-table21/config.json").read_text()
        wkt = pathlib.Path("assets/ISO-table21/geometry.wkt").read_text()
        r = self._post(
            client,
            [
                ("files", ("config.json", cfg, "application/json")),
                ("files", ("geometry.wkt", wkt, "text/plain")),
            ],
            name="pytest-runnable",
        )
        assert r.status_code == 200
        created = self._uploads_root() / "pytest-runnable"
        try:
            out = tmp_path / "out"
            r = client.post(
                "/run",
                data={
                    "scenario": "uploads/pytest-runnable",
                    "seed": "420",
                    "results_only": "1",
                    "output_base": str(out),
                },
            )
            assert r.status_code == 200
            assert "sse-connect" in r.text or "sse_connect" in r.text
            events = _stream_until_terminal(client)
            assert events[-1] == "done"
            assert manager.status == "done"
            assert manager.result.total_agents >= 1
            assert (out / "uploads_pytest-runnable.sqlite").exists()
            _drop_temp_trajectory()
        finally:
            shutil.rmtree(created, ignore_errors=True)


def test_results_only_run_skips_viewer_but_writes_files(client, tmp_path):
    """The results-only button runs the sim and reports files, with no viewer."""
    out = tmp_path / "out"
    r = client.post(
        "/run",
        data={
            "scenario": "ISO-table21",
            "seed": "420",
            "results_only": "1",
            "output_base": str(out),
        },
    )
    assert r.status_code == 200
    events = _stream_until_terminal(client)
    assert events[-1] == "done"
    assert manager.results_only is True

    from fasthtml.common import to_xml

    from pyfds_evac.webapp.app import _results_only_view

    html = to_xml(_results_only_view())
    assert "Output files" in html
    assert "Viewer skipped" in html
    assert "<canvas" not in html  # the trajectory animator was never built
    assert "Trajectory SQLite" in html

    # The artifacts really landed, and the bundle path is a directory now that
    # export_app_bundle is a path field rather than a checkbox.
    assert (out / "ISO-table21.sqlite").exists()
    assert (out / "bundle" / "config.json").exists()
    assert (out / "bundle" / "geometry.wkt").exists()
    _drop_temp_trajectory()


def test_normal_run_still_builds_the_viewer(client):
    """The default button path is unchanged: results_only stays off."""
    r = client.post("/run", data={"scenario": "ISO-table21", "seed": "420"})
    assert r.status_code == 200
    assert manager.results_only is False
    _stream_until_terminal(client)
    _drop_temp_trajectory()


def test_upload_sits_inside_core_beside_the_picker(client):
    """One place to choose what runs, not two competing sections.

    The upload is a way of adding to the scenario picker, so it renders inside
    Core just after it. It cannot be its own <form> there (HTML forbids nested
    forms), so it posts via htmx off the button instead.
    """
    r = client.get("/")
    assert r.status_code == 200
    body = r.text

    # It is inside the Core block, after the scenario field. Match the markup
    # rather than a bare class name, which also appears in the stylesheet.
    core = body.index(">Core<")
    picker = body.index('id="scenario-block"')
    upload = body.index("id='upload-drop'")
    assert core < picker < upload

    # And no longer a separate collapsible section of its own.
    assert "Upload your own scenario" not in body
    assert "<form id='upload-form'" not in body

    # Posted by htmx off the button, with multipart encoding.
    assert "hx-encoding='multipart/form-data'" in body
    assert "hx-post='/upload-scenario'" in body
    # The staged file must not ride along on the urlencoded run request.
    assert "not files,upload_name" in body


class TestOutputBase:
    """The "Output folder" box used to be wired to nothing at either end.

    Nothing filled it and nothing read it, so a path typed there was silently
    discarded and the run went to the derived path regardless.
    """

    @staticmethod
    def _opts(**extra):
        from pyfds_evac.webapp.params import form_to_opts

        form = {"scenario": "t_junction", "seed": "42"}
        form.update(extra)
        return form_to_opts(form)

    def test_blank_uses_the_derived_folder(self, results_root):
        from pyfds_evac.webapp.params import form_to_opts

        opts = form_to_opts(
            {"scenario": "t_junction", "seed": "42"}, stamp="20260929T120000Z"
        )
        assert opts.output_sqlite == (
            f"{results_root.as_posix()}/t_junction/deterministic/seed42/"
            "20260929T120000Z/t_junction.sqlite"
        )

    def test_blank_seed_folder_is_named_by_the_scenario_seed(self, results_root):
        # #319: "seeddefault" hid the seed the run actually used.
        from pyfds_evac.webapp.params import form_to_opts

        opts = form_to_opts({"scenario": "t_junction"}, baseseed=1301, stamp="S")
        assert opts.seed is None
        assert opts.output_sqlite == (
            f"{results_root.as_posix()}/t_junction/deterministic/seed1301/S/"
            "t_junction.sqlite"
        )

    def test_existing_folder_gets_a_suffix(self, results_root):
        from pyfds_evac.webapp.params import form_to_opts

        form = {"scenario": "t_junction", "seed": "7"}
        first = pathlib.Path(form_to_opts(form, stamp="S").output_sqlite).parent
        first.mkdir(parents=True)
        second = pathlib.Path(form_to_opts(form, stamp="S").output_sqlite).parent
        assert second == first.with_name("S-2")

    def test_typed_folder_is_honoured(self):
        opts = self._opts(output_base="D:/scratch/my run")
        assert opts.output_sqlite == "D:/scratch/my run/t_junction.sqlite"
        assert opts.output_fed_history == "D:/scratch/my run/t_junction_fed_history.csv"
        assert opts.export_app_bundle == "D:/scratch/my run/bundle"

    def test_typed_folder_is_normalised(self):
        # Backslashes and a trailing separator must not double up in the path.
        opts = self._opts(output_base="out\\runs\\")
        assert opts.output_sqlite == "out/runs/t_junction.sqlite"

    def test_whitespace_only_falls_back_to_derived(self, results_root):
        opts = self._opts(output_base="   ")
        assert opts.output_sqlite.startswith(f"{results_root.as_posix()}/t_junction/")

    def test_posted_output_paths_are_ignored(self):
        # #330: the paths come from the scenario and the folder, never from a
        # posted output_* value, which could belong to a previous scenario.
        opts = self._opts(
            output_base="out",
            output_sqlite="results/Haspel/deterministic/seeddefault/Haspel.sqlite",
            export_app_bundle="elsewhere/bundle",
        )
        assert opts.output_sqlite == "out/t_junction.sqlite"
        assert opts.export_app_bundle == "out/bundle"

    def test_new_scenario_with_stale_paths_uses_the_derived_folder(self):
        # #330 repro: Haspel's paths posted with a new scenario and seed.
        from pyfds_evac.webapp.params import form_to_opts

        stale = "results/Haspel/deterministic/seeddefault/Haspel"
        opts = form_to_opts(
            {
                "scenario": "blind_spawn_discovery",
                "seed": "11",
                "output_sqlite": f"{stale}.sqlite",
                "output_smoke_history": f"{stale}_smoke_history.csv",
                "output_fed_history": f"{stale}_fed_history.csv",
                "output_route_history": f"{stale}_route_history.csv",
                "output_route_cost_history": f"{stale}_route_cost_history.csv",
                "export_app_bundle": "results/Haspel/deterministic/seeddefault/bundle",
            }
        )
        paths = [
            opts.output_sqlite,
            opts.output_smoke_history,
            opts.output_fed_history,
            opts.output_route_history,
            opts.output_route_cost_history,
            opts.export_app_bundle,
        ]
        assert all("Haspel" not in p for p in paths)
        assert "/blind_spawn_discovery/deterministic/seed11/" in opts.output_sqlite

    def test_form_has_no_hidden_output_paths(self, client):
        html = client.get("/").text
        for key in ("output_sqlite", "output_fed_history", "export_app_bundle"):
            assert f'name="{key}"' not in html


def test_artifact_preview_lines_are_rewritable(client):
    """The sidebar preview must carry the data the script needs to fill it in.

    Without data-suffix the list is stuck showing a literal "<run>".
    """
    from pyfds_evac.webapp.params import ARTIFACT_SUFFIXES

    r = client.get("/")
    assert r.status_code == 200
    for suffix in ARTIFACT_SUFFIXES:
        assert f'data-suffix="{suffix}"' in r.text
    assert "artifact-preview" in r.text
    assert "outputBase()" in r.text  # the script reads the folder box


def test_run_name_matches_the_client_side_clean():
    from pyfds_evac.webapp.params import default_output_base, run_name

    assert run_name("t_junction") == "t_junction"
    assert run_name("t_junction/config_full.json") == "t_junction_config_full"
    assert run_name("uploads/mine") == "uploads_mine"
    assert run_name(None) == "run"
    assert default_output_base("t_junction", "deterministic", 7, "S").endswith(
        "/results/t_junction/deterministic/seed7/S"
    )
    assert default_output_base("t_junction", None, None, "S").endswith(
        "/deterministic/seeddefault/S"
    )


def test_results_root_defaults_to_the_repository(monkeypatch):
    from pyfds_evac.webapp.params import RESULTS_ENV, results_root

    monkeypatch.delenv(RESULTS_ENV)
    assert results_root() == pathlib.Path(__file__).resolve().parents[1] / "results"


def test_runs_get_distinct_folders_named_by_start_time(client, results_root):
    """#319: two runs with the same settings must not share a folder."""
    from pyfds_evac.webapp.runner import run_stamp

    folders = []
    for _ in range(2):
        r = client.post("/run", data={"scenario": "ISO-table21", "seed": "420"})
        assert r.status_code == 200
        assert _stream_until_terminal(client)[-1] == "done"
        sqlite = pathlib.Path(manager.opts.output_sqlite)
        assert sqlite.is_file()
        assert sqlite.parent.name.startswith(run_stamp(manager.spec.started_at))
        assert (
            sqlite.parent.parent == results_root / "ISO-table21/deterministic/seed420"
        )
        folders.append(sqlite.parent)
    assert folders[0] != folders[1]
    client.post("/clear")


def test_temp_trajectory_is_removed_when_the_result_is_dropped(client):
    """#319: the temp sqlite and manifest used to leak on every GUI run."""
    paths = []
    for _ in range(2):
        client.post("/run", data={"scenario": "ISO-table21", "seed": "420"})
        assert _stream_until_terminal(client)[-1] == "done"
        tmp = pathlib.Path(manager.result.sqlite_file)
        manifest = pathlib.Path(manager.result.manifest_file)
        assert tmp.is_file() and manifest.is_file()
        # The copy in the output folder is the user's and is kept.
        assert pathlib.Path(manager.opts.output_sqlite).is_file()
        paths.append((tmp, manifest))
    # Starting the second run dropped the first one's temp files.
    assert not paths[0][0].exists() and not paths[0][1].exists()
    client.post("/clear")
    assert not paths[1][0].exists() and not paths[1][1].exists()


def test_export_app_bundle_is_a_path_not_a_checkbox(results_root):
    """Regression: the checkbox posted 'on', so bundles landed in ./on/.

    --export-app-bundle takes a directory. The sidebar used to render it as a
    switch, and the posted "on" was passed straight through as the path.
    """
    from pyfds_evac.webapp.params import form_to_opts

    opts = form_to_opts(
        {"scenario": "t_junction", "seed": "42", "export_app_bundle": "on"}
    )
    assert opts.export_app_bundle != "on"
    assert opts.export_app_bundle.endswith("/bundle")
    assert opts.export_app_bundle.startswith(f"{results_root.as_posix()}/t_junction/")


def test_form_rejects_value_outside_choices():
    """A typo in a flag with argparse choices fails when the form is read.

    form_to_opts skips argparse, so without this check "Clothed" reached the
    heat model and failed only once the run had started.
    """
    import pytest

    from pyfds_evac.webapp.params import form_to_opts

    form = {"scenario": "t_junction", "seed": "42", "heat_clothing": "Clothed"}
    with pytest.raises(ValueError, match="heat_clothing"):
        form_to_opts(form)
    form["heat_clothing"] = "unclothed"
    assert form_to_opts(form).heat_clothing == "unclothed"


class TestTrajectorySampling:
    """Playback fidelity must not decay as a run gets longer.

    The viewer draws a straight line between consecutive samples, so the
    wall-clock gap between them is how far an agent travels along a chord
    that ignores geometry.  A fixed sample *count* makes that gap grow with
    run length: at the old 120-sample cap a 600 s run sampled every 5 s, so
    agents were drawn straight through walls and whole cohorts vanished
    between frames.
    """

    @staticmethod
    def _step(n_frames: int, fps: float = 10.0) -> int:
        import math

        from pyfds_evac.webapp.trajviz import _MAX_SAMPLES, _SAMPLE_INTERVAL_S

        step = max(1, round(_SAMPLE_INTERVAL_S * fps))
        if n_frames // step > _MAX_SAMPLES:
            step = math.ceil(n_frames / _MAX_SAMPLES)
        return step

    @pytest.mark.parametrize("duration_s", [60, 300, 600])
    def test_the_gap_stays_put_as_runs_grow(self, duration_s):
        from pyfds_evac.webapp.trajviz import _SAMPLE_INTERVAL_S

        fps = 10.0
        gap = self._step(int(duration_s * fps) + 1, fps) / fps
        assert gap == pytest.approx(_SAMPLE_INTERVAL_S)

    def test_an_agent_moves_less_than_a_wall_between_samples(self):
        """At a 1.3 m/s desired speed this is 13 cm, far narrower than any
        wall in the shipped decks, so the chord between two samples cannot
        visibly cut through one.
        """
        fps = 10.0
        gap = self._step(6001, fps) / fps
        assert gap * 1.3 < 1.0

    def test_a_very_long_run_degrades_instead_of_growing_without_bound(self):
        from pyfds_evac.webapp.trajviz import _MAX_SAMPLES

        fps = 10.0
        n_frames = int(3600 * fps) + 1
        step = self._step(n_frames, fps)
        assert n_frames // step <= _MAX_SAMPLES
        # Still far finer than the 30 s the old fixed cap would have given.
        assert step / fps <= 1.0


class TestAgentRadius:
    """Agents are drawn at their real body size so they scale with the map.

    That needs the radius the solver used.  ``ScenarioResult`` does not carry
    it and the JuPedSim sqlite stores no per-agent geometry, so the viewer
    reads it back off the scenario -- and a scenario that has been round
    tripped through the webapp can hand back parameters as a JSON string.
    """

    @staticmethod
    def _scenario(raw):
        return SimpleNamespace(raw=raw)

    def test_the_configured_radius_wins(self):
        from pyfds_evac.webapp.trajviz import _agent_radius_m

        scenario = self._scenario(
            {"distributions": {"d1": {"parameters": {"radius": 0.25}}}}
        )
        assert _agent_radius_m(scenario) == pytest.approx(0.25)

    def test_parameters_stored_as_json_are_read(self):
        from pyfds_evac.webapp.trajviz import _agent_radius_m

        scenario = self._scenario(
            {"distributions": {"d1": {"parameters": '{"radius": 0.3}'}}}
        )
        assert _agent_radius_m(scenario) == pytest.approx(0.3)

    def test_a_mixed_crowd_draws_at_its_mean(self):
        from pyfds_evac.webapp.trajviz import _agent_radius_m

        scenario = self._scenario(
            {
                "distributions": {
                    "a": {"parameters": {"radius": 0.2}},
                    "b": {"parameters": {"radius": 0.4}},
                }
            }
        )
        assert _agent_radius_m(scenario) == pytest.approx(0.3)

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            {},
            {"distributions": {}},
            {"distributions": {"a": {"parameters": "not json"}}},
            {"distributions": {"a": {"parameters": {"radius": "wide"}}}},
            {"distributions": {"a": {"parameters": {}}}},
            {"distributions": {"a": {"parameters": {"radius": 0}}}},
            {"distributions": [1, 2]},
        ],
    )
    def test_a_missing_or_junk_radius_falls_back(self, raw):
        """Never zero: a zero radius would collapse every agent to the
        visibility floor and silently stop the drawing scaling at all.
        """
        from pyfds_evac.webapp.trajviz import (
            _DEFAULT_AGENT_RADIUS_M,
            _agent_radius_m,
        )

        scenario = None if raw is None else self._scenario(raw)
        assert _agent_radius_m(scenario) == pytest.approx(_DEFAULT_AGENT_RADIUS_M)


def test_incapacitation_toggle_defaults_to_deterministic(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'class="mode-btn active" id="btn-det"' in r.text
    assert 'class="mode-btn" id="btn-prob"' in r.text
    tag = re.search(r'<input[^>]*name="incapacitation_mode"[^>]*>', r.text)
    assert tag and 'value="deterministic"' in tag.group(0)


def _choice_actions():
    from pyfds_evac.webapp.params import _HIDDEN, _load_parser

    return [
        a
        for a in _load_parser()._actions
        if a.choices is not None
        and a.option_strings
        and a.dest not in _HIDDEN
        # A segmented toggle, not a dropdown; see the test above.
        and a.dest != "incapacitation_mode"
    ]


def test_every_choice_flag_is_offered_in_the_form():
    assert {a.dest for a in _choice_actions()} >= {
        "heat_clothing",
        "heat_endpoint",
        "heat_fed_method",
        "heat_radiant_source",
        "heat_regime",
        "heat_incapacitation_mode",
    }


@pytest.mark.parametrize("action", _choice_actions(), ids=lambda a: a.dest)
def test_choice_flag_renders_as_select_of_argparse_choices(client, action):
    """Flags with argparse choices are dropdowns fed by those choices.

    The argparse default is preselected; a blank option, standing for the
    CLI default, appears only when that default is None.
    """
    html = client.get("/").text
    select = re.search(
        rf'<select[^>]*name="{action.dest}"[^>]*>(.*?)</select>', html, re.S
    )
    assert select, f"no <select> for {action.dest}"
    tag = select.group(0)
    assert f'id="{action.dest}"' in tag
    assert re.search(rf'<label[^>]*for="{action.dest}"', html)
    options = re.findall(r"<option([^>]*)>", select.group(1))
    values = [re.search(r'value="([^"]*)"', o).group(1) for o in options]
    blank = [""] if action.default is None else []
    assert values == blank + [str(c) for c in action.choices]
    selected = [v for v, o in zip(values, options) if "selected" in o]
    expected = "" if action.default is None else str(action.default)
    assert selected == [expected]


def test_non_choice_flag_still_renders_as_input(client):
    html = client.get("/").text
    assert not re.search(r'<select[^>]*name="fed_threshold"', html)
    tag = re.search(r'<input[^>]*name="fed_threshold"[^>]*>', html)
    assert tag and 'type="number"' in tag.group(0)
    assert 'value="1.0"' in tag.group(0)


# Output paths and the route-cost switch the GUI fixes on purpose (#319).
_GUI_FIXED = {
    "output_sqlite",
    "output_smoke_history",
    "output_fed_history",
    "output_route_history",
    "output_route_cost_history",
    "export_app_bundle",
    "collect_route_cost_history",
}


@pytest.mark.parametrize("scenario", ["t_junction", "blind_spawn_discovery"])
def test_empty_form_resolves_to_the_cli_defaults(scenario):
    """#317: a form that sets nothing must resolve like run.py --scenario x."""
    import run as cli
    from pyfds_evac.webapp.params import form_to_opts

    gui = vars(form_to_opts({"scenario": scenario}))
    api = vars(cli._build_parser().parse_args(["--scenario", scenario]))
    assert set(gui) - _GUI_FIXED == set(api) - _GUI_FIXED
    for key in set(api) - _GUI_FIXED:
        assert gui[key] == api[key], key


def test_rendered_form_does_not_preset_seed_or_vis_cache(client):
    """#317: no seed 42 over the scenario's baseSeed, no vis_cache autofill."""
    html = client.get("/").text
    seed = re.search(r"<input[^>]*id=\"seed\"[^>]*>", html).group(0)
    assert "value=" not in seed
    assert "fillVisCache" not in html


def test_switch_sentinel_distinguishes_unchecked_from_absent(client):
    from pyfds_evac.webapp.params import form_to_opts

    html = client.get("/").text
    assert '<input type="hidden" name="enable_rerouting" value="off">' in html
    base = {"scenario": "t_junction"}
    assert form_to_opts(base).enable_rerouting is True
    assert form_to_opts({**base, "enable_rerouting": "off"}).enable_rerouting is False
    assert form_to_opts({**base, "enable_rerouting": "on"}).enable_rerouting is True


class TestRunSpec:
    """#318: each submitted run keeps an immutable record of its settings."""

    def test_snapshot_survives_later_edits_and_records_the_seed(self, client):
        r = client.post("/run", data={"scenario": "blind_spawn_discovery"})
        assert r.status_code == 200
        spec = manager.spec
        assert spec is not None and spec.run_id == manager.run_id
        # Neither the live Namespace nor a later form can reach the snapshot.
        manager.opts.seed = 999
        with pytest.raises(TypeError):
            spec.opts["seed"] = 999
        client.post("/run", data={"scenario": "t_junction", "seed": "5"})
        assert _stream_until_terminal(client)[-1] == "done"
        done = manager.spec
        assert done.opts["seed"] is None  # blank form: the scenario's seed
        assert done.expected_seed == 1301  # baseSeed of the deck
        assert done.seed_used == 1301  # confirmed by result.metrics
        assert done.status == "done"
        assert done.total_agents == manager.result.total_agents
        assert done.scenario_path.endswith("blind_spawn_discovery")
        _drop_temp_trajectory()

    def test_reset_drops_the_snapshot(self, client):
        client.post("/run", data={"scenario": "ISO-table21", "seed": "3"})
        _stream_until_terminal(client)
        _drop_temp_trajectory()
        client.post("/clear")
        assert manager.spec is None


# ── Show equivalent Python ────────────────────────────────────────────────────
_HX = {"HX-Request": "true"}


def _code_of(html_text):
    import html

    match = re.search(r"<code>(.*?)</code>", html_text, re.S)
    assert match, html_text[:2000]
    return html.unescape(match.group(1))


def _script_literals(code):
    """PATHS and OPTIONS of a generated script, read without running it."""
    import ast

    tree = ast.parse(code)
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", None)
        if name in ("SCENARIO", "FDS_DIR", "VIS_CACHE", "OPTIONS"):
            found[name] = ast.literal_eval(node.value)
    return found


def _preview(client, **form):
    r = client.post("/export/preview", data=form, headers=_HX)
    assert r.status_code == 200
    return r.text


class TestEquivalentPython:
    def test_preview_is_valid_python_and_round_trips(self, client, tmp_path):
        import ast
        from pathlib import Path

        from pyfds_evac.webapp.app import _resolve_form
        from pyfds_evac.webapp.pyexport import OMITTED_OUTPUT_KEYS

        form = {
            "scenario": "t_junction",
            "seed": "7",
            "fds_dir": str(tmp_path),
            "constant_extinction": "0.3",
            "incapacitation_mode": "probabilistic",
            "enable_heat_fed": "on",
            "heat_clothing": "unclothed",
            "vis_cache": "cache/vis.npz",
        }
        code = _code_of(_preview(client, **form))
        ast.parse(code)
        lit = _script_literals(code)
        _scenario, opts = _resolve_form(dict(form))
        expected = vars(opts)
        rebuilt = dict(lit["OPTIONS"])
        rebuilt.update(fds_dir=lit["FDS_DIR"], vis_cache=lit["VIS_CACHE"])
        assert set(rebuilt) | {"scenario"} == set(expected)
        for key, value in rebuilt.items():
            if key in OMITTED_OUTPUT_KEYS:
                assert value is None, key
            elif key in ("fds_dir", "vis_cache"):
                assert value == str(Path(expected[key]).resolve()), key
            else:
                assert value == expected[key], key
        assert Path(lit["SCENARIO"]).parts[-2:] == ("assets", "t_junction")
        assert "Preview of form settings, not a run." in code

    def test_switch_posted_as_the_browser_posts_it(self, client):
        """A checked switch posts its "off" sentinel and then "on"."""
        on = _code_of(
            _preview(client, scenario="t_junction", enable_rerouting=["off", "on"])
        )
        off = _code_of(_preview(client, scenario="t_junction", enable_rerouting="off"))
        assert "'enable_rerouting': True," in on
        assert "'enable_rerouting': False," in off

    def test_preview_leaves_the_seed_to_the_scenario(self, client):
        code = _code_of(_preview(client, scenario="blind_spawn_discovery"))
        assert "'seed': None,  # None = the scenario's baseSeed (1301)" in code
        assert "42" not in code.split("OPTIONS = {")[1].split("\n")[1]

    def test_invalid_form_gives_the_api_message_and_no_code(self, client):
        text = _preview(
            client,
            scenario="t_junction",
            vis_cache="x.npz",
            enable_rerouting="off",
        )
        assert "<code>" not in text
        assert "--vis-cache requires --enable-rerouting" in text
        assert "Fix the settings to generate code" in text
        assert text.count("disabled") >= 2

    def test_hostile_text_stays_inside_string_literals(self, client, tmp_path):
        import ast
        import sys

        hostile = "x'\"\nimport os; os.system('echo pwned')  #  \r\\"
        # NTFS forbids quotes and newlines in names; keep the path plain there.
        name = "plain" if sys.platform == "win32" else hostile.replace("/", "_")
        fds_dir = tmp_path / name
        fds_dir.mkdir()
        clean = ast.parse(_code_of(_preview(client, scenario="t_junction")))
        code = _code_of(
            _preview(
                client,
                scenario="t_junction",
                fds_dir=str(fds_dir),
                vis_cache=hostile,
                output_base=hostile,
            )
        )
        tree = ast.parse(code)
        shape = [type(n).__name__ for n in tree.body]
        assert shape == [type(n).__name__ for n in clean.body]
        constants = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)}
        assert str(fds_dir.resolve()) in constants
        # No hostile call reached code: the only calls are the script's own.
        names = {
            n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        assert "system" not in names

    def test_hostile_scenario_name_cannot_leave_the_comment(self):
        import ast
        import dataclasses

        from pyfds_evac.webapp.params import form_to_opts
        from pyfds_evac.webapp.pyexport import run_script
        from pyfds_evac.webapp.runner import RunSpec

        spec = RunSpec(
            run_id=3,
            scenario_name="uploads/a\nimport os os.system('pwned')\r",
            scenario_path="/tmp/a'\nb",
            opts=vars(form_to_opts({"scenario": "t_junction"})),
            started_at="2026-01-01T00:00:00+00:00",
            pyfds_evac_version="0.1.0\nimport os",
            git_commit=None,
            git_dirty=None,
            expected_seed=None,
        )
        code = run_script(spec).code
        tree = ast.parse(code)
        assert not any(
            isinstance(n, ast.Import) and n.names[0].name == "os" for n in tree.body
        )
        assert "# seed not recorded for this run" in code
        assert "42" not in code.split("'seed':")[1].split("\n")[0]
        done = dataclasses.replace(spec, seed_used=77, status="done")
        assert "'seed': 77,  # seed used by run #3" in run_script(done).code

    def test_run_button_only_after_a_run_and_gone_after_clear(self, client):
        from fasthtml.common import to_xml

        from pyfds_evac.webapp.app import _clear_run_bar

        assert 'data-pyexport-run="' not in client.get("/").text
        assert "Show equivalent Python" in client.get("/").text
        client.post("/run", data={"scenario": "ISO-table21", "seed": "11"})
        _stream_until_terminal(client)
        run_id = manager.spec.run_id
        assert f'data-pyexport-run="{run_id}"' in to_xml(_clear_run_bar())
        r = client.post(
            f"/export/run?run={run_id}",
            data={"scenario": "ISO-table21", "seed": "11"},
            headers=_HX,
        )
        code = _code_of(r.text)
        assert f"# Run #{run_id}, started" in code
        assert f"'seed': 11,  # seed used by run #{run_id}" in code
        assert "Status: Complete: all agents evacuated (1/1)" in r.text
        assert "The form has changed" not in r.text
        changed = client.post(
            f"/export/run?run={run_id}",
            data={"scenario": "ISO-table21", "seed": "12"},
            headers=_HX,
        )
        assert "The form has changed since this run" in changed.text
        assert "'seed': 11," in _code_of(changed.text)  # still the snapshot
        # The script sets the GUI's output files to None, so output paths
        # alone (a new folder, or a stale posted output_sqlite, #330) are
        # not a change to the code.
        moved = client.post(
            f"/export/run?run={run_id}",
            data={
                "scenario": "ISO-table21",
                "seed": "11",
                "output_base": "elsewhere/run",
                "output_sqlite": "results/Haspel/stale.sqlite",
            },
            headers=_HX,
        )
        assert "The form has changed" not in moved.text
        _drop_temp_trajectory()
        client.post("/clear")
        stale = client.post(f"/export/run?run={run_id}", data={}, headers=_HX)
        assert "<code>" not in stale.text
        assert 'data-pyexport-run="' not in to_xml(_clear_run_bar())


_GUI_DRIVER = r"""
import json, pathlib, sys
from starlette.testclient import TestClient
from pyfds_evac.webapp.app import app, manager
from pyfds_evac.webapp.pyexport import run_script

client = TestClient(app)
client.post("/run", data={"scenario": sys.argv[1]})
with client.stream("GET", "/progress") as s:
    for line in s.iter_lines():
        if line.startswith("event:") and line.split(":", 1)[1].strip() in ("done", "error"):
            break
assert manager.status == "done", manager.error
pathlib.Path(sys.argv[2]).write_text(run_script(manager.spec).code)
m = manager.result.metrics
print("METRICS" + json.dumps({k: m[k] for k in sys.argv[3].split(",")}))
manager.result.cleanup()
"""

_SCRIPT_DRIVER = r"""
import json, runpy, sys
g = runpy.run_path(sys.argv[1])
m = g["result"].metrics
print("METRICS" + json.dumps({k: m[k] for k in sys.argv[2].split(",")}))
"""


def _metrics(stdout):
    import json

    line = next(ln for ln in stdout.splitlines() if ln.startswith("METRICS"))
    return json.loads(line[len("METRICS") :])


def test_exported_script_reproduces_the_gui_run(tmp_path):
    """The run's exported script, run alone, matches the GUI run exactly.

    Each side runs in a fresh interpreter, so both are the first run in their
    process and #198 (process-wide agent ids) cannot tell them apart. The deck
    has discovery agents, so its baseSeed (1301), rerouting and the clear-air
    visibility model all reach the result.
    """
    import subprocess
    import sys

    repo = pathlib.Path(__file__).resolve().parents[1]
    keys = "total_agents,agents_evacuated,agents_remaining,evacuation_time,seed"
    script = tmp_path / "exported.py"
    gui = subprocess.run(
        [sys.executable, "-c", _GUI_DRIVER, "blind_spawn_discovery", str(script), keys],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert gui.returncode == 0, gui.stderr[-3000:]
    exported = subprocess.run(
        [sys.executable, "-c", _SCRIPT_DRIVER, str(script), keys],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert exported.returncode == 0, exported.stderr[-3000:]
    gui_metrics, script_metrics = _metrics(gui.stdout), _metrics(exported.stdout)
    assert gui_metrics["seed"] == 1301
    assert gui_metrics["total_agents"] == 30
    assert script_metrics == gui_metrics
    (output,) = tmp_path.glob("pyfds_evac_blind_spawn_discovery_run1_*Z_output")
    assert (output / "trajectory.sqlite").is_file()


class TestRunOutcome:
    """#321: the outcome comes from all_evacuated, never from success."""

    def test_complete(self):
        from pyfds_evac.webapp.runner import run_outcome

        o = run_outcome(True, 0, 150, 212.4, 300.0)
        assert o.complete is True
        assert o.label == "Complete: all agents evacuated"
        assert o.time_label == "Evacuation time"

    def test_time_limit(self):
        from pyfds_evac.webapp.runner import run_outcome

        o = run_outcome(False, 60, 150, 300.0, 300.0)
        assert o.complete is False
        assert o.label == "Incomplete: time limit reached (60 of 150 remaining)"
        assert o.time_label == "Simulated time (limit reached)"

    def test_no_cause_claimed_when_numbers_disagree(self):
        from pyfds_evac.webapp.runner import run_outcome

        o = run_outcome(False, 3, 10, 120.0, 300.0)
        assert o.label == "Incomplete (3 of 10 remaining)"
        assert "limit" not in o.time_label

    def test_not_reported(self):
        from pyfds_evac.webapp.runner import run_outcome

        o = run_outcome(None, 0, 10, 10.0, 300.0)
        assert o.complete is None
        assert o.label == "Outcome not reported"

    def test_tiles_never_show_success(self, monkeypatch):
        """A timeout rendered as "stopped (True)"."""
        from fasthtml.common import to_xml

        from pyfds_evac.webapp.app import _kpi_tiles

        result = SimpleNamespace(
            metrics={"success": True, "all_evacuated": False},
            agents_remaining=100,
            agents_evacuated=0,
            total_agents=100,
            evacuation_time=1000.0,
        )
        monkeypatch.setattr(manager, "spec", None)
        monkeypatch.setattr(
            manager, "scenario", SimpleNamespace(max_simulation_time=1000.0)
        )
        html = to_xml(_kpi_tiles(result))
        assert "True" not in html
        assert "Incomplete: time limit reached (100 of 100 remaining)" in html
        assert "Simulated time (limit reached)" in html
        assert "Evacuation time" not in html
        assert "0 / 100 agents" in html

    def test_run_status_uses_the_snapshot(self):
        import dataclasses

        from pyfds_evac.webapp.pyexport import run_status
        from pyfds_evac.webapp.runner import RunSpec

        spec = RunSpec(
            run_id=1,
            scenario_name="t_junction",
            scenario_path="t",
            opts={},
            started_at="2026-09-29T12:00:00+00:00",
            pyfds_evac_version=None,
            git_commit=None,
            git_dirty=None,
            expected_seed=1,
            status="done",
            time_limit=300.0,
            all_evacuated=False,
            total_agents=150,
            agents_evacuated=90,
            agents_remaining=60,
            evacuation_time=300.0,
        )
        assert run_status(spec) == (
            "Incomplete: time limit reached (60 of 150 remaining), "
            "simulated time 300.00 s"
        )
        done = dataclasses.replace(
            spec,
            all_evacuated=True,
            agents_evacuated=150,
            agents_remaining=0,
            evacuation_time=212.4,
        )
        assert run_status(done) == (
            "Complete: all agents evacuated (150/150), evacuation time 212.40 s"
        )


class TestModelTab:
    """#323: the Model tab must state the engine's defaults, not contradict them."""

    @staticmethod
    def _html():
        from fasthtml.common import to_xml

        from pyfds_evac.webapp.docs import model_docs

        return to_xml(model_docs())

    @staticmethod
    def _section(html, title):
        start = html.index(title)
        end = html.find("Read more", start)
        return html[start:end]

    def test_opt_in_mechanisms_are_labelled_off(self):
        html = self._html()
        fic = self._section(html, "Irritant slowdown (FIC)")
        assert ">Off<" in fic and "--enable-fic-speed" in fic
        heat = self._section(html, "Heat dose")
        assert "Off; when on: clothed, deterministic" in heat
        assert "--enable-heat-fed" in heat
        assert "4.1 \\times 10^{8}" in heat  # ISO 13571 Eq. (9), clothed

    def test_incapacitation_is_deterministic_by_default(self):
        gas = self._section(self._html(), "Toxic gas: Fractional Effective Dose")
        assert "deterministic" in gas
        assert "same threshold, 1.0" in gas
        assert "In probabilistic mode" in gas

    def test_sampling_height_and_single_threshold(self):
        html = self._html()
        assert "1.6 m, as FDS+Evac (HUMAN_SMOKE_HEIGHT)" in html
        assert "One threshold for gas and heat" in html

    def test_defaults_match_the_cli(self):
        import run as cli

        defaults = vars(cli._build_parser().parse_args(["--scenario", "t_junction"]))
        assert defaults["enable_fic_speed"] is False
        assert defaults["enable_heat_fed"] is False
        assert defaults["incapacitation_mode"] == "deterministic"
        assert defaults["heat_incapacitation_mode"] == "deterministic"
        assert defaults["smoke_slice_height"] == 1.6
        assert defaults["fed_threshold"] == 1.0
        assert defaults["susceptibility_sigma"] == 0.94
        assert defaults["enable_rerouting"] is True
        assert defaults["reroute_interval"] == 1.0

    def test_unsourced_content_is_gone(self):
        html = self._html()
        for text in ("v2.4", "© 2024", "MMXXIV", "D = 0.3", "Tenability Tiers"):
            assert text not in html

    def test_links_to_the_models_pages(self):
        html = self._html()
        base = "https://pedestriandynamics.org/pyFDS-Evac/"
        for path in (
            "models/",
            "models/smoke-speed/",
            "models/fed/",
            "models/heat/#incapacitation",
            "models/routing/",
            "models/wayfinding/",
            "docs/fds-sampling/",
        ):
            assert f'href="{base}{path}"' in html


def test_warnings_card_links_the_case_requirements():
    from fasthtml.common import to_xml

    from pyfds_evac.webapp.app import _warnings_card

    html = to_xml(_warnings_card(["slice sampled at 2.0 m"]))
    assert "docs/fds-case-requirements.md" not in html
    assert "pyFDS-Evac/docs/fds-case-requirements/" in html
    assert "The run completed" not in html


class TestTerminalStates:
    """#320: a settled run is never discarded or hidden by accident."""

    @pytest.fixture
    def stub(self, monkeypatch):
        import pyfds_evac.webapp.app as app_module
        from pyfds_evac.webapp.runner import RunManager

        monkeypatch.setattr(
            "pyfds_evac.webapp.runner.run_scenario",
            lambda scenario, progress_callback=None, **kw: SimpleNamespace(
                sqlite_file=None
            ),
        )
        fresh = RunManager()
        monkeypatch.setattr(app_module, "manager", fresh)
        monkeypatch.setattr(
            app_module, "_finished_view", lambda: app_module.Div("results of stub")
        )
        yield fresh
        fresh.join(5.0)

    def test_cancel_after_the_run_finished_keeps_its_results(self, stub, client):
        stub.start(None, dict, "stub")
        assert stub.join(5.0)
        r = client.post("/cancel")
        assert stub.status == "done"
        assert "results of stub" in r.text
        assert "cancelled" not in r.text

    def test_done_event_replaces_the_whole_running_view(self, stub, client):
        import re as _re

        from fasthtml.common import to_xml

        import pyfds_evac.webapp.app as app_module

        view = to_xml(app_module._running_stream_view())
        connect = _re.search(r"<div[^>]*sse-connect[^>]*>", view).group(0)
        assert 'sse-swap="done"' in connect
        assert 'sse-swap="progress"' in view
        assert 'sse-swap="progress,done"' not in view
        assert "data-run-live" in view
        stub.start(None, dict, "stub")
        assert stub.join(5.0)
        with client.stream("GET", "/progress") as s:
            body = "".join(s.iter_text())
        done = body[body.index("event: done") :]
        assert "results of stub" in done
        assert "cancel-btn" not in done
        assert "data-run-live" not in done

    def test_failed_run_names_the_message_and_keeps_details_apart(self, stub):
        from fasthtml.common import to_xml

        import pyfds_evac.webapp.app as app_module

        def boom():
            raise RuntimeError("slice not found")

        stub.start(None, boom, "stub")
        assert stub.join(5.0)
        html = to_xml(app_module._terminal_view(stub.status))
        assert "Failed" in html
        assert "Run failed: </b>slice not found" in html
        assert "Technical details" in html
        assert "RuntimeError: slice not found" in html
        assert "hx-confirm" not in html  # nothing to lose

    def test_reload_shows_the_server_state(self, stub, client):
        import threading

        gate = threading.Event()
        stub.start(None, lambda: gate.wait(5.0) and {}, "stub")
        page = client.get("/").text
        assert 'data-run-live="1"' in page
        assert "Choose a scenario and" not in page
        gate.set()
        assert stub.join(5.0)
        page = client.get("/").text
        assert "results of stub" in page
        assert 'data-run-live="1"' not in page

    def test_rejected_submit_goes_to_the_alert_not_the_panel(self, client, tmp_path):
        r = client.post(
            "/run",
            data={
                "scenario": "ISO-table21",
                "vis_cache": "x.pkl",
                "fds_dir": str(tmp_path),
                "enable_rerouting": "off",
            },
            headers=_HX,
        )
        assert r.headers["HX-Retarget"] == "#form-status"
        assert r.headers["HX-Reswap"] == "innerHTML"
        assert "The run was not started." in r.text
        assert "Technical details" in r.text
        assert "enable-rerouting" in r.text
        r = client.post("/run", data={}, headers=_HX)
        assert r.headers["HX-Retarget"] == "#form-status"
        assert "Select a scenario first." in r.text

    def test_field_errors_name_the_field(self):
        from pyfds_evac.webapp.app import _field_label

        assert _field_label("heat_clothing: 'x' is not one of a, b") == (
            "Heat clothing: 'x' is not one of a, b"
        )
        assert _field_label("must be in [0.25, 1.0], got 2") == (
            "must be in [0.25, 1.0], got 2"
        )

    def test_settings_changed_banner_and_clear_confirmation(self, client):
        from fasthtml.common import to_xml

        from pyfds_evac.webapp.app import _clear_run_bar

        form = {"scenario": "ISO-table21", "seed": "11"}
        r = client.post("/run", data=form, headers=_HX)
        assert 'hx-swap-oob="true"' in r.text  # old alerts are cleared
        _stream_until_terminal(client)
        run_id = manager.spec.run_id
        assert "Settings changed" not in client.post("/form-state", data=form).text
        changed = client.post("/form-state", data={**form, "seed": "12"}).text
        assert f"Settings changed since run #{run_id}" in changed
        assert "Previous settings" in changed
        broken = client.post(
            "/form-state", data={**form, "heat_clothing": "nonsense"}
        ).text
        assert "currently cannot be run: Heat clothing:" in broken
        bar = to_xml(_clear_run_bar())
        assert f"Clear the results of run #{run_id} from this view?" in bar
        assert "files on disk are kept" in bar
        _drop_temp_trajectory()
        client.post("/clear")
        assert client.post("/form-state", data={**form, "seed": "12"}).text == ""
