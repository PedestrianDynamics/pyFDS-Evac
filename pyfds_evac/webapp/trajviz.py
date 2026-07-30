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
from pathlib import Path
from typing import Any

from fasthtml.common import NotStr

from .plots import _PALETTE, _agent_exit_map

# Number of position samples sent to the browser; the JS interpolates between
# them, so this stays small while playback stays smooth.
_N_SAMPLES = 120

# Extinction-slice quantity names, in preference order. FDS names the soot
# extinction coefficient differently across cases ("SOOT EXTINCTION
# COEFFICIENT" in newer decks, bare "EXTINCTION" in older ones). This mirrors
# load_slice_sampler's multi-name lookup, but _smoke_payload samples the raw
# grid via to_global() rather than a SliceFieldSampler, so it filters inline.
_EXTINCTION_QUANTITIES = ("SOOT EXTINCTION COEFFICIENT", "EXTINCTION")

# Largest grid dimension shipped to the browser. The FDS slice is downsampled
# to at most this many cells on its long axis; canvas image-smoothing blurs the
# result so a coarse grid still looks like a continuous smoke field.
_SMOKE_MAX_CELLS = 70


def _smoke_payload(
    fds_dir: str | None,
    times: list[float],
    slice_height_m: float = 2.0,
    simulation: Any = None,
) -> dict | None:
    """Sample the FDS extinction slice onto a coarse grid for each render time.

    Returns a dict with the grid dimensions, world extent, per-frame extinction
    packed as base64 uint8 (scaled to ``kmax``), and ``kmax`` itself — or
    ``None`` when no FDS directory / extinction slice is available. Any failure
    is swallowed so the trajectory viewer never breaks on smoke rendering.

    ``simulation`` accepts a pre-loaded ``fdsreader.Simulation`` (used by tests
    to inject a fake slice); when ``None`` the directory is parsed from disk.
    """
    if simulation is None and (not fds_dir or not Path(fds_dir).exists()):
        return None
    try:
        import numpy as np

        if simulation is not None:
            sim = simulation
        else:
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

        return {
            "W": int(w),
            "H": int(h),
            "ext": [float(xs[0]), float(ys[0]), float(xs[-1]), float(ys[-1])],
            "kmax": kmax,
            "b64": base64.b64encode(bytes(buf)).decode("ascii"),
        }
    except Exception:
        return None


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
    colors = [color_of.get(agent_exit.get(a, ""), "#cc785c") for a in agent_ids]

    frames_all = sorted(data["frame"].unique())
    step = max(1, len(frames_all) // _N_SAMPLES)
    sampled = frames_all[::step]
    by_frame = {f: g for f, g in data.groupby("frame")}

    samples, times = [], []
    for f in sampled:
        sub = by_frame[f]
        pos = {
            int(i): (float(x), float(y))
            for i, x, y in zip(sub["id"], sub["x"], sub["y"])
        }
        flat: list[Any] = []
        for a in agent_ids:
            p = pos.get(a)
            flat.append(p[0] if p else None)
            flat.append(p[1] if p else None)
        samples.append(flat)
        times.append(round(f / fps, 2))

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

    fed_samples: list[list[Any]] = []
    for idx, f in enumerate(sampled):
        present = {int(i) for i in by_frame[f]["id"]}
        ts = times[idx]
        fed_samples.append(
            [_fed_at(a, ts) if a in present else None for a in agent_ids]
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
                    "color": color_of.get(exit_id, "#cc785c"),
                    "label": exit_id.replace("_", " "),
                }
            )

    return {
        "times": times,
        "samples": samples,
        "colors": colors,
        "fed": fed_samples,
        "hasFed": has_fed,
        "walk": walk,
        "exits": exits,
        "bounds": _bounds(walkable, data),
        "smoke": _smoke_payload(fds_dir, times),
    }


_JS = """
(function () {
  var D = __DATA__;
  var canvas = document.getElementById('traj-canvas');
  if (!canvas || !D.samples.length) return;
  var playBtn = document.getElementById('traj-play');
  var slider = document.getElementById('traj-slider');
  var tlabel = document.getElementById('traj-time');
  var ctx = canvas.getContext('2d');
  var T = D.times, S = D.samples, COL = D.colors, FED = D.fed, n = COL.length;
  var t0 = T[0], t1 = T[T.length - 1], span = Math.max(1e-6, t1 - t0);
  var PLAYBACK = 16;            // seconds of wall time to play the whole run
  var simT = t0, playing = false, lastTs = null;
  var bx = D.bounds, pad = 0.06;
  var mode = D.hasFed ? 'fed' : 'exit';

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
        // Neutral gray smoke, dark enough to read on the light canvas theme.
        d[pi] = 74; d[pi + 1] = 72; d[pi + 2] = 78; d[pi + 3] = Math.round(a * 255);
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

  // FED dose -> tier colour (green -> amber -> orange -> red).
  var STOPS = [[0, '#3f8f57'], [0.3, '#d19a2e'], [0.6, '#d2722b'], [1, '#c23b2e']];
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
    if (d == null) return '#9aa0a6';
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
    var w = canvas.clientWidth || 600, h = 440;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return [w, h];
  }
  function tf(w, h) {
    var dx = bx[2] - bx[0] || 1, dy = bx[3] - bx[1] || 1;
    var mw = w * (1 - 2 * pad), mh = h * (1 - 2 * pad);
    var s = Math.min(mw / dx, mh / dy);
    var ox = (w - s * dx) / 2 - s * bx[0];
    var oy = (h - s * dy) / 2 - s * bx[1];
    return function (x, y) { return [ox + s * x, h - (oy + s * y)]; };  // flip y
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
  function draw() {
    var d = size(), w = d[0], h = d[1], p = tf(w, h);
    ctx.clearRect(0, 0, w, h);
    poly(D.walk, p, 'rgba(20,20,19,0.035)', 'rgba(20,20,19,0.18)', 1);
    var b = bracket(simT), a = S[b[0]], c = S[b[1]], f = b[2];
    drawSmoke(b[0], p);
    D.exits.forEach(function (e) {
      poly(e.poly, p, e.color + '28', e.color, 2);
    });
    for (var i = 0; i < n; i++) {
      var ax = a[2 * i], ay = a[2 * i + 1], cx = c[2 * i], cy = c[2 * i + 1];
      var X, Y;
      if (ax == null && cx == null) continue;
      else if (ax == null) { X = cx; Y = cy; }
      else if (cx == null) { X = ax; Y = ay; }
      else { X = ax + (cx - ax) * f; Y = ay + (cy - ay) * f; }
      var col = COL[i];
      if (mode === 'fed') {
        var da = FED[b[0]][i], dc = FED[b[1]][i], dv;
        if (da == null) dv = dc; else if (dc == null) dv = da;
        else dv = da + (dc - da) * f;
        col = fedColor(dv);
      }
      var q = p(X, Y);
      ctx.beginPath(); ctx.arc(q[0], q[1], 4.5, 0, 6.2832);
      ctx.fillStyle = col; ctx.fill();
      ctx.lineWidth = 0.5; ctx.strokeStyle = 'rgba(20,20,19,0.35)'; ctx.stroke();
    }
    tlabel.textContent = 't = ' + (simT - t0).toFixed(0) + ' s';
    slider.value = String(((simT - t0) / span) * 1000);
  }
  function loop(ts) {
    if (playing) {
      if (lastTs != null) simT += ((ts - lastTs) / 1000) * (span / PLAYBACK);
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
  requestAnimationFrame(loop);
})();
"""


def trajectory_component(result: Any, scenario: Any, fds_dir: str | None = None) -> Any:
    """A Card with a canvas trajectory animation (smooth interpolated playback)."""
    from monsterui.all import Card, DivLAligned, H3, UkIcon

    payload = _payload(result, scenario, fds_dir)
    if payload is None:
        return Card(
            DivLAligned(UkIcon("route"), H3("Trajectories", cls="m-0")),
            NotStr(
                '<p class="text-sm" style="color:hsl(var(--muted-foreground))">'
                "Trajectory data unavailable.</p>"
            ),
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
        '<canvas id="traj-canvas" class="traj-canvas"></canvas>'
        '<div class="traj-controls">'
        '<button id="traj-play" type="button" class="traj-play">▶</button>'
        '<input id="traj-slider" type="range" min="0" max="1000" value="0" '
        'class="traj-slider">'
        '<span id="traj-time" class="traj-time">t = 0 s</span>'
        + toggle
        + "</div></div>"
    )
    script = "<script>" + _JS.replace("__DATA__", data_json) + "</script>"
    return Card(
        DivLAligned(UkIcon("route"), H3("Trajectories", cls="m-0")),
        NotStr(markup + script),
    )
