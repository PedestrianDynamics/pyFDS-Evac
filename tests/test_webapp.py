"""End-to-end tests for the FastHTML web GUI via Starlette's TestClient."""

import io
import pathlib
import shutil
import zipfile

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
    assert 'sse-connect="/progress"' in r.text or "sse_connect" in r.text

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
    manager.start(scenario, kwargs, "ISO-table21")
    with pytest.raises(RuntimeError):
        manager.start(scenario, kwargs, "ISO-table21")
    # Drain to completion so the lock releases for other tests.
    _stream_until_terminal(client)
    _drop_temp_trajectory()


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
                    "output_sqlite": str(out / "run.sqlite"),
                    "export_app_bundle": str(out / "bundle"),
                },
            )
            assert r.status_code == 200
            assert "sse-connect" in r.text or "sse_connect" in r.text
            events = _stream_until_terminal(client)
            assert events[-1] == "done"
            assert manager.status == "done"
            assert manager.result.total_agents >= 1
            assert (out / "run.sqlite").exists()
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
            "output_sqlite": str(out / "run.sqlite"),
            "output_fed_history": str(out / "fed.csv"),
            "export_app_bundle": str(out / "bundle"),
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
    assert (out / "run.sqlite").exists()
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

    def test_blank_uses_the_derived_folder(self):
        opts = self._opts()
        assert opts.output_sqlite == (
            "results/t_junction/probabilistic/seed42/t_junction.sqlite"
        )

    def test_typed_folder_is_honoured(self):
        opts = self._opts(output_base="D:/scratch/my run")
        assert opts.output_sqlite == "D:/scratch/my run/t_junction.sqlite"
        assert opts.output_fed_history == "D:/scratch/my run/t_junction_fed_history.csv"
        assert opts.export_app_bundle == "D:/scratch/my run/bundle"

    def test_typed_folder_is_normalised(self):
        # Backslashes and a trailing separator must not double up in the path.
        opts = self._opts(output_base="out\\runs\\")
        assert opts.output_sqlite == "out/runs/t_junction.sqlite"

    def test_whitespace_only_falls_back_to_derived(self):
        opts = self._opts(output_base="   ")
        assert opts.output_sqlite.startswith("results/t_junction/")

    def test_explicit_path_still_beats_the_folder(self):
        # A fully-specified output path (hidden field) is not overridden.
        opts = self._opts(output_base="out", output_sqlite="exact/place.sqlite")
        assert opts.output_sqlite == "exact/place.sqlite"


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
    assert (
        default_output_base("t_junction", "deterministic", 7)
        == "results/t_junction/deterministic/seed7"
    )
    assert default_output_base("t_junction", None, None).endswith(
        "/probabilistic/seeddefault"
    )


def test_export_app_bundle_is_a_path_not_a_checkbox():
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
    assert opts.export_app_bundle.startswith("results/t_junction/")


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
