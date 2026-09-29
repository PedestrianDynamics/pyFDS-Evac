"""The Quickstart's smoke-speed widget computes what the Python model computes.

The widget (``site/assets/js/smoke-speed-experiment.js``) evaluates the default
speed law in the browser, with parameters read from
``site/data/smoke_speed.json``. These tests fail when that file no longer holds
the ``SmokeSpeedConfig()`` defaults, or when the JavaScript law and visibility
differ from ``speed_factor_from_extinction`` and ``S = C / K``.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pyfds_evac import SmokeSpeedConfig
from pyfds_evac.core.smoke_speed import speed_factor_from_extinction

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data" / "smoke_speed.json"
WIDGET = ROOT / "site" / "assets" / "js" / "smoke-speed-experiment.js"
GENERATOR = ROOT / "scripts" / "docs" / "smoke_speed_widget_data.py"

# The slider's range, the clamp region beyond it, and inputs the Python law
# treats as clear air.
K_VALUES = [i / 10 for i in range(0, 51)] + [8.0, 11.0, 11.2, 20.0, 100.0, -1.0]


def _params():
    return json.loads(DATA.read_text())


def test_data_file_holds_the_config_defaults():
    config = SmokeSpeedConfig()
    params = _params()
    assert params["speed_law"] == config.speed_law
    assert params["alpha"] == config.alpha
    assert params["beta"] == config.beta
    assert params["min_speed_factor"] == config.min_speed_factor
    assert params["visibility_factor_c"] == config.visibility_factor_c


def test_generator_reproduces_the_data_file():
    spec = {"__name__": "widget_data", "__file__": str(GENERATOR)}
    exec(compile(GENERATOR.read_text(), str(GENERATOR), "exec"), spec)
    assert spec["widget_parameters"]() == _params()


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_javascript_matches_python():
    p = _params()
    script = (
        f"const m = require({json.dumps(str(WIDGET))});"
        f"const ks = {json.dumps(K_VALUES)};"
        "console.log(JSON.stringify(ks.map(k => ["
        f"m.speedFactor(k, {p['alpha']}, {p['beta']}, {p['min_speed_factor']}),"
        f"m.visibility(k, {p['visibility_factor_c']})])));"
    )
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True
    )
    for k, (factor, sight) in zip(K_VALUES, json.loads(proc.stdout), strict=True):
        expected = speed_factor_from_extinction(
            k, alpha=p["alpha"], beta=p["beta"], min_speed_factor=p["min_speed_factor"]
        )
        assert factor == pytest.approx(expected, abs=1e-12), k
        if k > 0:
            assert sight == pytest.approx(p["visibility_factor_c"] / k), k
        else:
            assert sight is None, k  # Infinity serialises to null


def test_quickstart_embeds_the_widget():
    page = (ROOT / "docs" / "quickstart.md").read_text()
    assert "{{< smoke-speed-experiment" in page
