# Showcase #939: strong vs. weak fire on DoorAlgo_Da (1.0 work)

Status: planned 2026-11-20, starts with the 1.0 work. Paper target:
SoftwareX draft Sec. 3.2 (replaces or joins the Schroeder 2015 example).

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

## Recorded decisions (from #939 and the 2026-11-13/14 sessions)

- Geometry: FDS+Evac guide DoorAlgo_Da (guide section 4.4,
  `assets/fds_evac_guide/`), modified copy. Not a like-for-like FDS+Evac
  comparison: TopExit closes, a late group and signs are added.
- Fire-only deck: evac namelists stripped, T_END 200, DT_SLCF 1,
  cell-centred gas slices at 1.75 m. CO_YIELD 0.01; do not raise yields;
  incapacitation is left out (FED max about 0.004).
- Scenario: `pyfds-evac init` on the deck, plus 15 late agents in the
  lower right (pre-movement uniform 25-45 s), TopExit `closed_after_s` 30.
- Signs face into the room (Bottom 0, Left 90, Right 270, Top 180);
  Left/Right `max_distance` 15 m. A sign on the way from the Gap to
  LeftStrip gives the late group a way to learn LeftExit.
- Strong vs. weak: two burners differing only in HRR (record both values
  when rebuilding; the weak run lived in `fire05_weak`).
- Animation from a script, knowledge growth shown
  (`--output-knowledge-history`).

## Steps

1. **Rebuild and commit the inputs** (`assets/showcase_doorAlgo/`): the
   fire-only deck in two variants (strong, weak), the scenario
   (`config.json`, `geometry.wkt`), a README with every non-default value
   and its reason. Add the decks to the init-deck sweep tables.
2. **FDS runs (local, about 13 min each, about 100 MB each)** into new
   folders `fds-evac-data/showcase_doorAlgo/{strong,weak}/`, each with a
   README: deck sha256, commit, FDS version, ranks, wall time; check the
   exit code and "STOP: FDS completed successfully".
3. **Evacuation runs:** 10 seeds per fire on the 1.0 release candidate,
   outputs (sqlite with `agent_exits`, knowledge history, FED history,
   run logs) into `fds-evac-data/showcase_doorAlgo/evac/`. Seed 1 should
   reproduce the table above in kind; differences are reported, not tuned.
4. **Figure and docs:** one paper figure (exit use and evacuated over
   time, strong vs. weak, mean and range over seeds), a docs page
   `docs/showcase.md`, `examples/showcase.py`, and a regression test that
   the run still shows rerouting, a discovery event and the closure.
5. **Video:** rebuild only from the committed data; the video project
   (storyboard, compositions, render script) is versioned beside the
   other videos in `videos/` and its data are copied into it or linked to
   `fds-evac-data/`.

Close #939 when steps 1-4 are merged.

## Rule for future videos

Every pyFDS-Evac video keeps its data: inputs committed (or in
`fds-evac-data/` with a README), FDS and evacuation outputs in
`fds-evac-data/`, and the video project in `videos/`. Nothing a video
shows may exist only in a session scratchpad.
