"""Opt-in, observational aggregate counters for pyFDS-Evac (G1).

Installed only by ``perf_run.py``; production code is not modified. Each
hook wraps an existing function or method, calls it unchanged with the same
arguments, and only counts from its arguments, its return value and
read-only accessors (``agent_count()``, ``delta_time()``, ``in_grid()``,
``_wp_ids``). No per-sample logging; one JSON file is written at exit.

Counter groups (model_handoff_g0.md §8/§10, review.md I1/I2/I5, spec §6):

- fdsreader: Simulation constructions and their parse seconds per open, with
  the opener. The adapter (#716/#720) turns fdsreader's disk cache off, so every
  open is a full .smv parse; there is no cache state (plan.md D13). The event
  fields ``kind`` and ``pickle_present_at_open`` are kept for old manifests and
  say nothing about cache use
- vismap: smoke-aware path (load hit / miss / build) and clear-air path
  (``VisibilityModel.clear_air``: load hit / build), seconds, grid shape
- sign queries: node_is_visible / visibility_to_node split into
  ``sign`` (in grid), ``off_grid`` (sign, observer off the grid) and
  ``non_sign`` (node without a sign descriptor, unconditionally True), each
  with calls and positive results, by caller, in 10 s bins
- map growth: nodes/edges added by init_cognitive_map, expand_on_arrival,
  _expand_visible; added nodes split into sign / non-sign nodes;
  agents with >= 1 known exit at each 10 s boundary
- routing: reroute evaluations split exit_choice / explore / wander, per pass
  and per 10 s bin; rank_routes and evaluate_route calls; switches
- jupedsim: iterations, agent-steps (agent_count before each step), dt

Timers only around one-off work (fdsreader opens, vismap build/load).

Added for G0 v2 (model_handoff_g0_v2.md §2, plan.md D13): fdsreader opens
carry their opener (calling pyfds_evac/fdsvismap function); the vismap build is
timed in stages (read_fds_data, the lazy slice read inside compute_all,
compute_all, _vis_bool_array, _vis_metre_array) with _get_visibility_array
counts. With PYFDS_PERF_DETAIL=1 a second opt-in group adds caller-keyed
counters (SliceFieldSampler.sample, read_cells, line_parts, _time_index,
_generate_candidates, evaluate_segment, reached_stage, distance_to_polygon,
_occupied, _crowds_agents, _defer_flow_spawn). The detail group walks a few
stack frames per call: it has its own overhead and is diagnostic-only until
measured.

G4 (plan.md D39): with ``PYFDS_PERF_DETAIL=1`` the detail group also times the route paths
(``evaluate_segment``, ``_first_leg``, ``_cell_los_stats``, ``_step_los_stats``, ``read_cells``, ``line_parts``,
``sample_fed_rate``, route-side ``sample``) and counts, per path, total reads against distinct memo keys
(``read_cells``: subslice, frame tuple, cell indices; ``sample_fed_rate``: species frame tuple, x, y;
``sample``: sampler, frame, x, y), under ``detail.route_paths``; wrapper overhead is calibrated at install under
``detail.route_paths_overhead``. Route-side ``sample`` leaves out the species reads behind
``sample_fed_rate``, which are part of that path's time. Timers nest and the inner paths are reached from
several parents, so each path also carries ``by_parent`` (seconds per innermost enclosing path, ``root`` if
none), ``self_seconds`` (seconds not in timed children) and ``hook_seconds`` (detail-group work inside the
timer, already left out of ``seconds``). The time inside ``evaluate_segment`` that no timed child covers is
its ``self_seconds``; the sum of a path's ``seconds`` over all paths double counts nested time.
"""

from __future__ import annotations

import atexit
import functools
import hashlib
import json
import os
import sys
import time
import types
from collections import Counter, defaultdict

import numpy as np

BIN_S = 10.0

C: Counter = Counter()
BINS: dict[str, Counter] = defaultdict(Counter)
EVENTS: dict[str, list] = defaultdict(list)
PASS_SIZES: Counter = Counter()
_CALLER: list[str] = []
_CMAPS: list = []
_EXIT_NODES: set[str] = set()
_STATE = {"iteration": 0, "dt": None, "last_bin": -1,
          "eval_pass_time": None, "eval_pass_n": 0, "new_depth": 0}


def _bin(t: float) -> str:
    return f"{int(float(t) // BIN_S) * int(BIN_S):04d}"


def _wrap(owner, name, make):
    orig = getattr(owner, name)
    if getattr(orig, "_perf_wrapped", False):
        return
    new = make(orig)
    functools.update_wrapper(new, orig)
    new._perf_wrapped = True
    setattr(owner, name, new)


# --- stack helpers ----------------------------------------------------------


def _frame_name(f) -> str:
    return f"{os.path.basename(f.f_code.co_filename)[:-3]}.{f.f_code.co_name}"


def _opener() -> str | None:
    """First frame outside fdsreader and the adapter: who asked for the open."""
    f = sys._getframe(2)
    while f is not None:
        fn = f.f_code.co_filename
        if "/fdsreader/" not in fn and not fn.endswith("fdsreader_adapter.py") \
                and not fn.endswith("contextlib.py") and not fn.endswith("perf_counters.py"):
            return _frame_name(f)
        f = f.f_back
    return None


# Frames of the G4 route-timer wrappers are not callers: skipping them keeps the caller keys
# of the detail counters as they were before the route paths were timed.
_ROUTE_WRAPPER_PREFIX = "_route_"


def _callers(depth: int = 2, skip: int = 2) -> str:
    """'caller<-caller's caller' as module.function names (up to *depth* frames)."""
    f = sys._getframe(skip)
    names = []
    while f is not None and len(names) < depth:
        if not f.f_code.co_name.startswith(_ROUTE_WRAPPER_PREFIX):
            names.append(_frame_name(f))
        f = f.f_back
    return "<-".join(names)


def _scenario_site() -> str:
    """Nearest scenario.py frame as function:line; 'other' if none."""
    f = sys._getframe(2)
    while f is not None:
        if f.f_code.co_filename.endswith("/core/scenario.py"):
            return f"{f.f_code.co_name}:{f.f_lineno}"
        f = f.f_back
    return "other"


# --- fdsreader --------------------------------------------------------------


def _pickle_present(fds_sim_mod, path):
    try:
        smv = fds_sim_mod.get_smv_file(path)
        return any(f.endswith(".pickle") for f in os.listdir(os.path.dirname(smv)))
    except Exception:
        return None


def _hook_fdsreader(fds_sim_mod):
    cls = fds_sim_mod.Simulation
    orig_new = cls.__new__
    orig_init = cls.__init__

    def new(klass, path):
        depth = _STATE["new_depth"]
        if depth == 0:
            _STATE["pickle_before"] = _pickle_present(fds_sim_mod, path)
            _STATE["opener"] = _opener()
        _STATE["new_depth"] = depth + 1
        t0 = time.perf_counter()
        try:
            obj = orig_new(klass, path)
        finally:
            _STATE["new_depth"] = depth
        if depth == 0:
            C["fdsreader_new_calls"] += 1
            EVENTS["fdsreader_new"].append({"seconds": time.perf_counter() - t0})
        else:
            C["fdsreader_new_nested_unpickle"] += 1
        return obj

    def init(self, path):
        cached = hasattr(self, "_hash")
        pickle_before = _STATE.pop("pickle_before", None)
        opener = _STATE.pop("opener", None)
        t0 = time.perf_counter()
        orig_init(self, path)
        kind = "pickle_load" if cached else "full_parse"
        C[f"fdsreader_{kind}"] += 1
        EVENTS["fdsreader_init"].append({
            "kind": kind, "pickle_present_at_open": pickle_before, "opener": opener,
            "seconds_init": time.perf_counter() - t0})

    new._perf_wrapped = True
    init._perf_wrapped = True
    cls.__new__ = staticmethod(new)
    cls.__init__ = init


# --- visibility -------------------------------------------------------------


def _hook_visibility(vis_mod):
    def mk_load(orig):
        def load(path, expected_meta):
            t0 = time.perf_counter()
            res = orig(path, expected_meta)
            npz = str(path)
            npz = npz[:-4] if npz.endswith(".npz") else npz
            EVENTS["vismap"].append({
                "event": "load_hit" if res is not None else "load_miss",
                "seconds": time.perf_counter() - t0,
                "file_existed": os.path.exists(npz + ".npz") or os.path.exists(str(path)),
                "caller": _CALLER[-1] if _CALLER else "other"})
            return res
        return load

    def mk_build(orig):
        def build(*a, **k):
            t0 = time.perf_counter()
            res = orig(*a, **k)
            EVENTS["vismap"].append({
                "event": "built_smoke_aware", "seconds": time.perf_counter() - t0,
                "time_points": int(len(res._time_points)),
                "vis_shape_T_wp_H_W": list(res._vis.shape)})
            return res
        return build

    def mk_resolve(orig):
        def resolve(fds_dir, sign_descriptors, *a, **k):
            t0 = time.perf_counter()
            _CALLER.append("smoke_aware")
            try:
                res = orig(fds_dir, sign_descriptors, *a, **k)
            finally:
                _CALLER.pop()
            EVENTS["vismap"].append({"event": "resolve_smoke_aware",
                                     "seconds": time.perf_counter() - t0,
                                     "signs": len(sign_descriptors)})
            C["vismap_resolve_smoke_aware"] += 1
            return res
        return resolve

    _wrap(vis_mod, "_load_vismap_cache", mk_load)
    _wrap(vis_mod, "_build_cache_from_fds", mk_build)
    _wrap(vis_mod, "_resolve_vis", mk_resolve)

    _hook_vismap_build(vis_mod)

    cls = vis_mod.VisibilityModel
    orig_clear = cls.__dict__["clear_air"].__func__

    def clear_air(klass, walkable, sign_descriptors, **k):
        n_hit = sum(1 for e in EVENTS["vismap"] if e["event"] == "load_hit")
        t0 = time.perf_counter()
        _CALLER.append("clear_air")
        try:
            model = orig_clear(klass, walkable, sign_descriptors, **k)
        finally:
            _CALLER.pop()
        hit = sum(1 for e in EVENTS["vismap"] if e["event"] == "load_hit") > n_hit
        EVENTS["vismap"].append({
            "event": "clear_air_loaded" if hit else "clear_air_built",
            "seconds": time.perf_counter() - t0, "signs": len(sign_descriptors),
            "cell_size_m": k.get("cell_size_m")})
        C["vismap_clear_air"] += 1
        return model

    clear_air._perf_wrapped = True
    cls.clear_air = classmethod(clear_air)

    def mk_query(orig, key):
        def q(self, time_s, x, y, node_id):
            res = orig(self, time_s, x, y, node_id)
            if node_id not in self._wp_ids:
                kind = "non_sign"
            elif not self.in_grid(x, y):
                kind = "off_grid"
            else:
                kind = "sign"
            positive = bool(res) if key == "node_is_visible" else res is not None
            caller = _CALLER[-1] if _CALLER else "other"
            b = _bin(time_s)
            C[f"{key}_calls"] += 1
            C[f"{key}_{kind}_calls"] += 1
            C[f"{key}_{kind}_calls_by_{caller}"] += 1
            BINS[f"{key}_{kind}_calls"][b] += 1
            if positive:
                C[f"{key}_{kind}_positive"] += 1
                BINS[f"{key}_{kind}_positive"][b] += 1
            return res
        return q

    _wrap(cls, "node_is_visible", lambda o: mk_query(o, "node_is_visible"))
    _wrap(cls, "visibility_to_node", lambda o: mk_query(o, "visibility_to_node"))


def _hook_vismap_build(vis_mod):
    """Stage timers of the vismap build; fdsvismap names are wrapped on the class."""
    from fdsvismap import FDSVisMap as fvm

    def mk_stage(stage):
        def mk(orig):
            def f(*a, **k):
                t0 = time.perf_counter()
                try:
                    return orig(*a, **k)
                finally:
                    EVENTS["vismap_build"].append(
                        {"stage": stage, "seconds": time.perf_counter() - t0})
            return f
        return mk

    cls = fvm.VisMap
    _wrap(cls, "read_fds_data", mk_stage("read_fds_data"))
    _wrap(cls, "compute_all", mk_stage("compute_all_incl_slice_read"))
    _wrap(vis_mod, "_extinction_slice_index", mk_stage("extinction_slice_index_open"))
    _wrap(vis_mod, "_vis_bool_array", mk_stage("vis_bool_array"))
    _wrap(vis_mod, "_vis_metre_array", mk_stage("vis_metre_array"))

    def mk_slice(orig):
        def f(self, time_index):
            loading = time_index not in self._slice_frames
            t0 = time.perf_counter()
            res = orig(self, time_index)
            if loading:
                EVENTS["vismap_build"].append(
                    {"stage": "slice_read_lazy", "seconds": time.perf_counter() - t0})
            return res
        return f

    def mk_count(orig, key, timed=False):
        def f(*a, **k):
            C[key] += 1
            if not timed:
                return orig(*a, **k)
            t0 = time.perf_counter()
            try:
                return orig(*a, **k)
            finally:
                C[key + "_s"] += time.perf_counter() - t0
        return f

    _wrap(cls, "_get_slice_frame", mk_slice)
    _wrap(cls, "_get_visibility_array", lambda o: mk_count(o, "get_visibility_array_calls", True))
    _wrap(cls, "_get_mean_extco_array_at_time",
          lambda o: mk_count(o, "get_mean_extco_array_calls"))
    _wrap(cls, "get_extco_array_at_time", lambda o: mk_count(o, "get_extco_array_calls"))


# --- cognitive map ----------------------------------------------------------


def _vis_arg(a, k):
    if "vis_model" in k:
        return k["vis_model"]
    return a[3] if len(a) > 3 else None


def _growth(name):
    def mk(orig):
        def g(*a, **k):
            cmap = a[0]
            nodes0 = set(cmap.known_nodes)
            e0 = len(cmap.known_edges)
            _CALLER.append(name)
            try:
                res = orig(*a, **k)
            finally:
                _CALLER.pop()
            added = cmap.known_nodes - nodes0
            vis = _vis_arg(a, k)
            signs = getattr(vis, "_wp_ids", {}) or {}
            n_sign = sum(1 for n in added if n in signs)
            C[f"{name}_calls"] += 1
            C[f"{name}_nodes_added"] += len(added)
            C[f"{name}_sign_nodes_added"] += n_sign
            C[f"{name}_non_sign_nodes_added"] += len(added) - n_sign
            C[f"{name}_edges_added"] += len(cmap.known_edges) - e0
            if added or len(cmap.known_edges) > e0:
                C[f"{name}_growth_events"] += 1
            if n_sign:
                C[f"{name}_sign_growth_events"] += 1
                BINS[f"{name}_sign_growth_events"][_bin(_time_arg(name, a, k))] += 1
            return res
        return g
    return mk


def _time_arg(name, a, k):
    if "time_s" in k:
        return k["time_s"]
    return a[4] if len(a) > 4 else 0.0


def _hook_cognitive_map(cm_mod, scen_mod):
    def mk_init(orig):
        def init(spawn_node, graph, *a, **k):
            if not _EXIT_NODES:
                _EXIT_NODES.update(
                    n for n, v in graph.nodes.items() if v.stage_type == "exit")
            _CALLER.append("init_cognitive_map")
            try:
                cmap = orig(spawn_node, graph, *a, **k)
            finally:
                _CALLER.pop()
            _CMAPS.append(cmap)
            C["cognitive_maps_created"] += 1
            C["init_known_nodes"] += len(cmap.known_nodes)
            return cmap
        return init

    _wrap(cm_mod, "init_cognitive_map", mk_init)
    _wrap(cm_mod, "expand_on_arrival", _growth("expand_on_arrival"))
    _wrap(cm_mod, "_expand_visible", _growth("_expand_visible"))
    for name in ("init_cognitive_map", "expand_on_arrival"):
        if hasattr(scen_mod, name):
            setattr(scen_mod, name, getattr(cm_mod, name))

    def mk_count(orig, key, none_key):
        def f(*a, **k):
            res = orig(*a, **k)
            C[key] += 1
            if res is None:
                C[none_key] += 1
            return res
        return f

    _wrap(cm_mod, "nearest_frontier_target",
          lambda o: mk_count(o, "frontier_calls", "frontier_none"))
    _wrap(cm_mod, "wander_target", lambda o: mk_count(o, "wander_calls", "wander_none"))


# --- routing ----------------------------------------------------------------


def _hook_routing(rg_mod, scen_mod):
    def mk_eval(orig):
        def ev(*a, **k):
            t = k.get("current_time_s")
            if t != _STATE["eval_pass_time"]:
                if _STATE["eval_pass_time"] is not None:
                    PASS_SIZES[_STATE["eval_pass_n"]] += 1
                _STATE["eval_pass_time"], _STATE["eval_pass_n"] = t, 0
            _STATE["eval_pass_n"] += 1
            w0, f0 = C["wander_calls"], C["frontier_calls"]
            res = orig(*a, **k)
            mode = ("wander" if C["wander_calls"] > w0
                    else "explore" if C["frontier_calls"] > f0 else "exit_choice")
            C["reroute_evaluations"] += 1
            C[f"reroute_evaluations_{mode}"] += 1
            if t is not None:
                BINS["reroute_evaluations"][_bin(t)] += 1
                BINS[f"reroute_evaluations_{mode}"][_bin(t)] += 1
            if res is not None:
                C["reroute_switches"] += 1
            return res
        return ev

    def mk_plain(orig, key):
        def f(*a, **k):
            C[key] += 1
            return orig(*a, **k)
        return f

    _wrap(rg_mod, "evaluate_and_reroute", mk_eval)
    _wrap(rg_mod, "rank_routes", lambda o: mk_plain(o, "rank_routes_calls"))
    _wrap(rg_mod, "evaluate_route", lambda o: mk_plain(o, "evaluate_route_calls"))
    for name in ("evaluate_and_reroute", "rank_routes"):
        if hasattr(scen_mod, name):
            setattr(scen_mod, name, getattr(rg_mod, name))


# --- jupedsim ---------------------------------------------------------------


def _hook_jupedsim(jps_sim_mod):
    def mk_iter(orig):
        def it(self, count=1):
            if _STATE["dt"] is None:
                _STATE["dt"] = float(self.delta_time())
            for _ in range(count):
                n = self.agent_count()
                C["agent_steps"] += n
                C["iterations"] += 1
                t = _STATE["iteration"] * _STATE["dt"]
                BINS["agent_steps"][_bin(t)] += n
                b = int(t // BIN_S)
                if b != _STATE["last_bin"] and _CMAPS:
                    _STATE["last_bin"] = b
                    BINS["agents_with_known_exit"][_bin(t)] = sum(
                        1 for m in _CMAPS if m.known_nodes & _EXIT_NODES)
                if _STATE.get("loop_t0") is None:
                    _STATE["loop_t0"] = time.perf_counter()
                orig(self, 1)
                _STATE["loop_t1"] = time.perf_counter()
                _STATE["iteration"] += 1
        return it

    _wrap(jps_sim_mod.Simulation, "iterate", mk_iter)


# --- detail group (PYFDS_PERF_DETAIL=1) -------------------------------------

_KEYS: dict[str, set] = defaultdict(set)
_KEYS_CAP = 2_000_000

# G4 route paths. Timers nest (read_cells runs inside cell_los_stats inside evaluate_segment,
# and the inner paths are also reached from _first_leg and from sample_fed_rate's callers), so
# each path records, besides its own seconds, the seconds per innermost enclosing path
# (by_parent) and the seconds not covered by timed children (self_seconds). Hook work of the
# detail group that runs inside an open timer (stack walks, key building, counters, the timer
# bookkeeping of nested paths) is measured and left out of every enclosing timer's seconds; it
# is reported as hook_seconds.
ROUTE_PATHS = ("evaluate_segment", "first_leg", "cell_los_stats", "step_los_stats", "read_cells",
               "line_parts", "sample_fed_rate", "sample_route")
# first_leg, first_leg_dose, segment and first_leg_r01 are keyed for the repeat count of G14:
# total calls against distinct exact keys, see _hook_detail. Only first_leg is timed; the other
# three are count-only (calls 0, no seconds).
ROUTE_KEYED = ("read_cells", "sample_fed_rate", "sample_route", "first_leg", "first_leg_dose",
               "segment", "first_leg_r01")


def _blank_path() -> dict:
    return {"calls": 0, "seconds": 0.0, "self_seconds": 0.0, "hook_seconds": 0.0, "by_parent": {}}


RP: dict[str, dict] = defaultdict(_blank_path)
# Keys a memo would use, per path, with the same cap as _KEYS; a capped set under-counts
# distinct keys and so over-states reuse, which is why the cap is reported.
RK: dict[str, set] = defaultdict(set)
_NOOP = "_noop_calibration"
NOOP_CALIBRATION_CALLS = 1_000_000
RK_CAPPED: set[str] = set()
# Open route timers, outermost first: [path, hook_seconds, child_seconds, open_started].
_OPEN: list[list] = []
# True while a key is built: its _time_index / _frames calls are not counted in time_index_*.
_QUIET = [False]


def route_key_frames(frames) -> tuple:
    """Frame index or frame array as a tuple, so 3 and np.array([3]) key alike."""
    if isinstance(frames, (int, np.integer)):
        return (int(frames),)
    return tuple(int(f) for f in frames)


def _uniform_frames(frames):
    """An array whose entries are all one frame reads like that frame as an int."""
    if isinstance(frames, np.ndarray) and frames.size and (frames == frames.flat[0]).all():
        return int(frames.flat[0])
    return frames


def _cells_digest(cells) -> bytes:
    """Digest of cell index arrays by value, so keys stay small."""
    h = hashlib.blake2b(digest_size=16)
    for a in cells:
        h.update(a.tobytes())
        h.update(b"|")
    return h.digest()


def _note_key(path, key):
    s = RK[path]
    RP[path]["total"] = RP[path].get("total", 0) + 1
    if len(s) >= _KEYS_CAP:
        RK_CAPPED.add(path)
        return
    s.add(key)


def _bind(names, a, k) -> dict:
    """Positional and keyword arguments of a wrapped call under the original's parameter names."""
    return {**dict(zip(names, a)), **k}


def _clock_descriptor(clock):
    """What a foresight clock reads, as pyFDS-Evac's own anticipate segment cache keys on.

    None without a clock; otherwise the start time t0 and the latest time any sample may be
    read at, min(horizon_end_s, max(decision_time_s, end_s)). Equal descriptors read equal
    times along equal geometry.
    """
    if clock is None:
        return None
    return (clock.t0, min(clock.horizon_end_s, max(clock.decision_time_s, clock.end_s)))


def _slice_frames(samplers, time_s) -> tuple:
    """Frame index at *time_s* of every FDS slice sampler, from the sampler's own _time_index."""
    return tuple(s._time_index(float(time_s)) for s in samplers)


def _extinction_frames(field, time_s) -> tuple:
    """Frames of the slices an extinction field reads; a field without samplers keys the time."""
    reader = getattr(field, "samplers", None)
    if reader is None:
        return (time_s,)
    return _slice_frames(reader(), time_s)


def _charge(t0):
    """Hook work since t0 ran inside every open route timer: leave it out of their seconds."""
    if not _OPEN:
        return
    dt = time.perf_counter() - t0
    for frame in _OPEN:
        frame[1] += dt


def _in_open(path) -> bool:
    return any(frame[0] == path for frame in _OPEN)


def _note_read(path, build):
    """Count a read under the key build() makes, after the read itself.

    Keys are built after the original call, so it sees the same sampler caches as in an
    uninstrumented run; the key's own _time_index / _frames calls are quiet. A read whose key
    cannot be built (the read failed on the same input) counts as a key of its own.
    """
    h0 = time.perf_counter()
    _QUIET[0] = True
    try:
        key = build()
    except Exception:
        key = object()
    finally:
        _QUIET[0] = False
    _note_key(path, key)
    _charge(h0)


def _open(path):
    """Start a route timer for *path*; returns (frame, t0) for _close."""
    h0 = time.perf_counter()
    frame = [path, 0.0, 0.0, h0]
    _OPEN.append(frame)
    return frame, time.perf_counter()


def _close(frame, t0):
    """End the route timer: net seconds, self seconds and seconds per innermost parent."""
    t1 = time.perf_counter()
    _OPEN.pop()
    net = t1 - t0 - frame[1]
    r = RP[frame[0]]
    r["calls"] += 1
    r["seconds"] += net
    r["self_seconds"] += net - frame[2]
    r["hook_seconds"] += frame[1]
    parent = "root"
    if _OPEN:
        parent = _OPEN[-1][0]
        _OPEN[-1][2] += net
    by_parent = r["by_parent"]
    by_parent[parent] = by_parent.get(parent, 0.0) + net
    if _OPEN:
        # Opening and closing this timer ran inside the enclosing ones.
        bookkeeping = (t0 - frame[3]) + (time.perf_counter() - t1)
        for outer in _OPEN:
            outer[1] += bookkeeping


def _timed(name):
    def make(orig):
        def _route_timed(*a, **k):
            frame, t0 = _open(name)
            try:
                return orig(*a, **k)
            finally:
                _close(frame, t0)
        return _route_timed
    return make


def _route_path_out(path) -> dict:
    out = {**RP[path], "by_parent": dict(sorted(RP[path]["by_parent"].items()))}
    if path in ROUTE_KEYED:
        out["distinct"] = len(RK[path])
        out["capped"] = path in RK_CAPPED
    return out


def _hook_detail(rg_mod, scen_mod):
    from pyfds_evac.core import direct_steering_runtime as dsr
    from pyfds_evac.core import fds_coverage
    from pyfds_evac.core import fds_sampling as fs
    from pyfds_evac.core import simulation_init as si

    cls = fs.SliceFieldSampler

    def mk_sample(orig):
        def sample(self, time_s, x, y):
            h0 = time.perf_counter()
            q = getattr(getattr(self._slice, "quantity", None), "name", "?")
            chain = _callers(6)
            who = f"{q}|{'<-'.join(chain.split('<-')[:5])}"
            C[f"sampler_sample_calls[{who}]"] += 1
            ks = _KEYS[who]
            if len(ks) < _KEYS_CAP:
                ks.add((x, y))
            # Side of the call: the route cost path (sample_fed_rate, evaluate_segment,
            # _polyline_stats, rank_routes) or the per-agent update; anything else is other.
            if any(t in chain for t in ("sample_fed_rate", "evaluate_segment", "_polyline_stats",
                                        "route_graph.")):
                side = "route"
            elif "sample_inputs" in chain or "smoke_speed.sample" in chain:
                side = "agent"
            else:
                side = "other"
            C[f"sampler_sample_by_side[{q}|{side}]"] += 1
            if "_polyline_stats" in chain:
                C["polyline_stats_samples"] += 1
                pk = _KEYS["polyline_stats"]
                if len(pk) < _KEYS_CAP:
                    pk.add((x, y))
            # The species reads behind sample_fed_rate are part of that path's own time.
            if side != "route" or _in_open("sample_fed_rate"):
                _charge(h0)
                return orig(self, time_s, x, y)
            _charge(h0)
            frame, t0 = _open("sample_route")
            try:
                return orig(self, time_s, x, y)
            finally:
                _close(frame, t0)
                # The sampler is part of the key: fields at one point are different reads.
                _note_read("sample_route", lambda: (id(self), self._time_index(time_s), x, y))
        return sample

    def mk_read_cells(orig):
        def read_cells(self, part, times):
            frame, t0 = _open("read_cells")
            try:
                res = orig(self, part, times)
            finally:
                _close(frame, t0)
                _note_read("read_cells", lambda: (
                    id(part.subslice), route_key_frames(_uniform_frames(self._frames(times))),
                    _cells_digest(part.cells)))
            h0 = time.perf_counter()
            C["read_cells_calls"] += 1
            C["read_cells_cells"] += int(getattr(res, "size", 0))
            _charge(h0)
            return res
        return read_cells

    def mk_line_parts(orig):
        def line_parts(self, x0, y0, x1, y1):
            h0 = time.perf_counter()
            cache = self._line_cache
            if (x0, y0, x1, y1) in cache:
                C["line_parts_hits"] += 1
            else:
                C["line_parts_misses"] += 1
                if len(cache) >= fs._LINE_CACHE_SIZE:
                    C["line_parts_clears"] += 1
            _charge(h0)
            frame, t0 = _open("line_parts")
            try:
                return orig(self, x0, y0, x1, y1)
            finally:
                _close(frame, t0)
        return line_parts

    def mk_time_index(orig):
        def time_index(self, ts):
            if _QUIET[0]:
                return orig(self, ts)
            h0 = time.perf_counter()
            C["time_index_hits" if ts in self._t_index_cache else "time_index_misses"] += 1
            _charge(h0)
            return orig(self, ts)
        return time_index

    _wrap(cls, "sample", mk_sample)
    _wrap(cls, "read_cells", mk_read_cells)
    _wrap(cls, "line_parts", mk_line_parts)
    _wrap(cls, "_time_index", mk_time_index)

    def fed_frames(fed_rate_sampler, time_s) -> tuple:
        if fed_rate_sampler is None:
            return ()
        try:
            samplers = fds_coverage.model_samplers(fed_rate_sampler._model)
        except AttributeError:
            return (time_s,)
        return _slice_frames(samplers, time_s)

    # Keys of the G14 repeat count. A key holds every input of the call that can differ between
    # two calls at one field frame; graph and config are fixed within a run. Two calls with
    # equal keys return equal values. A sampler without _time_index would key the raw time.
    seg_args = ("graph", "source", "target", "time_s", "extinction_sampler", "fed_rate_sampler",
                "config", "arrival_time_s", "clock")

    def segment_key(a, k):
        # evaluate_segment: source, target, the extinction and FED frames at the arrival time
        # (arrival_time_s, else time_s) and the foresight-clock descriptor. The FED rate is one
        # sample at the arrival time; with a clock the extinction reads follow the descriptor.
        d = _bind(seg_args, a, k)
        arrival = d.get("arrival_time_s")
        if arrival is None:
            arrival = d["time_s"]
        return (d["source"], d["target"], _extinction_frames(d["extinction_sampler"], arrival),
                fed_frames(d["fed_rate_sampler"], arrival), _clock_descriptor(d.get("clock")))

    def mk_seg(orig):
        def evaluate_segment(*a, **k):
            h0 = time.perf_counter()
            f = sys._getframe(1)
            C[f"evaluate_segment_calls[{_frame_name(f)}:{f.f_lineno}]"] += 1
            if f.f_code.co_name == "_generate_candidates":
                _STATE["seg_p1"] = _STATE.get("seg_p1", 0) + 1
            _charge(h0)
            frame, t0 = _open("evaluate_segment")
            try:
                return orig(*a, **k)
            finally:
                _close(frame, t0)
                _note_read("segment", lambda: segment_key(a, k))
        return evaluate_segment

    leg_args = ("graph", "agent_position", "node_id", "time_s", "extinction_sampler", "config",
                "walks", "clock")

    def walk_served(a, k) -> bool:
        # The condition under which _first_leg returns a cached walk and computes nothing.
        try:
            d = _bind(leg_args, a, k)
            walks = d.get("walks")
            if walks is None:
                return False
            clock = d.get("clock")
            cached = walks.get(d["node_id"] if clock is None else (d["node_id"], "foreseen"))
            return cached is not None and cached.time_s == d["time_s"]
        except Exception:
            return False

    def leg_key(a, k, places):
        # _first_leg: the walk start as passed (rounded to *places* digits when given), the
        # node, the extinction frames at time_s and the foresight-clock descriptor.
        d = _bind(leg_args, a, k)
        x, y = d["agent_position"]
        position = (x, y) if places is None else (round(x, places), round(y, places))
        return (position, d["node_id"], _extinction_frames(d["extinction_sampler"], d["time_s"]),
                _clock_descriptor(d.get("clock")))

    def mk_first_leg(orig):
        timed = _timed("first_leg")(orig)

        def _route_first_leg(*a, **k):
            h0 = time.perf_counter()
            served = walk_served(a, k)
            _charge(h0)
            try:
                return timed(*a, **k)
            finally:
                if served:
                    h1 = time.perf_counter()
                    C["first_leg_walks_hits"] += 1
                    _charge(h1)
                else:
                    _note_read("first_leg", lambda: leg_key(a, k, None))
                    _note_read("first_leg_r01", lambda: leg_key(a, k, 1))
        return _route_first_leg

    dose_args = ("leg", "walk_time_s", "first_segment", "time_s", "fed_rate_sampler", "config")

    def dose_key(a, k):
        # _first_leg_dose reads leg.length_m and leg.waypoints, walk_time_s, the first segment's
        # length_m and fed_growth, and the FED rate along the walk's excess prefix at time_s
        # (config is fixed within a run). The first segment's source and target are kept as
        # well; whether a sampler is given decides the branch.
        d = _bind(dose_args, a, k)
        leg, first = d["leg"], d["first_segment"]
        return (tuple(tuple(p) for p in leg.waypoints), leg.length_m, d["walk_time_s"],
                first.source, first.target, first.length_m, first.fed_growth,
                fed_frames(d["fed_rate_sampler"], d["time_s"]), d["fed_rate_sampler"] is None)

    def mk_dose(orig):
        def _first_leg_dose(*a, **k):
            try:
                return orig(*a, **k)
            finally:
                _note_read("first_leg_dose", lambda: dose_key(a, k))
        return _first_leg_dose

    def mk_gen(orig):
        def gen(graph, *a, **k):
            h0 = time.perf_counter()
            site = _scenario_site()
            n_edges = sum(len(v) for v in graph.edges.values())
            cached = k.get("cached_segments")
            p0 = _STATE.get("seg_p1", 0)
            _charge(h0)
            res = orig(graph, *a, **k)
            h1 = time.perf_counter()
            miss = _STATE.get("seg_p1", 0) - p0
            # Phase 1 visits every edge once: edges - evaluated = served from
            # the pass cache (all evaluated when no cache dict is passed).
            C[f"generate_candidates_calls[{site}]"] += 1
            C[f"generate_candidates_edges[{site}]"] += n_edges
            C[f"generate_candidates_segment_misses[{site}]"] += miss
            C[f"generate_candidates_segment_hits[{site}]"] += n_edges - miss
            if cached is None:
                C[f"generate_candidates_no_cache_dict[{site}]"] += 1
            _charge(h1)
            return res
        return gen

    def mk_polyline(orig):
        def polyline_stats(*a, **k):
            h0 = time.perf_counter()
            C["polyline_stats_calls"] += 1
            _charge(h0)
            return orig(*a, **k)
        return polyline_stats

    _wrap(rg_mod, "_polyline_stats", mk_polyline)
    _wrap(rg_mod, "evaluate_segment", mk_seg)
    _wrap(rg_mod, "_first_leg", mk_first_leg)
    _wrap(rg_mod, "_first_leg_dose", mk_dose)
    _wrap(rg_mod, "_cell_los_stats", _timed("cell_los_stats"))
    _wrap(rg_mod, "_step_los_stats", _timed("step_los_stats"))

    def mk_fed_rate(orig):
        timed = _timed("sample_fed_rate")(orig)

        def _route_fed_rate(self, time_s, x, y):
            try:
                return timed(self, time_s, x, y)
            finally:
                _note_read("sample_fed_rate", lambda: (
                    tuple(s._time_index(time_s) for s in fds_coverage.model_samplers(self._model)),
                    x, y))
        return _route_fed_rate

    _wrap(scen_mod._FedRateAdapter, "sample_fed_rate", mk_fed_rate)
    _wrap(rg_mod, "_generate_candidates", mk_gen)

    def mk_dist(orig):
        def distance_to_polygon(x, y, polygon):
            C["distance_to_polygon_calls"] += 1
            return orig(x, y, polygon)
        return distance_to_polygon

    def mk_reached(orig):
        def reached_stage(x, y, target, stage_cfg, agent_radius):
            cfg = stage_cfg or {}
            kind = cfg.get("stage_type", "checkpoint")
            poly = "polygon" if cfg.get("polygon") is not None else "no_polygon"
            C[f"reached_stage_calls[{kind}|{poly}]"] += 1
            return orig(x, y, target, stage_cfg, agent_radius)
        return reached_stage

    _wrap(dsr, "distance_to_polygon", mk_dist)
    _wrap(dsr, "reached_stage", mk_reached)
    if hasattr(scen_mod, "reached_stage"):
        scen_mod.reached_stage = dsr.reached_stage

    def mk_occ(orig):
        def occupied(*a, **k):
            res = orig(*a, **k)
            C["occupied_calls"] += 1
            C["occupied_agents"] += len(res[0])
            return res
        return occupied

    def mk_crowds(orig):
        def crowds(*a, **k):
            res = orig(*a, **k)
            C["crowds_agents_calls"] += 1
            C["crowds_agents_true"] += bool(res)
            return res
        return crowds

    def mk_defer(orig):
        def defer(deferred, source_id, time_s):
            C["flow_spawns_deferred_steps"] += 1
            return orig(deferred, source_id, time_s)
        return defer

    def mk_refuses(orig):
        def refuses(error):
            res = orig(error)
            C["add_agent_position_refusals_checked"] += 1
            C["add_agent_position_refusals"] += bool(res)
            return res
        return refuses

    _wrap(si, "_refuses_position", mk_refuses)
    if hasattr(scen_mod, "_refuses_position"):
        scen_mod._refuses_position = si._refuses_position
    _wrap(si, "_occupied", mk_occ)
    _wrap(si, "_crowds_agents", mk_crowds)
    _wrap(scen_mod, "_defer_flow_spawn", mk_defer)

    # Per-call cost of a route-path wrapper, from a no-op through the same _wrap and _timed.
    holder = types.SimpleNamespace(noop=lambda: None)
    _wrap(holder, "noop", _timed(_NOOP))
    for _ in range(NOOP_CALIBRATION_CALLS):
        holder.noop()
    for path in ROUTE_PATHS:
        RP[path]
    for path in ROUTE_KEYED:
        RP[path].setdefault("total", 0)


# --- install / dump ---------------------------------------------------------


def _hook_run_scenario(core_pkg, scen_mod):
    def mk(orig):
        def rs(*a, **k):
            t0 = time.perf_counter()
            res = orig(*a, **k)
            _STATE["run_scenario_s"] = time.perf_counter() - t0
            _STATE["run_scenario_t0"] = t0
            return res
        return rs
    _wrap(scen_mod, "run_scenario", mk)
    core_pkg.run_scenario = scen_mod.run_scenario


def dump(path: str) -> None:
    if _STATE["eval_pass_time"] is not None:
        PASS_SIZES[_STATE["eval_pass_n"]] += 1
        _STATE["eval_pass_time"] = None
    out = {
        "schema": "pyfds-evac perf counters v1",
        "dt_s": _STATE["dt"],
        "timers_s": {
            "method": "perf_counter in-process; diagnostic (counters run)",
            "run_scenario_total": _STATE.get("run_scenario_s"),
            "run_scenario_setup_before_first_iterate": (
                _STATE["loop_t0"] - _STATE["run_scenario_t0"]
                if _STATE.get("loop_t0") and _STATE.get("run_scenario_t0") else None),
            "loop_first_iterate_to_last_iterate_end": (
                _STATE["loop_t1"] - _STATE["loop_t0"] if _STATE.get("loop_t0") else None),
            "run_scenario_after_last_iterate": (
                _STATE["run_scenario_t0"] + _STATE["run_scenario_s"] - _STATE["loop_t1"]
                if _STATE.get("run_scenario_s") and _STATE.get("loop_t1") else None),
        },
        "counters": dict(sorted(C.items())),
        "bins_s": BIN_S,
        "binned": {k: dict(sorted(v.items())) for k, v in sorted(BINS.items())},
        "reroute_pass_sizes": {str(k): v for k, v in sorted(PASS_SIZES.items())},
        "events": dict(EVENTS),
        "exit_nodes": sorted(_EXIT_NODES),
        "detail": {
            "enabled": bool(os.environ.get("PYFDS_PERF_DETAIL")),
            "sampler_distinct_xy": {k: len(v) for k, v in sorted(_KEYS.items())},
        },
    }
    if RP:
        out["detail"]["route_paths"] = {p: _route_path_out(p) for p in sorted(RP) if p != _NOOP}
        out["detail"]["route_paths_overhead"] = {
            "noop_wrapper_calls": RP[_NOOP]["calls"],
            "noop_wrapper_seconds": RP[_NOOP]["seconds"]}
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


def install(out_path: str) -> None:
    import fdsreader.simulation as fds_sim_mod
    import jupedsim.simulation as jps_sim_mod

    import pyfds_evac.core as core_pkg
    from pyfds_evac.core import cognitive_map, route_graph, scenario, visibility

    _hook_fdsreader(fds_sim_mod)
    _hook_visibility(visibility)
    _hook_cognitive_map(cognitive_map, scenario)
    _hook_routing(route_graph, scenario)
    _hook_jupedsim(jps_sim_mod)
    _hook_run_scenario(core_pkg, scenario)
    if os.environ.get("PYFDS_PERF_DETAIL"):
        _hook_detail(route_graph, scenario)
    atexit.register(dump, out_path)
