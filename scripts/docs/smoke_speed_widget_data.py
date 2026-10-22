"""Write the smoke-speed parameters that the Quickstart widget reads.

The interactive widget on the Quickstart page evaluates the default speed law
in the browser. Its parameters come from ``site/data/smoke_speed.json``, which
this script writes from ``SmokeSpeedConfig()`` (the sight-distance constant
excepted, see below), so the widget and the Python model share one source. ``tests/test_smoke_speed_widget.py`` fails when the
file and the code disagree.

Run from the repository root::

    uv run python scripts/docs/smoke_speed_widget_data.py
"""

import json
from pathlib import Path

from pyfds_evac import SmokeSpeedConfig

# The widget shows the sight distance C / K next to the Frantzich-Nilsson factor
# with the FDS convention C = 3 (as the Quickstart example does). It is not the
# paper's A of the fridolf law, which SmokeSpeedConfig.visibility_factor_c holds.
SIGHT_DISTANCE_FACTOR_C = 3.0

OUT = Path(__file__).resolve().parents[2] / "site" / "data" / "smoke_speed.json"


def widget_parameters():
    """The default speed-law parameters, as the widget reads them."""
    config = SmokeSpeedConfig()
    return {
        "source": "pyfds_evac.SmokeSpeedConfig() defaults (visibility_factor_c: "
        "the FDS sight-distance convention), written by "
        "scripts/docs/smoke_speed_widget_data.py",
        "speed_law": config.speed_law,
        "alpha": config.alpha,
        "beta": config.beta,
        "min_speed_factor": config.min_speed_factor,
        "visibility_factor_c": SIGHT_DISTANCE_FACTOR_C,
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(widget_parameters(), indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
