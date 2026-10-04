"""Every GUI launcher listens on 127.0.0.1 unless --host widens it (#477)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from pyfds_evac.webapp.launch import warn_if_exposed

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.1.1", "::1", "localhost"])
def test_no_warning_on_loopback(host, capsys):
    warn_if_exposed(host, 5001)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "myhost"])
def test_warning_when_reachable_from_other_computers(host, capsys):
    warn_if_exposed(host, 5001)
    err = capsys.readouterr().err
    assert f"listens on {host}:5001" in err
    assert "--host 127.0.0.1" in err


def _record_serve(monkeypatch, target: str) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(target, lambda *a, **kw: calls.append(kw))
    monkeypatch.delenv("PORT", raising=False)
    return calls


@pytest.mark.parametrize(
    ("argv", "host"), [([], "127.0.0.1"), (["--host", "0.0.0.0"], "0.0.0.0")]
)
def test_repo_app_py_binds_loopback_by_default(argv, host, monkeypatch, capsys):
    pytest.importorskip("fasthtml")
    calls = _record_serve(monkeypatch, "pyfds_evac.webapp.app.serve")
    monkeypatch.setattr(sys, "argv", ["app.py", *argv])
    runpy.run_path(str(REPO / "app.py"), run_name="__main__")
    assert calls == [{"host": host, "port": 5001}]  # reload left at serve's default
    assert ("Warning" in capsys.readouterr().err) is (host != "127.0.0.1")


@pytest.mark.parametrize(
    ("argv", "host"), [([], "127.0.0.1"), (["--host", "0.0.0.0"], "0.0.0.0")]
)
def test_module_main_binds_loopback_by_default(argv, host, monkeypatch):
    pytest.importorskip("fasthtml")
    import pyfds_evac.webapp.app as app_module

    calls = _record_serve(monkeypatch, "pyfds_evac.webapp.app.serve")
    app_module._main(argv)
    assert calls == [{"appname": "pyfds_evac.webapp.app", "host": host, "port": 5001}]


@pytest.mark.parametrize(
    ("argv", "host"), [([], "127.0.0.1"), (["--host", "0.0.0.0"], "0.0.0.0")]
)
def test_gui_command_warns_only_when_exposed(argv, host, monkeypatch, capsys):
    pytest.importorskip("fasthtml")
    from pyfds_evac.webapp.launch import main

    calls = _record_serve(monkeypatch, "fasthtml.common.serve")
    assert main(argv) == 0
    assert calls[0]["host"] == host
    assert calls[0]["reload"] is False
    assert ("Warning" in capsys.readouterr().err) is (host != "127.0.0.1")
