# WKT → FDS conversions

Each pair is a designed JuPedSim walkable area and the FDS deck generated from
it by `pyfds_evac.core.wkt_to_fds` (auto-`dx`, floor-vent fire source, the
canonical extinction + CO/CO₂/O₂ slices). The generated FDS solid region is the
complement of the walkable WKT, so both share one coordinate frame by
construction (issue #26).

| `<case>.wkt` | source walkable area (copied from `assets/<case>/geometry.wkt`) |
| `<case>.fds` | generated deck (`wkt_to_fds(<case>.wkt)`) |

Regenerate:

```bash
python -m pyfds_evac.core.wkt_to_fds assets/t_junction/geometry.wkt > t_junction.fds
```

Note: scenarios with 0.1 m internal walls make auto-`dx` refine to 0.1 m (finer
mesh, more OBSTs) to resolve them; the rest use the 0.25 m default.

The `basic`, `social_force` and `haspel` pairs were removed alongside their
scenarios; `HC` has no scenario folder and is kept only as a generated sample.
