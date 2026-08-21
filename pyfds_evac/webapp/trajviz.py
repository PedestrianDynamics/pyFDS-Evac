"""Lightweight canvas trajectory animator.

Plotly's frame animation stepped between coarse samples, so motion jumped. This
renders agent dots on a <canvas> and interpolates positions between downsampled
samples in a requestAnimationFrame loop, giving smooth 60fps playback from a
small payload. Geometry (walkable area, exits) is drawn once per frame.
"""

from __future__ import annotations

import base64
import bisect
import json
import math
from pathlib import Path
from typing import Any

from fasthtml.common import H3, Div, NotStr

from .plots import _PALETTE, _agent_exit_map

_CARD = (
    "background:var(--surface-card);border:1px solid var(--hairline);"
    "border-radius:1.1rem;padding:20px;box-shadow:var(--shadow-md)"
)

# Wall-clock gap between the position samples sent to the browser.  The JS
# draws a straight line between consecutive samples, so this gap sets how far
# an agent travels along a chord that ignores geometry.  A fixed sample
# *count* cannot bound that -- it makes the gap grow with run length, and at
# 120 samples a 600 s run was sampled every 5 s (6.5 m of travel), which drew
# agents straight through walls and vanished whole cohorts between frames.
#
# 0.1 s is the rate the trajectory is recorded at (dt=0.01 s, every 10th frame),
# so the browser is given the simulation's own positions and interpolates
# nothing that was not measured.
_SAMPLE_INTERVAL_S = 0.1
# Ceiling on the sample count, so a very long run degrades to a coarser gap
# rather than an unbounded payload.  Sized to let a typical run through at the
# full rate (a 600 s run is 6001 samples) and to bite only past that: 1200 s
# falls back to 0.2 s, 3600 s to 0.5 s, both still far finer than the wall
# thickness that matters.  At 333 agents a 600 s run is about 24 MB of JSON;
# the app is served locally, so that is parse time and memory, not transfer.
_MAX_SAMPLES = 8000
# Centimetre precision is finer than the canvas can show, and full float
# repr is pure payload.
_COORD_DP = 2

# Body radius to draw an agent at when the scenario configures none, matching
# the default `simulation_init` hands to JuPedSim.
_DEFAULT_AGENT_RADIUS_M = 0.2


# The extinction-coefficient slice quantity. Not to be confused with FDS's
# separate 'EXTINCTION' quantity, a 0/1/-1 combustion-suppression flag
# (User Guide Sec. 22.10.29) that is not a smoke value and must never be
# used as a fallback here.
_EXTINCTION_QUANTITIES = ("SOOT EXTINCTION COEFFICIENT",)

# Largest grid dimension shipped to the browser. The FDS slice is downsampled
# to at most this many cells on its long axis; canvas image-smoothing blurs the
# result so a coarse grid still looks like a continuous smoke field.
_SMOKE_MAX_CELLS = 70


def _smoke_payload(
    fds_dir: str | None, times: list[float], slice_height_m: float = 2.0
) -> dict | None:
    """Sample the FDS extinction slice onto a coarse grid for each render time.

    Returns a dict with the grid dimensions, world extent, per-frame extinction
    packed as base64 uint8 (scaled to ``kmax``), and ``kmax`` itself — or
    ``None`` when no FDS directory / extinction slice is available. Any failure
    is swallowed so the trajectory viewer never breaks on smoke rendering.
    """
    if not fds_dir or not Path(fds_dir).exists():
        return None
    try:
        import numpy as np
        from fdsreader import Simulation

        sim = Simulation(str(fds_dir))
        matches: list = []
        for quantity in _EXTINCTION_QUANTITIES:
            matches = list(sim.slices.filter_by_quantity(quantity))
            if matches:
                break
        if not matches:
            return None

        # Horizontal slice nearest the sampling height (agents' breathing zone).
        def _zmid(s: Any) -> float:
            return (s.extent.z_start + s.extent.z_end) / 2.0

        sl = min(matches, key=lambda s: abs(_zmid(s) - slice_height_m))
        grid, coords = sl.to_global(masked=True, return_coordinates=True)
        grid = np.nan_to_num(np.asarray(grid, dtype=float), nan=0.0)  # (T, X, Y)
        slice_times = np.asarray(sl.times, dtype=float)
        xs = np.asarray(coords["x"], dtype=float)
        ys = np.asarray(coords["y"], dtype=float)
        if grid.ndim != 3 or xs.size < 2 or ys.size < 2:
            return None

        n_x, n_y = grid.shape[1], grid.shape[2]
        step = max(1, int(np.ceil(max(n_x, n_y) / _SMOKE_MAX_CELLS)))
        grid = grid[:, ::step, ::step]
        xs = xs[::step]
        ys = ys[::step]
        w, h = grid.shape[1], grid.shape[2]

        kmax = float(grid.max())
        if kmax <= 0.0:
            kmax = 1.0  # uniform-clear field: keep a valid scale, layer is blank

        # One uint8 frame per render time, using the nearest FDS timestep.
        # Bytes are row-major over (x, y): index = ix * h + iy.
        buf = bytearray()
        for t in times:
            ti = int(np.argmin(np.abs(slice_times - float(t))))
            frame = grid[ti]
            u8 = np.clip(frame / kmax * 255.0, 0, 255).astype(np.uint8)
            buf += u8.tobytes()

        # xs/ys are cell-CENTRE coords, but the drawn image maps its pixel
        # EDGES to the extent rectangle. Expand by half a (downsampled) cell so
        # pixel edges line up with the geometry instead of cell centres —
        # removes the half-cell gaps/overlaps at the map edges.
        csx = (xs[-1] - xs[0]) / (w - 1) if w > 1 else 1.0
        csy = (ys[-1] - ys[0]) / (h - 1) if h > 1 else 1.0
        return {
            "W": int(w),
            "H": int(h),
            "ext": [
                float(xs[0] - csx / 2.0),
                float(ys[0] - csy / 2.0),
                float(xs[-1] + csx / 2.0),
                float(ys[-1] + csy / 2.0),
            ],
            "kmax": kmax,
            "b64": base64.b64encode(bytes(buf)).decode("ascii"),
        }
    except Exception:
        return None


def _interior_walls(*polys) -> list[list[list[float]]]:
    """Interior rings (holes = walls/obstacles) of the walkable geometry.

    Tries each candidate polygon in order and returns the rings from the first
    that has any — the JuPedSim sqlite may drop holes, so the scenario's own
    walkable polygon is the more reliable source.
    """
    for poly in polys:
        if poly is None:
            continue
        rings: list[list[list[float]]] = []
        try:
            geoms = list(getattr(poly, "geoms", [])) or [poly]
            for g in geoms:
                for ring in getattr(g, "interiors", []):
                    rx, ry = ring.xy
                    rings.append([[float(x), float(y)] for x, y in zip(rx, ry)])
        except Exception:
            rings = []
        if rings:
            return rings
    return []


def _bounds(walkable, data) -> list[float]:
    try:
        minx, miny, maxx, maxy = walkable.polygon.bounds
        return [float(minx), float(miny), float(maxx), float(maxy)]
    except Exception:
        return [
            float(data["x"].min()),
            float(data["y"].min()),
            float(data["x"].max()),
            float(data["y"].max()),
        ]


def _agent_radius_m(scenario: Any) -> float:
    """Mean configured agent body radius, in metres.

    The viewer draws agents at their real size, so it needs the radius the
    solver used. ``ScenarioResult`` does not carry it and the JuPedSim sqlite
    stores no per-agent geometry, so it is read back off the scenario exactly
    the way ``simulation_init`` reads it: from each distribution's parameters,
    which may arrive as a JSON string. Per-agent sampled radii are not
    recoverable here, so a mixed-radius crowd draws at its mean.
    """
    raw = getattr(scenario, "raw", None) or {}
    dists = raw.get("distributions") or {}
    if not isinstance(dists, dict):
        return _DEFAULT_AGENT_RADIUS_M
    radii: list[float] = []
    for dist in dists.values():
        params = dist.get("parameters") if isinstance(dist, dict) else None
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except ValueError:
                continue
        if not isinstance(params, dict):
            continue
        try:
            r = float(params["radius"])
        except (KeyError, TypeError, ValueError):
            continue
        if r > 0:
            radii.append(r)
    return sum(radii) / len(radii) if radii else _DEFAULT_AGENT_RADIUS_M


def _payload(result: Any, scenario: Any, fds_dir: str | None = None) -> dict | None:
    if not result.sqlite_file or not Path(result.sqlite_file).exists():
        return None

    import pedpy

    sqlite = Path(result.sqlite_file)
    traj = pedpy.load_trajectory_from_jupedsim_sqlite(trajectory_file=sqlite)
    walkable = pedpy.load_walkable_area_from_jupedsim_sqlite(trajectory_file=sqlite)
    data = traj.data
    fps = float(getattr(traj, "frame_rate", 0) or 1.0)

    agent_exit = _agent_exit_map(result.route_cost_history)
    exits_seen = sorted(set(agent_exit.values()))
    color_of = {ex: _PALETTE[i % len(_PALETTE)] for i, ex in enumerate(exits_seen)}
    agent_ids = sorted(int(a) for a in data["id"].unique())
    colors = [color_of.get(agent_exit.get(a, ""), "#ff6a1a") for a in agent_ids]

    frames_all = sorted(data["frame"].unique())
    # Sample on a fixed wall-clock gap, not a fixed count, so playback fidelity
    # does not decay as runs get longer. The cap only binds on runs long enough
    # that _SAMPLE_INTERVAL_S would blow the payload budget.
    step = max(1, round(_SAMPLE_INTERVAL_S * fps))
    if len(frames_all) // step > _MAX_SAMPLES:
        step = math.ceil(len(frames_all) / _MAX_SAMPLES)
    sampled = frames_all[::step]
    # Per-agent tracks, not a full agent-by-sample grid.  An agent exists from
    # its spawn to the moment it reaches an exit, so a grid spends a slot on
    # every agent that has not spawned yet or has already left: on a 600 s
    # station_fahy run only 4.9 % of the grid holds a position and the other
    # 95.1 % is the word "null".  Each agent instead carries the index of its
    # first sample and a flat run of coordinates from there.
    times = [round(f / fps, 2) for f in sampled]
    # One pass over the rows rather than a groupby per sampled frame, which
    # builds a DataFrame for each of the thousands of samples.
    sample_of_frame = {f: t for t, f in enumerate(sampled)}
    positions_by_sample: list[dict[int, tuple[float, float]]] = [{} for _ in sampled]
    for i, f, x, y in zip(data["id"], data["frame"], data["x"], data["y"]):
        t = sample_of_frame.get(f)
        if t is None:
            continue
        positions_by_sample[t][int(i)] = (
            round(float(x), _COORD_DP),
            round(float(y), _COORD_DP),
        )

    # One pass over the recorded positions, not one scan of every sample per
    # agent, which would be agents x samples work for a payload this shape.
    start_of: dict[int, int] = {}
    track_of: dict[int, list[Any]] = {a: [] for a in agent_ids}
    for t, pos in enumerate(positions_by_sample):
        for a, xy in pos.items():
            flat = track_of.get(a)
            if flat is None:
                continue
            if a not in start_of:
                start_of[a] = t
            # Pad any gap (the writer does not produce one, but tolerating it
            # costs nothing) so index k always means sample starts[i] + k.
            expected = (t - start_of[a]) * 2
            if len(flat) < expected:
                flat.extend([None] * (expected - len(flat)))
            flat.append(xy[0])
            flat.append(xy[1])
    starts = [start_of.get(a, -1) for a in agent_ids]
    tracks = [track_of[a] for a in agent_ids]

    # Per-agent cumulative FED at each sample time, aligned with `samples`.
    # FED is a step function in time; we take the last value at or before the
    # sample time. None where the agent is absent from that frame.
    fed_t: dict[int, list[float]] = {}
    fed_v: dict[int, list[float]] = {}
    pairs: dict[int, list[tuple[float, float]]] = {}
    for row in result.fed_history or []:
        try:
            pairs.setdefault(int(row["agent_id"]), []).append(
                (float(row["time_s"]), float(row["fed_cumulative"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    for aid, seq in pairs.items():
        seq.sort()
        fed_t[aid] = [p[0] for p in seq]
        fed_v[aid] = [p[1] for p in seq]
    has_fed = bool(fed_t)

    def _fed_at(aid: int, ts: float) -> float:
        ts_list = fed_t.get(aid)
        if not ts_list:
            return 0.0
        j = bisect.bisect_right(ts_list, ts) - 1
        return fed_v[aid][j] if j >= 0 else 0.0

    # Aligned with `tracks`: one value per agent per sample it is present for,
    # starting at the same `starts[i]`.  Every read of it in the JS sits behind
    # a hasFed guard, so without a FED model it is not built at all rather than
    # shipping a second payload of zeros.
    fed_tracks: list[list[Any]] = []
    if has_fed:
        for i, a in enumerate(agent_ids):
            first = starts[i]
            if first < 0:
                fed_tracks.append([])
                continue
            n_samples = len(tracks[i]) // 2
            fed_tracks.append(
                [
                    _fed_at(a, times[first + k])
                    if a in positions_by_sample[first + k]
                    else None
                    for k in range(n_samples)
                ]
            )

    try:
        wx, wy = walkable.polygon.exterior.xy
        walk = [[float(x), float(y)] for x, y in zip(wx, wy)]
    except Exception:
        walk = []

    exits = []
    for exit_id, edata in (scenario.raw.get("exits") or {}).items() if scenario else []:
        coords = edata.get("coordinates") or []
        if coords:
            exits.append(
                {
                    "poly": [[float(c[0]), float(c[1])] for c in coords],
                    "color": color_of.get(exit_id, "#ff6a1a"),
                    "label": exit_id.replace("_", " "),
                }
            )

    return {
        "times": times,
        "starts": starts,
        "tracks": tracks,
        "colors": colors,
        "fed": fed_tracks,
        "hasFed": has_fed,
        "walk": walk,
        "walls": _interior_walls(
            getattr(scenario, "walkable_polygon", None) if scenario else None,
            getattr(walkable, "polygon", None),
        ),
        "exits": exits,
        "agentR": round(_agent_radius_m(scenario), 3),
        "bounds": _bounds(walkable, data),
        "smoke": _smoke_payload(fds_dir, times),
    }


_JS = """
(function () {
  var D = __DATA__;
  var canvas = document.getElementById('traj-canvas');
  if (!canvas || !D.times.length) return;
  var playBtn = document.getElementById('traj-play');
  var slider = document.getElementById('traj-slider');
  var tlabel = document.getElementById('traj-time');
  var ctx = canvas.getContext('2d');
  var T = D.times, ST = D.starts, TR = D.tracks, COL = D.colors, FED = D.fed,
      n = COL.length;
  // Agents carry their own track from ST[i], so a lookup is a bounds check
  // rather than an index into a grid mostly full of nulls. Returns null when
  // agent i had not spawned yet, or had already left, at sample ti.
  function posAt(i, ti) {
    var k = ti - ST[i];
    if (ST[i] < 0 || k < 0) return null;
    var tr = TR[i], j = 2 * k;
    if (j + 1 >= tr.length || tr[j] == null) return null;
    return [tr[j], tr[j + 1]];
  }
  function fedAt(i, ti) {
    var k = ti - ST[i];
    if (ST[i] < 0 || k < 0) return null;
    var fr = FED[i];
    if (!fr || k >= fr.length) return null;
    return fr[k];
  }
  var t0 = T[0], t1 = T[T.length - 1], span = Math.max(1e-6, t1 - t0);
  var simT = t0, playing = false, lastTs = null;
  var speedMult = 1;            // 1x = real time: 1 sim-second per wall-second
  var bx = D.bounds, pad = 0.06;
  var mode = D.hasFed ? 'fed' : 'exit';
  var zoom = 1, panX = 0, panY = 0, MIN_ZOOM = 0.5, MAX_ZOOM = 20;
  // Agent body radius in metres, drawn to scale with the geometry.  The floor
  // is a visibility backstop only: on a plan hundreds of metres across a
  // 0.2 m agent is sub-pixel when zoomed out, and a dot that rounds away
  // entirely reads as a lost agent rather than a small one.
  var AGENT_R = D.agentR > 0 ? D.agentR : 0.2, MIN_AGENT_PX = 2;

  // ---- theme ----------------------------------------------------------
  // Canvas takes literal colours only. TH is refreshed whenever the page
  // theme flips (see window.trajRepaint at the foot of this script), so a
  // light-mode reader gets dark geometry on paper rather than white-on-white.
  var TH = {};
  function readTheme() {
    var light = document.documentElement.getAttribute('data-theme') === 'light';
    TH.light      = light;
    TH.walkFill   = light ? 'rgba(31,23,16,0.035)' : 'rgba(255,255,255,0.03)';
    TH.walkLine   = light ? 'rgba(31,23,16,0.22)'  : 'rgba(255,255,255,0.16)';
    TH.wallFill   = light ? '#d9d2c8'              : '#14161b';
    TH.wallLine   = light ? 'rgba(31,23,16,0.38)'  : 'rgba(255,255,255,0.34)';
    TH.agentRing  = light ? 'rgba(31,23,16,0.35)'  : 'rgba(0,0,0,0.45)';
    TH.sparkLine  = light ? 'rgba(31,23,16,.55)'   : 'rgba(255,255,255,.55)';
    TH.noData     = light ? '#6f665e'              : '#9aa0a6';
    // Smoke is drawn as raw RGBA bytes: pale grey reads on the dark ground,
    // but on paper it has to darken instead or it vanishes.
    TH.smokeRGB   = light ? [90, 88, 100] : [205, 203, 214];
  }
  readTheme();

  var CANVAS_H = 440;           // render height; size() and the wheel handler must agree
  var dragging = false, dragStart = null;

  // Smoke field: decode base64 uint8 frames into an offscreen canvas we can
  // scale onto the main canvas under the agents. Each frame is W*H bytes,
  // row-major over (x, y): byte at ix*H + iy holds K scaled to 0..255 of kmax.
  var SM = D.smoke, smBytes = null, smCanvas = null, smCtx = null;
  var showSmoke = !!SM;
  if (SM) {
    var raw = atob(SM.b64);
    smBytes = new Uint8Array(raw.length);
    for (var si = 0; si < raw.length; si++) smBytes[si] = raw.charCodeAt(si);
    smCanvas = document.createElement('canvas');
    smCanvas.width = SM.W; smCanvas.height = SM.H;
    smCtx = smCanvas.getContext('2d');
  }
  function drawSmoke(fi, p) {
    if (!SM || !showSmoke || !smBytes) return;
    var W = SM.W, H = SM.H, off = fi * W * H, kmax = SM.kmax;
    var id = smCtx.createImageData(W, H);
    var d = id.data;
    for (var ix = 0; ix < W; ix++) {
      for (var iy = 0; iy < H; iy++) {
        var K = (smBytes[off + ix * H + iy] / 255) * kmax;
        var a = 1 - Math.exp(-K * 0.6);      // Beer-Lambert-ish opacity
        if (a > 0.9) a = 0.9;                 // keep agents visible through it
        var pi = ((H - 1 - iy) * W + ix) * 4; // flip y: world +y is screen up
        d[pi] = TH.smokeRGB[0]; d[pi + 1] = TH.smokeRGB[1]; d[pi + 2] = TH.smokeRGB[2];
        d[pi + 3] = Math.round(a * 255);
      }
    }
    smCtx.putImageData(id, 0, 0);
    var tl = p(SM.ext[0], SM.ext[3]);          // world (xmin, ymax) -> top-left
    var br = p(SM.ext[2], SM.ext[1]);          // world (xmax, ymin) -> bot-right
    ctx.imageSmoothingEnabled = true;
    // Clip to the walkable area so smoke never bleeds outside the geometry
    // (the FDS domain is a bounding box larger than the walkable polygon).
    var clipped = false;
    if (D.walk.length) {
      ctx.save();
      ctx.beginPath();
      for (var i = 0; i < D.walk.length; i++) {
        var q = p(D.walk[i][0], D.walk[i][1]);
        i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]);
      }
      ctx.closePath();
      ctx.clip();
      clipped = true;
    }
    ctx.drawImage(smCanvas, tl[0], tl[1], br[0] - tl[0], br[1] - tl[1]);
    if (clipped) ctx.restore();
  }

  // Pre-compute per-sample FED statistics for the panel
  var fedMaxByTime = null, fedMeanByTime = null;
  if (D.hasFed) {
    fedMaxByTime = T.map(function (_, ti) {
      var m = 0;
      for (var k = 0; k < n; k++) {
        var v = fedAt(k, ti);
        if (v != null && v > m) m = v;
      }
      return m;
    });
    fedMeanByTime = T.map(function (_, ti) {
      var s = 0, c = 0;
      for (var k = 0; k < n; k++) {
        var v = fedAt(k, ti);
        if (v != null) { s += v; c++; }
      }
      return c > 0 ? s / c : 0;
    });
  }

  // FED dose -> tier colour (green -> amber -> orange -> red).
  var STOPS = [[0, '#f4c430'], [0.3, '#ffb020'], [0.6, '#ff6a1a'], [1, '#e01e37']];
  function lerpHex(a, b, t) {
    var ar = parseInt(a.slice(1, 3), 16), ag = parseInt(a.slice(3, 5), 16),
        ab = parseInt(a.slice(5, 7), 16);
    var br = parseInt(b.slice(1, 3), 16), bg = parseInt(b.slice(3, 5), 16),
        bb = parseInt(b.slice(5, 7), 16);
    var r = Math.round(ar + (br - ar) * t), g = Math.round(ag + (bg - ag) * t),
        bl = Math.round(ab + (bb - ab) * t);
    return 'rgb(' + r + ',' + g + ',' + bl + ')';
  }
  function fedColor(d) {
    if (d == null) return TH.noData;
    if (d <= 0) return STOPS[0][1];
    if (d >= 1) return STOPS[STOPS.length - 1][1];
    for (var k = 1; k < STOPS.length; k++) {
      if (d <= STOPS[k][0]) {
        return lerpHex(STOPS[k - 1][1], STOPS[k][1],
          (d - STOPS[k - 1][0]) / (STOPS[k][0] - STOPS[k - 1][0]));
      }
    }
    return STOPS[STOPS.length - 1][1];
  }

  function size() {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 600, h = CANVAS_H;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return [w, h];
  }
  function baseTf(w, h) {
    var dx = bx[2] - bx[0] || 1, dy = bx[3] - bx[1] || 1;
    var mw = w * (1 - 2 * pad), mh = h * (1 - 2 * pad);
    var s = Math.min(mw / dx, mh / dy);
    var ox = (w - s * dx) / 2 - s * bx[0];
    var oy = (h - s * dy) / 2 - s * bx[1];
    var f = function (x, y) { return [ox + s * x, h - (oy + s * y)]; };  // flip y
    f.s = s;                      // px per world metre, before user zoom
    return f;
  }
  // Fit-to-bounds transform, then user zoom/pan applied on top around the
  // canvas centre so scroll-to-zoom and drag-to-pan work independent of the
  // world extent.  `.s` rides along so anything sized in world units (the
  // agents) can be drawn at the same scale as the geometry.
  function tf(w, h) {
    var base = baseTf(w, h), cx = w / 2, cy = h / 2;
    var f = function (x, y) {
      var q = base(x, y);
      return [(q[0] - cx) * zoom + cx + panX, (q[1] - cy) * zoom + cy + panY];
    };
    f.s = base.s * zoom;          // px per world metre at the current zoom
    return f;
  }
  function poly(P, p, fill, stroke, lw) {
    if (!P.length) return;
    ctx.beginPath();
    for (var i = 0; i < P.length; i++) {
      var q = p(P[i][0], P[i][1]);
      i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]);
    }
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.stroke(); }
  }
  function bracket(t) {
    if (t <= T[0]) return [0, 0, 0];
    if (t >= T[T.length - 1]) return [T.length - 1, T.length - 1, 0];
    var lo = 0, hi = T.length - 1;
    while (hi - lo > 1) { var m = (lo + hi) >> 1; if (T[m] <= t) lo = m; else hi = m; }
    var f = (t - T[lo]) / Math.max(1e-9, T[hi] - T[lo]);
    return [lo, hi, f];
  }
  function drawFedPanel() {
    if (!D.hasFed || !fedMaxByTime) return;
    var b = bracket(simT), lo = b[0], hi = b[1], f = b[2];
    var curMax  = fedMaxByTime[lo]  + (fedMaxByTime[hi]  - fedMaxByTime[lo])  * f;
    var curMean = fedMeanByTime[lo] + (fedMeanByTime[hi] - fedMeanByTime[lo]) * f;
    function fc(v) { return v >= 1.0 ? '#E01E37' : v >= 0.6 ? '#FF6A1A' : v >= 0.3 ? '#FFB020' : '#F4C430'; }
    var maxEl = document.getElementById('fed-val-max');
    if (maxEl) { maxEl.textContent = curMax.toFixed(4); maxEl.style.color = fc(curMax); }
    var meanEl = document.getElementById('fed-val-mean');
    if (meanEl) { meanEl.textContent = curMean.toFixed(4); meanEl.style.color = fc(curMean); }
    var barEl = document.getElementById('fed-bar-fill');
    if (barEl) barEl.style.width = Math.min(100, curMax * 100) + '%';
    var sc = document.getElementById('fed-spark');
    if (!sc) return;
    var dpr = window.devicePixelRatio || 1;
    var sw = sc.clientWidth, sh = sc.clientHeight;
    if (!sw || !sh) return;
    sc.width = sw * dpr; sc.height = sh * dpr;
    var sctx = sc.getContext('2d');
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sctx.clearRect(0, 0, sw, sh);
    var N = fedMaxByTime.length;
    var maxV = 0;
    for (var i = 0; i < N; i++) { if (fedMaxByTime[i] > maxV) maxV = fedMaxByTime[i]; }
    maxV = Math.max(1.05, maxV * 1.12);
    function px(i) { return N > 1 ? (i / (N - 1)) * sw : sw / 2; }
    function py(v) { return sh - (v / maxV) * (sh - 2); }
    var grad = sctx.createLinearGradient(0, 0, 0, sh);
    grad.addColorStop(0, 'rgba(244,196,48,.22)');
    grad.addColorStop(1, 'rgba(244,196,48,0)');
    sctx.beginPath();
    sctx.moveTo(px(0), sh);
    for (var i = 0; i < N; i++) sctx.lineTo(px(i), py(fedMaxByTime[i]));
    sctx.lineTo(px(N - 1), sh); sctx.closePath();
    sctx.fillStyle = grad; sctx.fill();
    sctx.beginPath();
    for (var i = 0; i < N; i++) { i === 0 ? sctx.moveTo(px(i), py(fedMaxByTime[i])) : sctx.lineTo(px(i), py(fedMaxByTime[i])); }
    sctx.strokeStyle = '#F4C430'; sctx.lineWidth = 1.5; sctx.stroke();
    sctx.beginPath();
    for (var i = 0; i < N; i++) { i === 0 ? sctx.moveTo(px(i), py(fedMeanByTime[i])) : sctx.lineTo(px(i), py(fedMeanByTime[i])); }
    sctx.strokeStyle = 'rgba(255,138,61,.7)'; sctx.lineWidth = 1;
    sctx.setLineDash([3, 3]); sctx.stroke(); sctx.setLineDash([]);
    var threshs = [[0.3, 'rgba(255,176,32,.55)', '0.3'], [1.0, 'rgba(224,30,55,.55)', '1.0']];
    for (var ti2 = 0; ti2 < threshs.length; ti2++) {
      var ty = py(threshs[ti2][0]);
      if (ty >= 0 && ty <= sh) {
        sctx.beginPath(); sctx.moveTo(0, ty); sctx.lineTo(sw, ty);
        sctx.strokeStyle = threshs[ti2][1]; sctx.lineWidth = 1;
        sctx.setLineDash([4, 4]); sctx.stroke(); sctx.setLineDash([]);
        sctx.fillStyle = threshs[ti2][1]; sctx.font = '9px JetBrains Mono, monospace';
        sctx.textAlign = 'right'; sctx.fillText(threshs[ti2][2], sw - 3, ty - 3); sctx.textAlign = 'left';
      }
    }
    var curFrac = T.length > 1 ? (simT - T[0]) / (T[T.length - 1] - T[0]) : 0;
    var cx = Math.max(0, Math.min(sw, curFrac * sw));
    sctx.beginPath(); sctx.moveTo(cx, 0); sctx.lineTo(cx, sh);
    sctx.strokeStyle = TH.sparkLine; sctx.lineWidth = 1.5; sctx.stroke();
    sctx.beginPath(); sctx.arc(cx, py(curMax), 3.5, 0, 6.2832);
    sctx.fillStyle = fc(curMax); sctx.fill();
  }
  function draw() {
    var d = size(), w = d[0], h = d[1], p = tf(w, h);
    ctx.clearRect(0, 0, w, h);
    poly(D.walk, p, TH.walkFill, TH.walkLine, 1.5);
    var b = bracket(simT), f = b[2];
    drawSmoke(b[0], p);
    // Interior walls (holes in the walkable area): drawn over the smoke as
    // solid voids so they read as obstacles the agents route around.
    if (D.walls) {
      for (var wI = 0; wI < D.walls.length; wI++) {
        poly(D.walls[wI], p, TH.wallFill, TH.wallLine, 1.4);
      }
    }
    D.exits.forEach(function (e) {
      poly(e.poly, p, e.color + '28', e.color, 2);
    });
    // One radius for the whole frame: agents are all the same size, and it is
    // the map scale, not the agent, that changes between frames.
    var rpx = Math.max(MIN_AGENT_PX, AGENT_R * p.s);
    var rlw = Math.max(0.5, Math.min(1.6, rpx * 0.16));
    for (var i = 0; i < n; i++) {
      var pa = posAt(i, b[0]), pc = posAt(i, b[1]);
      var X, Y;
      if (pa == null && pc == null) continue;
      else if (pa == null) { X = pc[0]; Y = pc[1]; }
      else if (pc == null) { X = pa[0]; Y = pa[1]; }
      else { X = pa[0] + (pc[0] - pa[0]) * f; Y = pa[1] + (pc[1] - pa[1]) * f; }
      var col = COL[i];
      if (mode === 'fed') {
        var da = fedAt(i, b[0]), dc = fedAt(i, b[1]), dv;
        if (da == null) dv = dc; else if (dc == null) dv = da;
        else dv = da + (dc - da) * f;
        col = fedColor(dv);
      }
      var q = p(X, Y);
      ctx.beginPath(); ctx.arc(q[0], q[1], rpx, 0, 6.2832);
      ctx.fillStyle = col; ctx.fill();
      ctx.lineWidth = rlw; ctx.strokeStyle = TH.agentRing; ctx.stroke();
    }
    tlabel.textContent = 't = ' + (simT - t0).toFixed(0) + ' s';
    slider.value = String(((simT - t0) / span) * 1000);
    if (D.hasFed) drawFedPanel();
  }
  // A stalled tab or a frame that took too long to render must not let simT
  // leap past what was actually recorded: the wall-clock gap between two
  // rAF callbacks is capped at one sample interval (0.1 s) before it is
  // applied, so a late callback plays back slow rather than skipping the
  // steps in between -- the same 0.1 s granularity the data was sampled at.
  var _RAF_DT_CAP_S = 0.1;
  function loop(ts) {
    if (playing) {
      if (lastTs != null) {
        var dt = Math.min((ts - lastTs) / 1000, _RAF_DT_CAP_S);
        simT += dt * speedMult;
      }
      lastTs = ts;
      if (simT >= t1) { simT = t1; playing = false; playBtn.textContent = '▶'; }
    }
    draw();
    requestAnimationFrame(loop);
  }
  playBtn.addEventListener('click', function () {
    if (simT >= t1) simT = t0;
    playing = !playing; lastTs = null;
    playBtn.textContent = playing ? '❚❚' : '▶';
  });
  slider.addEventListener('input', function () {
    playing = false; playBtn.textContent = '▶';
    simT = t0 + (parseFloat(slider.value) / 1000) * span;
  });
  var customInput = document.getElementById('traj-speed-custom');
  document.querySelectorAll('.speed-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      speedMult = parseFloat(this.dataset.speed);
      document.querySelectorAll('.speed-btn').forEach(function (b) {
        b.classList.toggle('active', b === btn);
      });
      if (customInput) customInput.classList.remove('active');
    });
  });
  if (customInput) {
    var applyCustomSpeed = function () {
      var v = parseFloat(customInput.value);
      if (!isFinite(v) || v <= 0) return;
      speedMult = v;
      document.querySelectorAll('.speed-btn').forEach(function (b) { b.classList.remove('active'); });
      customInput.classList.add('active');
    };
    customInput.addEventListener('change', applyCustomSpeed);
    customInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') applyCustomSpeed(); });
  }
  // Scroll to zoom (centred on the cursor), drag to pan.
  canvas.addEventListener('wheel', function (e) {
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left, my = e.clientY - rect.top;
    var w = canvas.clientWidth || 600, h = CANVAS_H, cx = w / 2, cy = h / 2;
    var worldX = (mx - cx - panX) / zoom + cx;
    var worldY = (my - cy - panY) / zoom + cy;
    var newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    panX = mx - cx - (worldX - cx) * newZoom;
    panY = my - cy - (worldY - cy) * newZoom;
    zoom = newZoom;
  }, { passive: false });
  canvas.addEventListener('mousedown', function (e) {
    dragging = true;
    dragStart = { x: e.clientX, y: e.clientY, panX: panX, panY: panY };
    canvas.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    panX = dragStart.panX + (e.clientX - dragStart.x);
    panY = dragStart.panY + (e.clientY - dragStart.y);
  });
  window.addEventListener('mouseup', function () {
    if (!dragging) return;
    dragging = false;
    canvas.style.cursor = 'grab';
  });
  canvas.style.cursor = 'grab';
  var resetViewBtn = document.getElementById('traj-reset-view');
  if (resetViewBtn) {
    resetViewBtn.addEventListener('click', function () { zoom = 1; panX = 0; panY = 0; });
  }
  var smBtn = document.getElementById('traj-smoke');
  if (smBtn) {
    smBtn.addEventListener('click', function () {
      showSmoke = !showSmoke;
      smBtn.classList.toggle('active', showSmoke);
      draw();
    });
  }
  var bf = document.getElementById('traj-mode-fed');
  var be = document.getElementById('traj-mode-exit');
  if (bf && be) {
    bf.addEventListener('click', function () {
      mode = 'fed'; bf.classList.add('active'); be.classList.remove('active');
    });
    be.addEventListener('click', function () {
      mode = 'exit'; be.classList.add('active'); bf.classList.remove('active');
    });
  }
  window.addEventListener('resize', draw);

  // Called by the footer theme switch. Nothing here is reachable from CSS:
  // the geometry, the smoke bitmap and the FED sparkline are all painted
  // into a canvas with literal colours, so they need an explicit repaint.
  window.trajRepaint = function () {
    readTheme();
    draw();
    if (typeof drawFedPanel === 'function') drawFedPanel();
  };

  draw();
  requestAnimationFrame(loop);
})();
"""


def trajectory_component(result: Any, scenario: Any, fds_dir: str | None = None) -> Any:
    """A Card with a canvas trajectory animation (smooth interpolated playback)."""
    payload = _payload(result, scenario, fds_dir)
    if payload is None:
        return Div(
            H3(
                "Trajectories",
                style="font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:16px;margin:0 0 10px;color:var(--ink)",
            ),
            NotStr(
                '<p style="font-size:.85rem;color:var(--ink-dim)">Trajectory data unavailable.</p>'
            ),
            style=_CARD,
        )
    data_json = json.dumps(payload)
    toggle = ""
    if payload["hasFed"]:
        toggle = (
            '<div class="traj-color">'
            '<span class="traj-color-lbl">colour</span>'
            '<button id="traj-mode-fed" type="button" class="cmode active">FED</button>'
            '<button id="traj-mode-exit" type="button" class="cmode">exit</button>'
            "</div>"
        )
    if payload.get("smoke"):
        toggle += (
            '<div class="traj-color">'
            '<span class="traj-color-lbl">smoke</span>'
            '<button id="traj-smoke" type="button" class="cmode active">on</button>'
            "</div>"
        )
    markup = (
        '<div class="traj-wrap">'
        '<canvas id="traj-canvas" class="traj-canvas" title="Scroll to zoom, drag to pan"></canvas>'
        '<div class="traj-controls">'
        '<button id="traj-play" type="button" class="traj-play">▶</button>'
        '<input id="traj-slider" type="range" min="0" max="1000" value="0" '
        'class="traj-slider">'
        '<span id="traj-time" class="traj-time">t = 0 s</span>'
        '<button id="traj-reset-view" type="button" class="traj-play" title="Reset zoom/pan" style="font-size:.85rem">&#8634;</button>'
        '<div class="traj-color">'
        '<span class="traj-color-lbl">speed</span>'
        '<button type="button" class="cmode speed-btn active" data-speed="1">1&times;</button>'
        '<button type="button" class="cmode speed-btn" data-speed="2">2&times;</button>'
        '<button type="button" class="cmode speed-btn" data-speed="5">5&times;</button>'
        '<button type="button" class="cmode speed-btn" data-speed="10">10&times;</button>'
        '<button type="button" class="cmode speed-btn" data-speed="50">50&times;</button>'
        '<input id="traj-speed-custom" type="number" step="0.1" min="0.05" '
        'placeholder="custom" class="speed-custom" title="Custom speed multiplier">'
        "</div>"
        + toggle
        + "</div>"
        + (
            payload["hasFed"]
            and (
                '<div id="fed-panel" style="margin-top:14px;background:var(--surface-panel);border:1px solid var(--hairline);border-radius:12px;padding:14px 16px">'
                '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-faint)">FED Dose</span>'
                '<div style="display:flex;gap:12px">'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#F4C430">· safe</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#FFB020">· alert 0.3</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#FF6A1A">· critical 0.6</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#E01E37">· severe 1.0</span>'
                "</div></div>"
                '<div style="display:flex;align-items:baseline;gap:24px;margin-bottom:12px">'
                '<div><div style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:2px">max</div>'
                '<div id="fed-val-max" style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:26px;font-weight:500;color:#F4C430;transition:color .3s">0.0000</div></div>'
                '<div><div style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:2px">mean</div>'
                '<div id="fed-val-mean" style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:26px;font-weight:500;color:#FF8A3D;transition:color .3s">0.0000</div></div>'
                "</div>"
                '<div style="position:relative;height:6px;border-radius:99px;background:var(--surface-card);border:1px solid var(--hairline);overflow:hidden;margin-bottom:4px">'
                '<div id="fed-bar-fill" style="position:absolute;inset:0;width:0%;border-radius:99px;background:linear-gradient(90deg,#F4C430,#FFB020,#FF6A1A,#E01E37);transition:width .15s"></div>'
                "</div>"
                '<div style="display:flex;justify-content:space-between;margin-bottom:10px">'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:var(--ink-faint)">0</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#FFB020">0.3</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#FF6A1A">0.6</span>'
                '<span style="font-family:'
                + "'JetBrains Mono'"
                + ',monospace;font-size:9px;color:#E01E37">1.0+</span>'
                "</div>"
                '<canvas id="fed-spark" style="width:100%;height:60px;display:block"></canvas>'
                "</div>"
            )
            or ""
        )
        + "</div>"
    )
    script = "<script>" + _JS.replace("__DATA__", data_json) + "</script>"
    return Div(
        Div(
            H3(
                "Trajectories",
                style="font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:16px;margin:0;color:var(--ink)",
            ),
            style="display:flex;align-items:center;margin-bottom:14px",
        ),
        NotStr(markup + script),
        style=_CARD,
    )
