"""Executed browser test of the web GUI's inline JavaScript (#904).

The other webapp tests check the page's scripts by source substring. This
one renders the page in headless Chromium and runs them. External scripts
(Plotly, htmx, KaTeX from CDNs) are blocked, so the test needs no network.
It skips when Playwright's Chromium is not installed
(``uv run playwright install chromium``).
"""

import pytest
from starlette.testclient import TestClient

from pyfds_evac.webapp.app import app

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.browser


@pytest.fixture(autouse=True)
def results_root(tmp_path, monkeypatch):
    """Derived output folders go to a temp root, not the repository."""
    from pyfds_evac.webapp.params import RESULTS_ENV

    root = tmp_path / "results"
    monkeypatch.setenv(RESULTS_ENV, str(root))
    return root


@pytest.fixture
def page():
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except sync_api.Error as exc:
            pytest.skip(f"Chromium not installed: {exc}")
        pg = browser.new_page()
        pg.route("http*://**", lambda route: route.abort())
        html = TestClient(app).get("/").text
        pg.set_content(html, wait_until="domcontentloaded")
        yield pg
        browser.close()


def _note_after_typing(page, folder):
    # The folder box sits in a collapsed section; open it as a user would.
    page.evaluate(
        "for (let d = document.getElementById('output_base').closest('details');"
        " d; d = d.parentElement.closest('details')) d.open = true"
    )
    page.fill("#output_base", folder)
    page.wait_for_function(
        "f => document.getElementById('output-run-note').textContent.includes(f)",
        arg=folder,
    )
    assert page.is_visible("#output-run-note")
    return page.text_content("#output-run-note")


def test_output_folder_note_places_a_relative_folder_under_the_results_root(page):
    """A relative folder is taken under the results root, an absolute one as is.

    Runs the regex ``!/^([\\/~]|[A-Za-z]:\\/)/.test(typed)`` of
    ``_AUTOFILL_JS`` that ``test_webapp_sources_compile_without_escape_warnings``
    checks only as text.
    """
    root = page.get_attribute("#output_base", "data-results-root") or "results"
    note = _note_after_typing(page, "mine")
    assert note == f"Each run writes into {root}/mine/<start time>/"
    for absolute in ("/abs/out", "~/out", "C:/out"):
        note = _note_after_typing(page, absolute)
        assert note == f"Each run writes into {absolute}/<start time>/"
