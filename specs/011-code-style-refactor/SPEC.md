# 011 — Code-style refactoring: nesting depth, logging, guard clauses

## Motivation

Several core runtime modules had accumulated deeply nested control flow —
functions with 3–4 levels of indentation — and silent `except: pass` blocks
that swallowed errors with no diagnostic output.  This made the code hard to
read, harder to test in isolation, and impossible to debug when things went
wrong silently.

## Rules applied

| Rule | Rationale |
|------|-----------|
| Max 2 indentation levels per function | Beyond 2 levels, logic is hard to follow without scrolling horizontally |
| Guard clauses and early returns | Invert conditions to exit early rather than nesting the happy path |
| Extract complex branches into named functions | Named functions document intent; branches can be tested independently |
| No bare `except: pass` | Silent failures hide bugs; use typed exceptions and log with context |
| `except Exception` only as last resort | Prefer narrow exception types; always bind and log the error variable |

## Changes per module

### `pyfds_evac/core/visibility.py`

**`extract_sign_descriptors`** — replaced a triple-nested
`for / for / if` loop with a single dict comprehension.  Same semantics,
zero nesting.

**`VisibilityModel.__init__`** — the if/else that chose between loading a
cached vismap and building a new one was extracted into two named helpers:

- `_build_cache_from_fds` — runs `fdsvismap`, converts arrays, optionally
  saves the cache.
- `_resolve_vis` — tries the cache first; falls back to `_build_cache_from_fds`.

`__init__` is now two sequential assignments with no branching.

See spec 010 for the full visibility cache design.

### `pyfds_evac/core/direct_steering_runtime.py`

**`update_checkpoint_speed`** had 4 levels of nesting:
a function body → `if checkpoint_key` → `if factor > threshold` →
`if is_inside_polygon`.  Extracted into two pure helpers:

- `_find_checkpoint_zone(checkpoint_key, stage_cfg, x, y)` — returns
  `(zone_key, speed_factor)` or `None`.
- `_find_steering_zone(direct_steering_info, x, y)` — scans all steering
  zones and returns the one with the strongest active speed modifier, or
  `None`.

`update_checkpoint_speed` now reads:

```python
zone = _find_checkpoint_zone(...) if checkpoint_key and stage_cfg else None
zone = zone or _find_steering_zone(...)
if zone is None:
    restore_agent_speed(...)
    return
# apply speed
```

**`advance_path_target`** had a weighted-random selection buried inside an
`if/else` with a `for` loop inside the `else` branch.  Extracted into
`_weighted_choice(candidates, rng)`, which is now independently testable.

**`assign_agent_target`** — the original code silently tried tuple assignment,
then list assignment, swallowing both failures.  The refactored version:

1. Tries tuple `(tx, ty)` first (preferred by most runtimes).
2. Falls back to list `[tx, ty]` if that raises `AttributeError` or
   `TypeError` (some runtimes only accept lists).
3. Logs a `WARNING` only if both assignments fail, including the exception
   message.

The list fallback was intentionally preserved — removing it caused a functional
regression for runtimes that only accept list targets.

**`is_inside_polygon`** — moved the `from shapely.geometry import Point` import
outside the `try` block (it cannot fail due to polygon logic) so the `except`
only catches genuine geometry errors.  Narrowed from `except Exception` to
`except (ValueError, TypeError)`.

### `pyfds_evac/core/route_graph.py`

**`_polyline_midpoint`** — previously returned `(0.0, 0.0)` for an empty
waypoint list.  This was a silent sentinel that could produce incorrect route
midpoints downstream.  Changed to raise `ValueError` so callers are forced to
guard against empty inputs explicitly.  The exception contract is documented in
the docstring.

**`StageGraph.from_scenario` auto-edge condition** — the guard
`if not transitions:` was too broad: it would auto-generate
`distribution → exit` edges even for scenarios that define checkpoints or zones
but happen to leave `transitions` empty.  Tightened to:

```python
if not transitions and all(
    n.stage_type in ("distribution", "exit") for n in graph.nodes.values()
):
```

This restricts auto-edges to genuinely minimal configs (distributions + exits
only).

### `pyfds_evac/core/scenario.py`

**Agent removal** — `simulation.mark_agent_for_removal(agent_id)` was wrapped
in `except Exception: pass`.  Changed to log a `WARNING` with the agent ID and
exception message.

**`_logger` placement** — `logging.getLogger(__name__)` must be defined
*after* all imports.  Placing it before the `try/except jupedsim` block breaks
ruff's E402 exemption for optional-dependency try/except patterns, causing
every subsequent import to be flagged.

## What was not changed

- Public APIs (`VisibilityModel`, `node_is_visible`, `update_checkpoint_speed`,
  `advance_path_target`, etc.) are unchanged.
- No logic was altered in modules that were not flagged for nesting violations.
- The `scenario.py` main simulation loop (`run_scenario`) was not refactored —
  it is large and complex enough to warrant its own dedicated spec if needed.
