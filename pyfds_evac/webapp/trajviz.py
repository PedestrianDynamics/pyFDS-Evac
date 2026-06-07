"""Lightweight canvas trajectory animator.

Plotly's frame animation stepped between coarse samples, so motion jumped. This
renders agent dots on a <canvas> and interpolates positions between downsampled
samples in a requestAnimationFrame loop, giving smooth 60fps playback from a
small payload. Geometry (walkable area, exits) is drawn once per frame.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fasthtml.common import NotStr

from .plots import _PALETTE, _agent_exit_map

# Number of position samples sent to the browser; the JS interpolates between
# them, so this stays small while playback stays smooth.
_N_SAMPLES = 120


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


def _payload(result: Any, scenario: Any) -> dict | None:
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
        "walk": walk,
        "exits": exits,
        "bounds": _bounds(walkable, data),
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
  var T = D.times, S = D.samples, COL = D.colors, n = COL.length;
  var t0 = T[0], t1 = T[T.length - 1], span = Math.max(1e-6, t1 - t0);
  var PLAYBACK = 16;            // seconds of wall time to play the whole run
  var simT = t0, playing = false, lastTs = null;
  var bx = D.bounds, pad = 0.06;

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
    D.exits.forEach(function (e) {
      poly(e.poly, p, e.color + '28', e.color, 2);
    });
    var b = bracket(simT), a = S[b[0]], c = S[b[1]], f = b[2];
    for (var i = 0; i < n; i++) {
      var ax = a[2 * i], ay = a[2 * i + 1], cx = c[2 * i], cy = c[2 * i + 1];
      var X, Y;
      if (ax == null && cx == null) continue;
      else if (ax == null) { X = cx; Y = cy; }
      else if (cx == null) { X = ax; Y = ay; }
      else { X = ax + (cx - ax) * f; Y = ay + (cy - ay) * f; }
      var q = p(X, Y);
      ctx.beginPath(); ctx.arc(q[0], q[1], 4.5, 0, 6.2832);
      ctx.fillStyle = COL[i]; ctx.fill();
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
  window.addEventListener('resize', draw);
  requestAnimationFrame(loop);
})();
"""


def trajectory_component(result: Any, scenario: Any) -> Any:
    """A Card with a canvas trajectory animation (smooth interpolated playback)."""
    from monsterui.all import Card, DivLAligned, H3, UkIcon

    payload = _payload(result, scenario)
    if payload is None:
        return Card(
            DivLAligned(UkIcon("route"), H3("Trajectories", cls="m-0")),
            NotStr(
                '<p class="text-sm" style="color:hsl(var(--muted-foreground))">'
                "Trajectory data unavailable.</p>"
            ),
        )
    data_json = json.dumps(payload)
    markup = (
        '<div class="traj-wrap">'
        '<canvas id="traj-canvas" class="traj-canvas"></canvas>'
        '<div class="traj-controls">'
        '<button id="traj-play" type="button" class="traj-play">▶</button>'
        '<input id="traj-slider" type="range" min="0" max="1000" value="0" '
        'class="traj-slider">'
        '<span id="traj-time" class="traj-time">t = 0 s</span>'
        "</div></div>"
    )
    script = "<script>" + _JS.replace("__DATA__", data_json) + "</script>"
    return Card(
        DivLAligned(UkIcon("route"), H3("Trajectories", cls="m-0")),
        NotStr(markup + script),
    )
