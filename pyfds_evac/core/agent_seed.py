"""Per-agent random streams keyed by spawn order, not by JuPedSim id.

JuPedSim numbers agents process-wide, and a refused ``add_agent`` still uses
up an id, so the id of "the third agent from this spawn area" differs between
two runs with the same seed (#198, #353). pyFDS-Evac therefore counts its own
spawns: each agent gets a key ``(origin, n)``, the n-th agent added from
*origin*, right after ``add_agent`` succeeds. Every per-agent random draw is
seeded from that key, the run seed and a purpose name. The JuPedSim id stays
the lookup key for all per-agent state and output.
"""

from __future__ import annotations

import hashlib
import random

# Spawn origin of the agents placed before the first step; flow sources are
# ``flow:<distribution key>``.
INITIAL_ORIGIN = "initial"

SpawnKey = tuple[str, int]

# One stream per purpose, so an agent's draws for different decisions are
# independent of each other.
PURPOSE_FAMILIARITY = "familiarity"
PURPOSE_VARIANT = "variant"
PURPOSE_PATH_CHOICE = "path_choice"
PURPOSE_TARGET = "target"
PURPOSE_STEERING = "steering"
PURPOSE_WAIT = "wait"
PURPOSE_NEXT_STAGE = "next_stage"
PURPOSE_INCAP_GAS = "incap_gas"
PURPOSE_INCAP_HEAT = "incap_heat"

# One stream per distribution and purpose, keyed by the distribution key.
PURPOSE_POSITIONS = "positions"
PURPOSE_SHUFFLE = "shuffle"
PURPOSE_PREMOVEMENT = "premovement"
PURPOSE_AGENT_VALUES = "agent_values"

# Hashed into every per-agent seed; fixed so that those seeds stay as they are.
_AGENT_SEED_TAG = "spawn-key-blake2b-v1"
_DISTRIBUTION_SEED_TAG = "distribution-blake2b-v1"

# Bumped whenever a derivation below changes; recorded in the manifest.
# v2: per-distribution streams are hashed from the distribution key (#360).
SEEDING_SCHEME = "spawn-key-blake2b-v2"

_SEED_MASK = (1 << 63) - 1
# numpy's legacy seeding, which jupedsim's distribute_* functions use,
# accepts only seeds below 2**32.
_NUMPY_SEED_MASK = (1 << 32) - 1


class SpawnKeyError(RuntimeError):
    """An agent has no spawn key, or not the one its spawn site expects."""


def agent_seed(run_seed: int | None, key: SpawnKey, purpose: str) -> int:
    """Return a deterministic 63-bit seed for one agent's *purpose* stream.

    The value depends only on the arguments: not on the process, the platform
    or ``PYTHONHASHSEED``. A ``None`` run seed counts as 0.
    """
    origin, index = key
    run = 0 if run_seed is None else int(run_seed)
    # "\x1f" (unit separator) cannot occur in a distribution key, so the
    # encoding is unambiguous.
    text = "\x1f".join((_AGENT_SEED_TAG, purpose, str(run), origin, str(int(index))))
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _SEED_MASK


def distribution_seed(run_seed: int | None, dist_key: str, purpose: str) -> int:
    """Return a deterministic 32-bit seed for one distribution's *purpose* stream.

    Hashing ``(run seed, purpose, distribution key)`` keeps the streams of two
    distributions, and of consecutive run seeds, apart: ``seed + index`` gave
    distribution 1 under seed s the stream of distribution 0 under s + 1
    (#360). The value fits numpy's legacy seeding. A ``None`` run seed
    counts as 0.
    """
    run = 0 if run_seed is None else int(run_seed)
    text = "\x1f".join((_DISTRIBUTION_SEED_TAG, purpose, str(run), str(dist_key)))
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & _NUMPY_SEED_MASK


def agent_rng(run_seed: int | None, key: SpawnKey, purpose: str) -> random.Random:
    """Return a ``random.Random`` seeded by :func:`agent_seed`."""
    return random.Random(agent_seed(run_seed, key, purpose))


def steering_seeds(run_seed: int | None, key: SpawnKey) -> dict[str, int]:
    """Return the seeds a path agent's direct steering draws from later.

    ``base_seed`` seeds the target point in each later stage, ``wait_seed``
    the waiting time and ``choice_seed`` the next-stage choice; each is offset
    by the stage step within its own stream.
    """
    return {
        "base_seed": agent_seed(run_seed, key, PURPOSE_STEERING),
        "wait_seed": agent_seed(run_seed, key, PURPOSE_WAIT),
        "choice_seed": agent_seed(run_seed, key, PURPOSE_NEXT_STAGE),
    }


def stagger_index(key: SpawnKey) -> int:
    """Return the reevaluation stagger index of the agent spawned at *key*.

    ``n + 1`` spreads the agents of one origin evenly over the reevaluation
    interval, and matches the JuPedSim ids 1..N of a single-origin run in a
    fresh process.
    """
    return int(key[1]) + 1


def assign_spawn_key(
    spawn_keys: dict[int, SpawnKey],
    origin_counts: dict[str, int],
    agent_id: int,
    origin: str,
) -> SpawnKey:
    """Return ``(origin, n)`` for the agent spawned n-th from *origin*.

    Counting per origin keeps the pairing when a blocked flow source spawns
    later than in the replayed run, which a single counter would shift. An
    agent that already has a key keeps it.
    """
    if agent_id in spawn_keys:
        return spawn_keys[agent_id]
    key = (origin, origin_counts.get(origin, 0))
    origin_counts[origin] = key[1] + 1
    spawn_keys[agent_id] = key
    return key


def pending_spawn_key(origin_counts: dict[str, int], origin: str) -> SpawnKey:
    """Return the key the next successful spawn from *origin* will get."""
    return (origin, origin_counts.get(origin, 0))


def commit_spawn_key(
    spawn_keys: dict[int, SpawnKey],
    origin_counts: dict[str, int],
    agent_id: int,
    expected: SpawnKey,
) -> SpawnKey:
    """Key a just-added agent, which must get the *expected* pending key.

    A flow spawn draws from :func:`pending_spawn_key` before ``add_agent``;
    raise SpawnKeyError when the key it is then given differs.
    """
    key = assign_spawn_key(spawn_keys, origin_counts, agent_id, expected[0])
    if key != expected:
        raise SpawnKeyError(
            f"Agent {agent_id} was keyed {key!r} but drew from {expected!r}."
        )
    return key


def lookup_spawn_key(
    spawn_keys: dict[int, SpawnKey], agent_id: int, origin: str | None = None
) -> SpawnKey:
    """Return the key of *agent_id*; raise SpawnKeyError if it has none.

    Keys are assigned where the agent is added, so a missing key means a spawn
    site draws before keying its agent. With *origin*, the key must also come
    from that origin.
    """
    key = spawn_keys.get(agent_id)
    if key is None:
        raise SpawnKeyError(f"Agent {agent_id} has no spawn key.")
    if origin is not None and key[0] != origin:
        raise SpawnKeyError(
            f"Agent {agent_id} has spawn key {key!r}, expected origin {origin!r}."
        )
    return key
