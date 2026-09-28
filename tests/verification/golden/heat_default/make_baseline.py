"""Write the default-mode heat FED baseline used by test_heat_endpoint_coupled.

Run from the root of a checkout *without* ``--heat-endpoint`` (the baseline
must come from code that predates the option)::

    PYTHONPATH=. python tests/verification/golden/heat_default/make_baseline.py

It runs the corridor of ``test_heat_endpoint_coupled`` for 30 s under the
Table 63.21 temperature history with the default law (Eq. 63.44) and writes
``fed_history.csv`` and ``manifest.json`` next to this file. Manifest values
that depend on the machine, the time or the checkout are replaced by
``"<normalised>"``.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "verification"))

from harness import CorridorSpec, SyntheticSampler, corridor_scenario  # noqa: E402

import run  # noqa: E402
from pyfds_evac.core.fed import (  # noqa: E402
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
    TenabilityConfig,
)
from pyfds_evac.core.scenario import run_scenario  # noqa: E402

TABLE_63_21_C = [20.0, 65.0, 125.0, 220.0, 405.0, 405.0]
VOLATILE_MANIFEST_KEYS = (
    "versions",
    "uv_lock_sha256",
    "git_commit",
    "git_dirty",
    "scenario_path",
    "fds_version",
    "created_utc",
)


def _field(t, x, y):
    return TABLE_63_21_C[min(int(t // 60.0), len(TABLE_63_21_C) - 1)]


def main() -> None:
    spec = CorridorSpec(
        length_m=120.0,
        width_m=4.0,
        num_agents=2,
        v0=0.3,
        seed=11,
        max_simulation_time=30.0,
    )
    model = DefaultHeatFedModel(
        FdsHeatField(SyntheticSampler(_field)),  # type: ignore[arg-type]
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=model,
        tenability_config=TenabilityConfig(
            enable_fic_speed=False,
            enable_incapacitation=False,
            enable_heat_incapacitation=True,
            heat_fed_threshold=1.0,
            heat_incapacitation_mode="deterministic",
        ),
    )
    try:
        run._write_fed_history_csv(result.fed_history, str(HERE / "fed_history.csv"))
        manifest = json.loads(pathlib.Path(result.manifest_file).read_text())
        for key in VOLATILE_MANIFEST_KEYS:
            manifest[key] = "<normalised>"
        (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        result.cleanup()
    with open(HERE / "fed_history.csv", newline="", encoding="utf-8") as handle:
        print(sum(1 for _ in csv.reader(handle)) - 1, "rows")


if __name__ == "__main__":
    main()
