# ISO 20414 Table 21 — reduced visibility vs walking speed

**Source:** ISO 20414:2020(E), §5.4, **Test 18 — Reduced visibility vs walking
speed**, specified in **Table 21**.

> *Objective* — "Assess consistency between the assigned impact of reduced
> visibility on walking speed and model representation."
>
> *Geometry* — "A corridor 2 m wide and 100 m long. One exit (1 m wide) is
> placed at the end of the corridor."
>
> *Scenario* — "The unimpeded walking speed of an occupant for a smoke-free
> environment is set to a constant value equal to 1,25 m/s. A constant
> extinction coefficient equal to 1,0/m is implemented in the corridor prior to
> running the simulation."
>
> *Expected result* — "the time needed by the occupant to cover the distance of
> the corridor is the same as the time manually calculated employing the
> correlation used by the model."

## How this asset matches

| ISO 20414 Table 21 | this asset | |
|---|---|---|
| corridor 2 m × 100 m | `POLYGON((-50 1, 50 1, 50 -1, -50 -1))` = 2 × 100 m | ✅ |
| unimpeded speed 1,25 m/s | `v0: 1.25` | ✅ |
| one occupant | `number: 1` | ✅ |
| constant extinction 1,0/m | swept, including 1.0 | ✅ |
| repeat at 10, 7,5, 3,0, 0,5 /m | `[0.5, 1.0, 3.0, 7.5, 10.0]` | ✅ |
| exit 1 m wide | 1.00 m opening, centred | ✅ |
| repeat at speeds 1,0 / 0,75 / 0,5 / 0,25 m/s | `test_iso_table21_holds_across_unimpeded_walking_speeds` | ✅ |

Both axes are covered, as ISO asks: "different combinations of unimpeded walking
speeds … and constant extinction coefficients need to be tested".

**The speed axis is a null test by construction.** The smoke factor multiplies
`v0`, so the time *ratio* cannot depend on `v0`. That is exactly why it earns
its place: it fails if a clamp is ever applied to an absolute speed rather than
to the factor — the shape of defect the FIC speed factor turned out to have,
where the multiplier was applied to the current speed instead of the baseline
and compounded to zero.

## What the test asserts

`tests/test_smoke_speed.py::test_iso_table21_constant_extinction_matches_expected_time_ratio`,
parameterised over the five extinction coefficients. For each it runs the
scenario clear, then under a `ConstantExtinctionField`, and asserts:

1. `t_smoke / t_clear ≈ 1 / speed_factor_from_extinction(k)` within **8 %** —
   ISO's expected result, against the model's own correlation as ISO requires
   ("the correlation used by the model");
2. every recorded `speed_factor` equals the expected one **exactly**.

The two do different jobs. (2) checks the model computed the right multiplier;
(1) checks that multiplier actually changed how long the walk took. A factor
that is computed and then never applied passes (2) and fails (1) — which is
exactly the failure the FIC speed factor had for months.

The 8 % tolerance absorbs discretisation: the occupant starts somewhere inside
a spawn box, the exit has width, and the update interval is 0.1 s.

At k = 10 /m the scenario needs `set_max_time(450)`, because the speed factor
approaches its floor and the default horizon is too short.

## Not FDS-coupled

The field is a `ConstantExtinctionField`; `SmokeSpeedConfig(fds_dir=".")` is a
placeholder and no slice is ever read. That is faithful to ISO — the standard
says the extinction coefficient is "implemented in the corridor prior to running
the simulation", not that it comes from a fire model — but it means this test
verifies the speed law and its coupling, **not** the FDS sampling path. For that,
see [`assets/iso_table22_coupled`](../iso_table22_coupled/README.md).

`ISO-table21.fds` exists so the geometry can be run under FDS if wanted; the
tests do not use it. It was UTF-16 and unrunnable until it was regenerated
(PR #79), which is worth knowing if you find an old copy.

## Also used as a generic fixture

`test_progress_callback.py`, `test_webapp.py` and `test_fed.py` load this asset
because it is the smallest scenario that runs, not for its ISO provenance.
Changing it therefore ripples well beyond the ISO tests.

## Related

- [`assets/ISO-table22`](../ISO-table22/README.md) — ISO 20414 Table 22, the
  occupant-incapacitation counterpart.
- FDS+Evac Technical Reference **Figure 9** ("A smoke vs speed test") is the
  vendor's version of this same test, with different numbers: a 10 m corridor,
  1,5 m/s, soot densities 0/500/1000/1500 mg/m³. It is implemented separately as
  `test_fds_evac_guide_smoke_density_points_match_theory`.
