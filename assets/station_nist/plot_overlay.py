#!/usr/bin/env python3
"""Overlay of both Station geometries in the NIST frame, with the 12 areas.

    .venv/bin/python assets/station_nist/plot_overlay.py

Writes ``overlay.png`` next to this file: the hand-drawn geometry of
``station_fahy`` translated into the NIST frame (grey outline), the
NIST-derived walkable area (black), the twelve Fahy areas, the four exits and
the checkpoints, and a detail of the front door.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely import wkt as W  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

HERE = Path(__file__).parent
FAHY = HERE.parent / "station_fahy"
TRANSLATION = (3.635, -8.366)
LABEL = "Station-derived geometry (provenance unverified)"


def _rings(ax, geom, label=None, **style):
    first = True
    for part in getattr(geom, "geoms", [geom]):
        ax.plot(*part.exterior.xy, label=label if first else None, **style)
        first = False
        for ring in part.interiors:
            ax.plot(*ring.xy, **style)


def _draw(ax, walkable, hand, config):
    _rings(ax, hand, "hand-drawn (station_fahy), translated", color="#9aa0a6", lw=0.6)
    _rings(ax, walkable, "NIST-derived walkable area", color="black", lw=0.8)
    cmap = plt.get_cmap("tab20")
    seen: dict[str, int] = {}
    for dist in config["distributions"].values():
        row = dist["parameters"]["fahy_row"]
        if row in seen:
            continue
        seen[row] = len(seen)
        poly = Polygon(dist["coordinates"])
        ax.fill(*poly.exterior.xy, color=cmap(seen[row]), alpha=0.45, lw=0)
        ax.text(poly.centroid.x, poly.centroid.y, row, ha="center", fontsize=6)
    for exit_id, ex in config["exits"].items():
        poly = Polygon(ex["coordinates"])
        ax.fill(*poly.exterior.xy, color="#d62728")
        ax.annotate(
            exit_id.replace("jps-", ""),
            poly.centroid.coords[0],
            fontsize=7,
            color="#d62728",
        )
    for cp in config["checkpoints"].values():
        ax.plot(*cp["center"], "o", ms=4, mfc="none", color="#1f77b4")
    ax.set_aspect("equal")
    ax.grid(lw=0.3)


def main() -> None:
    walkable = W.loads((HERE / "geometry.wkt").read_text())
    hand = affinity.translate(
        W.loads((FAHY / "geometry.wkt").read_text()), *TRANSLATION
    )
    config = json.loads((HERE / "config.json").read_text())
    fig, (ax, det) = plt.subplots(
        1, 2, figsize=(15, 6.5), gridspec_kw={"width_ratios": [2.2, 1]}
    )
    _draw(ax, walkable, hand, config)
    ax.set_xlim(-13, 19)
    ax.set_ylim(-19, 4)
    ax.set_xlabel("x in the NIST frame (m)")
    ax.set_ylabel("y (m)")
    ax.legend(loc="lower left", fontsize=7)
    _draw(det, walkable, hand, config)
    det.set_xlim(1.5, 7.5)
    det.set_ylim(-18, -12)
    det.set_title(
        "front door: vestibule, 0.91 m interior door, ticket area", fontsize=8
    )
    fig.suptitle(f"Station NIST deck, areas on the NIST frame. {LABEL}", fontsize=10)
    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.08, wspace=0.12)
    fig.savefig(HERE / "overlay.png", dpi=130)


if __name__ == "__main__":
    main()
