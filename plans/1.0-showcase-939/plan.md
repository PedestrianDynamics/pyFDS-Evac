# Showcase #939: strong vs. weak fire on DoorAlgo_Da (1.0 work)

Status: planned 2026-11-20, revised 2026-11-21 after a clear-air spike.
Starts with the 1.0 work. Paper target: SoftwareX draft Sec. 3.2
(replaces or joins the Schroeder 2015 example; decide before step 4,
because it sets the figure and the claim).

## Why this plan exists

The showcase behind the YouTube video "pyFDS-Evac: how fire smoke changes
which exits evacuees find (strong vs. weak fire)" was built and run only
in a session scratchpad (2026-11-13/14). Deck, scenario, both FDS runs and
the video project are lost. What survives:

- the decisions in issue #939 and memory note `showcase-939`;
- the seed-1 result table (135 agents, 200 s):

| | Strong fire | Weak fire |
|---|---|---|
| Out at 200 s | 124 / 135 | 133 / 135 |
| Upper group (15, knows only TopExit) | 7 out via LeftExit, 8 pace to the end | all 15 out via LeftExit |
| Lower-room arrivals (20) | 17 out through Bottom, slowed to 0.4-0.6 | out through Bottom, little slowing |
| Densest smoke an agent meets | K about 9 1/m | K about 3.5 1/m |

These numbers are not reproducible today and must not be quoted until
step 3 reproduces them.

## The story the scenario must show

1. TopExit (top left) closes at 30 s.
2. The upper group (top right, knows only TopExit) can no longer use it
   and has to learn a new exit. Two crossings in the walls make it
   possible to discover LeftExit (bottom left).
3. Smoke builds up in that area. Agents who start later (the late
   group) can no longer discover LeftExit, because smoke shortens how
   far they can see and read signs.

The result of the showcase is point 3: the late group's discovery of
LeftExit over time, strong versus weak fire. Rerouting of the upper
group is the setup, not the result.

## Spike result (2026-11-21, clear air, no FDS, main at 0.9.0)

Scratch only; scenario rebuilt from the deck with `pyfds-evac init`.

- Upper group (15, top right x 36-48, y 32-38, knows only TopExit,
  pre-movement 5 s, TopExit closed after 30 s), 3 seeds: all 15 evacuate;
  13-14 leave through LeftExit, discovered by sight from about 60 s; no
  agent waits at the closed exit. The rerouting half works on main.
- Late group (15, pre-movement uniform 25-45 s) from four spawn boxes in
  the lower middle room and the corridor above the Gap, 3 seeds each: in
  clear air every agent finds an exit by sight within seconds and
  evacuates (BottomExit from the room, LeftExit from the corridor).
  Clear air cannot show the smoke effect; only the FDS runs can.
- The knowledge history labels every discovery `sight`; there is no
  separate sign event, so a discovery event does not tell a sign from
  direct sight.
- The old failures (agents walking into the closed exit, explorers
  wandering between the Gap and their spawn) did not appear. #946 (PR 947,
  "walk there, then look") may be the reason; confirm in step 1 on the
  real deck.

## Recorded decisions (from #939 and the 2026-11-13/14 sessions)

- Geometry: FDS+Evac guide DoorAlgo_Da (guide section 4.4,
  `assets/fds_evac_guide/`), modified copy. Not a like-for-like FDS+Evac
  comparison: TopExit closes, a late group and signs are added.
- Fire-only deck: evac namelists stripped, T_END 200, DT_SLCF 1,
  cell-centred gas slices at 1.75 m. CO_YIELD 0.01; do not raise yields;
  incapacitation is left out (FED max about 0.004).
- Scenario: `pyfds-evac init` on the deck, plus the late group (15
  agents, pre-movement uniform 25-45 s), TopExit `closed_after_s` 30.
- Signs face into the room (Bottom 0, Left 90, Right 270, Top 180);
  Left/Right `max_distance` 15 m. Two crossings let agents reach a point
  where LeftExit can be discovered.
- Strong vs. weak: two burners differing only in HRR.
- Animation from a script, knowledge growth shown
  (`--output-knowledge-history`).

## Open before step 1

- **Group polygons.** The original late-group polygon is lost. Choose
  one where the group cannot see any exit from its spawn point and where
  LeftExit is discoverable only after the crossings; commit it with a
  reason. Record every group's polygon, size, pre-movement and known
  exits in the README.
- **Strong and weak HRR.** Both values were lost. Choose and freeze them
  before any FDS run and record why. Do not adjust them afterwards to
  reproduce the seed-1 table.
- **Release candidate.** Name the commit or tag of the 1.0 release
  candidate that step 3 runs on, and record it in the `evac/` README.

## Steps

1. **Rebuild and commit the inputs** (`assets/showcase_doorAlgo/`): the
   fire-only deck in two variants (strong, weak), the scenario
   (`config.json`, `geometry.wkt`), a README with every non-default value
   and its reason. Add the decks to the init-deck sweep tables. Start
   with a short clear-air check on the real scenario that the upper
   group reroutes and the late group has the crossings available.
2. **FDS runs (local, FDS 6.10.1, about 13 min each, about 100 MB
   each)** into new folders `fds-evac-data/showcase_doorAlgo/{strong,weak}/`,
   each with a README: deck sha256, commit, FDS version, ranks, wall time;
   check the exit code and "STOP: FDS completed successfully". The guide
   deck itself is FDS 6.7.7; say so in the README. This box has no FDS, so
   these runs happen on the maintainer's Mac.
3. **Evacuation runs:** 10 seeds per fire on the named release
   candidate, outputs (sqlite with `agent_exits`, knowledge history, FED
   history, run logs) into `fds-evac-data/showcase_doorAlgo/evac/`.
   Report, per fire, the fraction of late-group agents that discover
   LeftExit and when, plus the exit use and evacuated-over-time curves.
   Seed 1 should reproduce the table above in kind; differences are
   reported, not tuned.
4. **Figure and docs:** one paper figure (late-group discovery of
   LeftExit and exit use over time, strong vs. weak, mean and range over
   seeds), a docs page `docs/showcase.md`, `examples/showcase.py`, and a
   regression test. The test cannot use the 100 MB runs: it uses a small
   fire fixture (cropped slices or a short synthetic extinction field, as
   in `tests/data/cell_centred`) with a coefficient that rises quickly
   near the crossings. It asserts the closure, the upper group's
   rerouting, and that late agents discover LeftExit in the weak variant
   but not (or later) in the strong one. Discovery by sign needs its own
   event label in the knowledge history; add it, or assert on sight only
   and say so.
5. **Video:** rebuild only from the committed data; the video project
   (storyboard, compositions, render script) is versioned beside the
   other videos in `videos/` and its data are copied into it or linked to
   `fds-evac-data/`.

Close #939 when steps 1-4 are merged. The video (step 5) was the
original deliverable; say in the issue that it follows separately.

## Rule for future videos

Every pyFDS-Evac video keeps its data: inputs committed (or in
`fds-evac-data/` with a README), FDS and evacuation outputs in
`fds-evac-data/`, and the video project in `videos/`. Nothing a video
shows may exist only in a session scratchpad.
