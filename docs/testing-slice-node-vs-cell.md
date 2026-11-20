---
title: "Node-centred against cell-centred slices"
linkTitle: "Node vs cell slices"
weight: 17
---

| | |
|---|---|
| **Component** | Reading of FDS slices at the sampling height: K, the walking-speed factor, the gas and heat FED rates ([#231](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/231)) |
| **Level** | FDS case, read with pyFDS-Evac's own samplers and rate functions; no evacuation is run |
| **Asset** | `assets/slice_node_vs_cell/slice_node_vs_cell.fds`, `scripts/verification/slice_node_vs_cell.py` |
| **Expected value from** | none: this is a measurement of a difference, not a pass/fail check |
| **Status** | Measured with FDS 6.10.1. It quantifies how far the two readings are apart; it does not decide which one is right |

## The two readings

FDS+Evac reads the cell-centred mass fractions and density of the fire cell
that holds the centre of each evacuation-grid cell, at `HUMAN_SMOKE_HEIGHT`
(default 1.6 m): `GET_FIRE_CONDITIONS` takes `ZZ` and `RHO` of the cell
`(II, JJ, KK)`, with `KK = FLOOR(...)` of the nose height
([`evac.f90`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90)
at c9da70d7a, `GET_FIRE_CONDITIONS` and the `HUMAN_GRID` setup above it).

pyFDS-Evac reads the value position of a slice nearest the agent, at the
frame nearest the time ([FDS slice sampling](fds-sampling.md)). A default
`&SLCF` slice is node-centred: FDS writes one value per mesh node, averaged
from the cells around it (FDS User's Guide, `&SLCF`). A `CELL_CENTERED=T`
slice holds the unaveraged cell values. Near a sharp gradient (a plume edge, a
layer interface) the averaged node value differs from the cell value.

## Setup

One compartment, 6 × 6 × 3 m, adiabatic walls, a 0.6 × 0.6 m opening in the
`x = 0` wall and a 0.4 × 0.4 m propane burner (160 kW after a 10 s ramp,
`SOOT_YIELD` 0.05, `CO_YIELD` 0.04) at the centre. The grid is 0.2 m in x and
y and 0.1 m in z, so z = 1.6 m is a node plane and the cell centres next to it
are at 1.55 and 1.65 m. The hot layer fills the room from the ceiling and
crosses 1.6 m while the plume stands in the middle: over the 120 s the mean
temperature on the plane rises from 20 °C to about 100 °C and K from 0 to
about 1.9 1/m. FDS 6.10.1 (`FDS-6.10.1-0-g12efa16-release`), OpenMP with four
threads, 10 min wall time on a shared machine. The output is in the data
store under `fds-evac-data/slice_node_vs_cell`.

At z = 1.6 m the deck writes `SOOT EXTINCTION COEFFICIENT`, the `VOLUME
FRACTION` of CO, CO2 and O2, and `TEMPERATURE`, as a default node-centred
`&SLCF` and as `CELL_CENTERED=T` slices at 1.55 m and 1.65 m. The cell whose
lower face is 1.6 m (centre 1.65 m) is the one FDS+Evac's `FLOOR` indexing
gives; the cell below (1.55 m) is the other candidate, because a nose height
that falls exactly on a cell face is decided by rounding.

## Analysis

`scripts/verification/slice_node_vs_cell.py` builds pyFDS-Evac's own readers
on each family (`SliceFieldSampler`, `ExtinctionField` with `SmokeSpeedModel`
and the default Lund law, `FdsFedField` with `default_fed_rate_per_minute`,
`FdsHeatField` with `default_heat_fed_rate_per_minute`) and reads every
output frame (61 frames, 2 s apart) at every fire cell of the plane (900):

- *node* at the cell centre, which is exactly halfway between two nodes per
  axis and so a tie that the sampler gives to the lower node; and at the four
  quadrant points of the cell, each nearest to a different corner node, as
  agents spread over the cell would read;
- *cell* at the cell centre of the 1.65 m slice, of the 1.55 m slice, and
  their mean, which isolates the horizontal averaging of the node value from
  the half-cell vertical offset.

The interface zone is where a sharp gradient meets the plane. A cell is sharp
at a frame when the cell-centred temperature (mean of the two layers) steps by
at least 10 % of the frame's range across a face to an in-plane neighbour or
between the two layers, and the range is at least 5 K; the zone is the sharp
cells dilated by one cell. It holds 5.5 % of the cell-frames and is mostly the
plume edge; the layer crossing the plane adds the frames in which the two
layers differ. Relative differences use the samples where either reading
exceeds a floor (K 1e-3 1/m, FED rate 1e-5 1/min, heat rate 1e-6 1/min), with
|cell| as the denominator.

## Result

Node reading against the 1.65 m cell, at the quadrant points (median, P95,
maximum of |node − cell|):

| Quantity | All cell-frames | Interface zone |
|---|---|---|
| K [1/m] | 0.020, 0.11, 1.6 | 0.051, 0.53, 1.6 |
| Speed factor [-] | 0.0016, 0.0086, 0.13 | 0.0041, 0.043, 0.13 |
| Gas FED rate [1/min] | 8.8e-5, 5.9e-4, 0.029 | 2.4e-4, 5.2e-3, 0.029 |
| Heat FED rate [1/min] | 4.9e-4, 5.8e-3, 7.1 | 2.4e-3, 0.49, 7.1 |
| T [K] | 0.94, 6.2, 199 | 3.9, 74, 199 |

As a fraction of the cell value, the median difference is 2.5 % for K and
0.2 % for the speed factor over all cell-frames, and 6.7 % for K and 0.45 %
for the speed factor in the interface zone, where the P95 is 139 % for K and
4.9 % for the speed factor (maximum 17 %). The gas FED rate differs by 3 %
(median) over all cell-frames and by 9 % in the zone (P95 190 %); the heat
FED rate by 5 % and 21 % (P95 370 % in the zone). The relative P95 and
maximum are large because the cell value is small where the node averages a
neighbouring hot cell. Reading at the exact cell centre instead of the
quadrant points, or against the 1.55 m cell or the mean of the two, changes
the medians by less than a factor of two and does not change the picture
(`python scripts/verification/slice_node_vs_cell.py --data DIR` prints all
combinations). Against the mean of the two cells the zone median of K is 0.046
1/m, close to the 0.051 1/m of the 1.65 m cell: most of the difference is the
horizontal averaging, not the half-cell vertical offset.

Accumulated over the 120 s, five stationary points chosen as the cells most
often in the zone (at least 1 m apart), gas FED, node against the 1.65 m cell:

| Point (x, y) [m] | Zone frames | Node, centre | Node, quadrant mean (range) | Cell 1.65 m |
|---|---|---|---|---|
| (2.7, 2.7) | 60 | 0.0071 | 0.0094 (0.0071 to 0.014) | 0.0075 |
| (3.5, 3.3) | 59 | 0.0078 | 0.0074 (0.0073 to 0.0078) | 0.0074 |
| (2.5, 3.7) | 22 | 0.0071 | 0.0072 | 0.0073 |
| (0.5, 5.7) | 4 | 0.0099 | 0.0100 | 0.0104 |
| (0.1, 0.1) | 1 | 0.011 | 0.010 | 0.011 |

The doses are within 5 % of the cell dose except at the plume edge (2.7, 2.7)
m, where the node reading spans −5 % to +89 % depending on where in the cell
the agent stands. The heat FED dose shows the same pattern more strongly,
because it is a steep function of temperature: at (2.7, 2.7) m the node dose
is 0.043 (centre) and 0.14 (quadrant mean, range 0.043 to 0.36) against 0.069
for the cell, and at (3.5, 3.3) m 0.068 against 0.040. All doses in this
deck stay far below 1, so none of the differences reaches an incapacitation
threshold.

## What it means for a comparison with FDS+Evac

- Away from gradients the two readings agree to a few per cent in K and a few
  tenths of a per cent in the speed factor. A comparison of evacuation times
  with FDS+Evac in a smoke layer that is horizontally uniform at 1.6 m is not
  affected by the slice centring at this level.
- At a plume edge or while a layer crosses the plane the node value is an
  average of up to eight cells, so K, T and the FED rates differ by tens of
  per cent in the median and by factors at the P95. The speed factor is
  bounded by the Lund law (floor 0.1, factor 1 at K = 0), so its absolute
  difference stays below 0.15 here, but the heat dose and the gas dose are
  steep functions of T and CO and are not.
- The sign of the difference depends on where the agent stands relative to the
  gradient: at the plume edge (2.7, 2.7) m the node reading gives 0.043 to
  0.36 for the heat dose against 0.069 for the cell, so the node value is
  both lower and higher than the cell value within one cell.
- This quantifies a difference. It does not decide which reading is right: the
  cell value is what FDS+Evac uses and what FDS solved for, the node value is a
  smoothed field of the same solution. One deck, one grid (0.2 m by 0.2 m by
  0.1 m) and one fuel are measured; a finer grid shrinks the averaging
  distance, a coarser one grows it.

## `CELL_CENTERED=T` as an option

pyFDS-Evac reads cell-centred slices: the sampler takes the cell centres of a
`CELL_CENTERED=T` slice as value positions, and the slice height is the
centre of the cell that holds the requested z ([FDS slice
sampling](fds-sampling.md)). A deck that writes only cell-centred slices at
the sampling height therefore gives the FDS+Evac reading with no change to
pyFDS-Evac. When one case holds both families at similar heights, the run
reads the horizontal slice whose height is nearest the requested one (the
first declared on a tie); there is no option to prefer cell-centred slices,
and none was added. To compare, write the cell-centred slice at the height you
want and the node-centred ones elsewhere, or run twice with the slices in
separate decks.

## Reproduce

```bash
fds slice_node_vs_cell.fds        # FDS 6.10.1; output to <DATA>
python scripts/verification/slice_node_vs_cell.py --data <DATA>
SLICE_NODE_VS_CELL_DATA=<DATA> pytest tests/verification/test_slice_node_vs_cell.py
```

The synthetic two-cell test of the analysis runs without FDS; the
`external_data` test reads the FDS output.
