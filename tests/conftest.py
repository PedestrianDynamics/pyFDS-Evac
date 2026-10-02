"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _plain_help(monkeypatch):
    """Render ``--help`` without ANSI styles, also under ``pytest -s``.

    The CLI's rich help formatter styles its output on a terminal; tests
    that search the help text need the plain text. A dumb terminal turns
    the styles off even when FORCE_COLOR is set.
    """
    monkeypatch.setenv("TERM", "dumb")
