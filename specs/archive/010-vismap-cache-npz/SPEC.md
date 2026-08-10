# 010 — Visibility cache: pickle → NumPy npz

## Problem

The previous `VisibilityModel` stored its pre-computed visibility arrays in a
Python **pickle** file.  Pickle is unsafe by design: loading a pickle file
executes arbitrary Python code.  A cache file from an untrusted source — or one
that has been tampered with — can compromise the entire process.

Additionally, the cache held the full `fdsvismap.VisMap` object, which carries
all raw FDS reader state (slice objects, file handles, large intermediate
arrays).  Reloading this object was therefore much heavier than necessary.

Separately, the old `extract_sign_descriptors` used Python tuples as waypoint
entries.  Tuples survive in memory but do not round-trip through JSON: they
become lists after `json.dumps → json.loads`.  This caused the metadata
comparison inside the cache loader to always fail (cache miss every run).

## Goals

1. Replace pickle with a format that is **safe to load** and contains only the
   data that is actually needed at query time.
2. Store only the minimum necessary arrays: time points, spatial coordinates,
   and the boolean visibility tensor.
3. Make the metadata comparison **stable** across JSON round-trips.
4. Keep the public API (`VisibilityModel`, `node_is_visible`) unchanged.

## Design

### Cache format — `.npz`

NumPy's `np.savez_compressed` / `np.load` operates on named arrays only.
There is no code execution path.  The file is safe to load with
`allow_pickle=False` (enforced).

The cache stores five named arrays:

| Key           | Shape / dtype        | Description                              |
|---------------|----------------------|------------------------------------------|
| `time_points` | `(T,)` float64       | Simulation time points (seconds)         |
| `x_coords`    | `(W,)` float64       | X grid coordinates of the vismap         |
| `y_coords`    | `(H,)` float64       | Y grid coordinates of the vismap         |
| `vis`         | `(T, N_wp, H, W)` bool | Visibility for each time, waypoint, cell |
| `meta`        | scalar str (JSON)    | Metadata for cache invalidation          |

The file is always written with a `.npz` suffix regardless of the suffix
supplied by the caller.  If the caller passes a path with a different suffix
(e.g. `vis.pkl`), a `WARNING` is logged naming the effective path.

### Metadata and cache invalidation

`_make_meta` builds a dict that uniquely identifies a vismap computation:

```python
{
    "fds_dir": "<resolved absolute path>",
    "waypoints": [[node_id, x, y, alpha, c], ...],  # lists, not tuples
    "time_step_s": float,
    "slice_height_m": float,
}
```

Waypoints are stored as **lists of lists** (not tuples) so that the dict
survives a `json.dumps → json.loads` round-trip without changing its structure.
On load, `json.loads(str(data["meta"]))` is compared directly to the in-memory
`expected_meta`.

Cache invalidation triggers on any change to: FDS dataset directory, waypoint
coordinates/angles/extinction coefficients, time step, or slice height.

### `_VisMapCache` wrapper

A lightweight class that wraps the three coordinate arrays and the boolean
tensor.  It exposes one method:

```python
def wp_is_visible(self, time: float, x: float, y: float, waypoint_id: int) -> bool
```

Index lookup uses `np.searchsorted` (O(log N)) rather than `np.abs(...).argmin()`
(O(N)).  This matters because `node_is_visible` is called inside routing and
cognitive-map expansion loops that may run thousands of times per simulation
step.

### Module structure

```
_make_meta(...)           → dict
_build_vismap(...)        → fdsvismap.VisMap
_vis_bool_array(vis)      → np.ndarray (T, N_wp, H, W) bool
_save_vismap_cache(path, vis, arrays, meta)
_load_vismap_cache(path, expected_meta) → _VisMapCache | None
_build_cache_from_fds(...)  → _VisMapCache   (computes + optionally saves)
_resolve_vis(...)           → _VisMapCache   (load or build)
VisibilityModel.__init__    → calls _resolve_vis, builds _wp_ids index
```

`_vis_bool_array` is called **once** inside `_build_cache_from_fds`.  The
resulting array is passed to both the in-memory `_VisMapCache` and
`_save_vismap_cache`, avoiding a second conversion pass.

### `np.load` as context manager

`np.load` returns an `NpzFile` object that holds open file descriptors.
The cache loader uses it as a context manager (`with np.load(...) as data:`)
so that descriptors are released immediately after the arrays are copied into
`_VisMapCache`, regardless of whether a metadata mismatch causes an early
return.

## Migration from pickle

Existing `.pkl` caches are silently ignored (the `.npz` path will not exist,
triggering a recompute).  No migration script is needed.  The `force_recompute`
flag on `VisibilityModel` can be used to explicitly regenerate.
