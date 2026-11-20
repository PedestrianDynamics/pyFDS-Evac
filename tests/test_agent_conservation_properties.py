"""Property test for the outcome counts of a run (#836, #904).

Kind: property or invariant. ``_outcome_counts`` assembles the counts that
``run_scenario`` reports from the agents placed at the start, the flow
counters and the agents left inside. For any counts with each source
spawning at most its configured number, and no more agents inside than
entered:

* ``total = evacuated + remaining`` (agents that entered either left or are
  inside);
* ``total + not_spawned`` is what the deck configured;
* a run is complete exactly when nobody is inside and nobody is still to
  enter.

The fixed runs in ``test_agent_conservation.py`` check the same counts end
to end; this one covers the arithmetic over generated counts.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from pyfds_evac.core.scenario import _outcome_counts

# Fixed examples so CI runs are reproducible; no example database on disk.
_SETTINGS = settings(derandomize=True, database=None, max_examples=300)


@st.composite
def _counts(draw):
    initial = draw(st.integers(min_value=0, max_value=200))
    has_flow = draw(st.booleans())
    numbers = draw(st.lists(st.integers(min_value=0, max_value=100), max_size=4))
    counters = [draw(st.integers(min_value=0, max_value=n)) for n in numbers]
    entered = initial + (sum(counters) if has_flow else 0)
    remaining = draw(st.integers(min_value=0, max_value=entered))
    return initial, has_flow, numbers, counters, remaining


@_SETTINGS
@given(case=_counts())
def test_agents_are_conserved(case):
    initial, has_flow, numbers, counters, remaining = case
    counts = _outcome_counts(initial, has_flow, numbers, counters, remaining)
    assert counts.total == counts.evacuated + remaining
    assert counts.evacuated >= 0
    assert counts.not_spawned >= 0
    configured = initial + (sum(numbers) if has_flow else 0)
    assert counts.total + counts.not_spawned == configured
    assert counts.completed == (remaining == 0 and counts.not_spawned == 0)


@_SETTINGS
@given(case=_counts())
def test_without_flow_only_the_initial_agents_count(case):
    initial, _, numbers, counters, remaining = case
    remaining = min(remaining, initial)
    counts = _outcome_counts(initial, False, numbers, counters, remaining)
    assert (counts.total, counts.not_spawned) == (initial, 0)
