"""Per-agent seeds derived from the spawn key (#353, #198)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyfds_evac.core.agent_seed import (
    INITIAL_ORIGIN,
    PURPOSE_FAMILIARITY,
    PURPOSE_TARGET,
    PURPOSE_VARIANT,
    SpawnKeyError,
    agent_rng,
    agent_seed,
    assign_spawn_key,
    commit_spawn_key,
    lookup_spawn_key,
    pending_spawn_key,
    stagger_index,
    steering_seeds,
)

REPO = Path(__file__).resolve().parents[1]

# Pinned: a change here changes every seeded outcome of every run.
PINNED = [
    ((42, ("initial", 0), "target"), 5594054523024230979),
    ((42, ("initial", 1), "target"), 8573566365834259600),
    ((42, ("initial", 0), "familiarity"), 2204500926416652498),
    ((None, ("flow:jps-distributions_0", 7), "variant"), 7957128368408702199),
    ((7, ("flow:jps-distributions_0", 7), "variant"), 7249145476771044721),
]


@pytest.mark.parametrize(("args", "expected"), PINNED)
def test_agent_seed_is_pinned(args, expected):
    assert agent_seed(*args) == expected


def test_agent_seed_fits_in_63_bits():
    seeds = [
        agent_seed(s, ("initial", n), PURPOSE_TARGET)
        for s in range(5)
        for n in range(200)
    ]
    assert all(0 <= s < 2**63 for s in seeds)


def test_none_seed_counts_as_zero():
    key = ("initial", 3)
    assert agent_seed(None, key, PURPOSE_TARGET) == agent_seed(0, key, PURPOSE_TARGET)


_PRINT_SEEDS = (
    "from pyfds_evac.core.agent_seed import agent_seed\n"
    "print([agent_seed(42, ('initial', n), 'target') for n in range(5)])\n"
)


def test_agent_seed_ignores_hash_randomisation():
    outputs = set()
    for hash_seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(REPO)}
        done = subprocess.run(
            [sys.executable, "-c", _PRINT_SEEDS],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.add(done.stdout)
    assert outputs == {
        str([agent_seed(42, ("initial", n), "target") for n in range(5)]) + "\n"
    }


def test_streams_are_independent():
    key = ("initial", 0)
    seeds = {
        agent_seed(1, key, PURPOSE_TARGET),
        agent_seed(1, key, PURPOSE_FAMILIARITY),
        agent_seed(1, key, PURPOSE_VARIANT),
        agent_seed(2, key, PURPOSE_TARGET),
        agent_seed(1, ("initial", 1), PURPOSE_TARGET),
        agent_seed(1, ("flow:a", 0), PURPOSE_TARGET),
    }
    assert len(seeds) == 6


def test_neighbouring_agents_do_not_share_draws():
    # The old seed + id * 9973 made agent a's stream at offset 9973 equal to
    # agent a+1's stream at 0; hashed keys do not line up that way.
    first = [agent_rng(1, ("initial", n), PURPOSE_TARGET).random() for n in range(500)]
    assert len(set(first)) == 500
    mean = sum(first) / len(first)
    assert 0.45 < mean < 0.55


def test_spawn_key_counts_per_origin_and_is_idempotent():
    keys, counts = {}, {}
    assert assign_spawn_key(keys, counts, 10, INITIAL_ORIGIN) == ("initial", 0)
    assert assign_spawn_key(keys, counts, 12, "flow:a") == ("flow:a", 0)
    assert assign_spawn_key(keys, counts, 13, INITIAL_ORIGIN) == ("initial", 1)
    assert assign_spawn_key(keys, counts, 10, INITIAL_ORIGIN) == ("initial", 0)
    assert pending_spawn_key(counts, "flow:a") == ("flow:a", 1)
    assert pending_spawn_key(counts, "flow:b") == ("flow:b", 0)


def test_lookup_spawn_key_is_strict():
    keys = {5: ("flow:a", 0)}
    assert lookup_spawn_key(keys, 5) == ("flow:a", 0)
    assert lookup_spawn_key(keys, 5, "flow:a") == ("flow:a", 0)
    with pytest.raises(SpawnKeyError):
        lookup_spawn_key(keys, 6)
    with pytest.raises(SpawnKeyError):
        lookup_spawn_key(keys, 5, INITIAL_ORIGIN)


def test_stagger_index_matches_fresh_process_ids():
    assert [stagger_index(("initial", n)) for n in range(3)] == [1, 2, 3]


def test_steering_seeds_are_three_streams():
    seeds = steering_seeds(1, ("initial", 0))
    assert set(seeds) == {"base_seed", "wait_seed", "choice_seed"}
    assert len(set(seeds.values())) == 3


def test_commit_spawn_key_checks_the_pending_key():
    keys, counts = {}, {}
    pending = pending_spawn_key(counts, "flow:a")
    assert commit_spawn_key(keys, counts, 7, pending) == ("flow:a", 0)
    with pytest.raises(SpawnKeyError, match="drew from"):
        commit_spawn_key(keys, counts, 8, pending)
