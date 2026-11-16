"""The AnticipationVelocityModel's own random stream follows the run seed (#758).

JuPedSim fills the model's ``rng_seed`` with a random number once per
process, so two processes running the same scenario with the same seed
diverged. The run seed now derives it (``agent_seed.model_seed``).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from pyfds_evac.core.agent_seed import PURPOSE_MODEL_RNG, model_seed
from pyfds_evac.core.scenario import _build_model

TESTS_DIR = pathlib.Path(__file__).parent

# Runs the 10 x 6 m deck of test_run_outcome with the AVM and prints a hash
# of every trajectory row and the evacuation time.
_CHILD = """
import contextlib, hashlib, io, sqlite3, sys
sys.path.insert(0, {tests_dir!r})
from test_run_outcome import ENOUGH_S, _scenario
from pyfds_evac.core.scenario import run_scenario

scenario = _scenario(ENOUGH_S)
scenario.model_type = "AnticipationVelocityModel"
scenario.sim_params["model_type"] = "AnticipationVelocityModel"
with contextlib.redirect_stdout(io.StringIO()):
    result = run_scenario(scenario, seed=int(sys.argv[1]))
try:
    with sqlite3.connect(result.sqlite_file) as db:
        rows = db.execute("SELECT * FROM trajectory_data ORDER BY frame, id").fetchall()
    digest = hashlib.sha256(repr(rows).encode()).hexdigest()
    print(result.status, result.evacuation_time, len(rows), digest)
finally:
    result.cleanup()
"""


def _run_in_new_process(seed: int) -> str:
    done = subprocess.run(
        [sys.executable, "-c", _CHILD.format(tests_dir=str(TESTS_DIR)), str(seed)],
        capture_output=True,
        text=True,
        env=os.environ,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


def test_same_seed_in_two_processes_gives_the_same_trajectories():
    first = _run_in_new_process(5)
    second = _run_in_new_process(5)
    assert first == second


def test_model_seed_is_deterministic_and_63_bit():
    value = model_seed(7, PURPOSE_MODEL_RNG)
    assert value == model_seed(7, PURPOSE_MODEL_RNG)
    assert 0 <= value < 1 << 63


def test_model_seed_counts_none_as_zero():
    assert model_seed(None, PURPOSE_MODEL_RNG) == model_seed(0, PURPOSE_MODEL_RNG)


def test_model_seed_differs_across_seeds_and_purposes():
    seeds = {model_seed(s, PURPOSE_MODEL_RNG) for s in range(50)}
    assert len(seeds) == 50
    assert model_seed(3, PURPOSE_MODEL_RNG) != model_seed(3, "other")


@pytest.mark.parametrize("seed", [0, 1, 123456])
def test_avm_is_built_with_the_derived_seed(seed):
    model = _build_model("AnticipationVelocityModel", {}, seed)
    assert model.rng_seed == model_seed(seed, PURPOSE_MODEL_RNG)
