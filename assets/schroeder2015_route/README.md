# Route choice in smoke after Schröder et al. (2015)

Inputs of the study page
[Route choice in smoke after Schröder et al. (2015)](../../docs/study-schroeder2015.md):
an assembly hall (Room 1) with doors A and B to a corridor (Room 2) with
exits E and F, and a fire in Room 3. The geometry is digitised from
Schröder et al. (2015), Fig. 6 (p. 335,
[JuSER 255940](https://juser.fz-juelich.de/record/255940)). The fire, the
crowd settings and the routing are ours. No data from the authors is used.

Inputs only. FDS output and evacuation results are not kept in the
repository.

| File | Role |
|------|------|
| `geometry.py` | Every coordinate: walkable area, stages, FDS walls and doors, burner |
| `make_configs.py` | Writes `evac/geometry.wkt`, `evac/config_gate.json`, `evac/config_additive.json` |
| `make_decks.py` | Writes the FDS decks of the nine fire variants (`--only NAME` for some) |
| `evac/config_gate.json` | Scenario with `cost_model: gate`; also used for the no-fire and smoke-blind arms |
| `evac/config_additive.json` | The same scenario with `cost_model: additive` |
| `evac/geometry.wkt` | Walkable area (Room 3 is not walkable) |
| `a047_pvc_h40/a047_pvc_h40.fds` | Main fire: t², α = 0.047 kW/s² to 1.5 MW, PVC, ceiling 4.0 m |
| `a047_pvc_h35/a047_pvc_h35.fds` | Comparison fire: as the main fire, ceiling 3.5 m |
| `a012_pvc_h30/a012_pvc_h30.fds` | Comparison fire: α = 0.012 kW/s², ceiling 3.0 m |
| `run_p1.sh` | Runs the evacuation arms for seeds 1–10 on one FDS output |

`make_decks.py` writes the three decks byte for byte. They differ from
the decks of the page's FDS runs only in the header comment, which now
points to this folder. The comments inside the decks name the tags of the study
notes: [N] is the design fire fixed before any routing run, [D] digitised
from the paper (±0.5–1 m), [A] assumed here.

## Regenerate the inputs

From the repository root:

```bash
uv run python assets/schroeder2015_route/make_configs.py assets/schroeder2015_route
uv run python assets/schroeder2015_route/make_decks.py assets/schroeder2015_route \
    --only a047_pvc_h40 a047_pvc_h35 a012_pvc_h30
```

## Run

`FIRE` and `RUNS` are folders of your choice outside the repository. FDS
6.10.1 on 6 MPI processes, about 60–100 min per deck:

```bash
mkdir -p "$FIRE/a047_pvc_h40"
cp assets/schroeder2015_route/a047_pvc_h40/a047_pvc_h40.fds "$FIRE/a047_pvc_h40/"
(cd "$FIRE/a047_pvc_h40" && mpiexec -n 6 fds a047_pvc_h40.fds)
```

Then the four arms, 10 seeds each (about 25–40 s per run), from the
repository root:

```bash
PY="uv run python" bash assets/schroeder2015_route/run_p1.sh \
    "$FIRE/a047_pvc_h40" "$RUNS/p1_a047_pvc_h40" 6 --with-nofire
```

The page lists the commands for each arm, the figure scripts and the
expected results.

Licence: decks, scenario files and geometry CC-BY-4.0; code MIT.
