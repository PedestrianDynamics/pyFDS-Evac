---
title: Studies
weight: 5
---

Each study asks one question about egress in a fire and answers it with
our own FDS runs and pyFDS-Evac crowds. A study page shows what was
computed, how, from which inputs, and where it departs from any published
work it follows.

Studies stand alone. They are not numbered and do not build on each
other; read them in any order. Each new study adds one row to this table
and one to
[Design fires › Fires used in pyFDS-Evac studies](/fundamentals/design-fires.md#fires-used-in-pyfds-evac-studies).

| Study | Question | Scenario | Fire | Status |
|---|---|---|---|---|
| [ASET-RSET maps after Schröder et al. (2020)](/docs/study-schroeder2020.md) | Where in the room does smoke arrive before the last person leaves? | 30 × 10 × 3 m room, one door, 100 people; after Schröder et al. (2020) | 60 kW constant on a 1 × 1 m polyurethane burner, as in the authors' reference implementation | Done. Maps are built by a script; built-in maps are [#210](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/210) |
| [Route choice in smoke after Schröder et al. (2015)](/docs/study-schroeder2015.md) | Which door and exit do agents choose when route cost reads the smoke along the whole route? | Assembly hall 10.5 × 24 m with doors A and B to a corridor with exits E and F, 200 people, pre-movement mean 120 s; geometry after Schröder et al. (2015), fire ours | t², α = 0.047 kW/s² to 1.5 MW, PVC, in a room next to the hall, 4.0 m ceiling; two comparison fires | Done. Door C closed and a higher ceiling are deferred |
| [Evacuation with and without the fire](/docs/howto-with-without-fire.md) | Is the RSET from a run without the fire conservative against a run coupled to the fire? | T-junction, 100 people, pre-movement 0, 30 or 60 s | PVC (FDS fuel: vinyl chloride monomer); ramp to 2 MW at 90 s, then steady | Done |

Status is one of: Planned, In progress, Done.

The fires are compared with the published design-fire classes in
[Design fires › Fires used in pyFDS-Evac studies](/fundamentals/design-fires.md#fires-used-in-pyfds-evac-studies).

Each study is one scenario run with research software. No result on these
pages is a design or safety verdict.
