# FDS 6.7.7 + C/VM2 ballroom on JURECA: command sequence (#808)

Every command is run by hand. Nothing here has been run: JURECA was not
reachable and there is no FDS on the machine where the scripts were
written. Stop at the first failed check. Do not submit anything
(`--go`) without your own go-ahead.

## Deck decisions to confirm before any run

Copied from `../README.md` ("Open choices named in #808" and "Further
choices"); none is resolved here.

- Door coordinates: y 11.5 and 41.5 m, east and west (Confirm).
- Fuel for `&REAC`: CH2.686O0.592 (Confirm).
- Fire mesh 0.25 m (**Confirm**): D*/dx 5.7, burner top 0.5 m, 2.0 m doors.
- MPI split: 21 meshes.
- West doors: exits to safety, no foyer (**Confirm**).
- Door state: open from t = 0 (**Confirm**); the example keeps them
  closed until the evacuation.
- Free speed 1.2 m/s constant (**Confirm**).
- Body size: `DIA_MEAN` 0.51 m constant, `init` maps it to radius 0.15 m
  (**Confirm**).
- Relaxation time: Adult default, uniform 0.8-1.2 s (Confirm).
- Evacuation grid 0.25 m (Confirm).
- Second grid 0.5 m, phase 1 only (Confirm).
- `FAC_DOOR_QUEUE`: default 1.3, not switched off; proposed ten more
  phase 3 runs with 0 beside pyFDS-Evac `w_queue` 0; whether 0 also needs
  a new phase 1 is unverified (**Confirm**).
- `FED_DOOR_CRIT=-1000.0`, the default of the code that runs; -100 is the
  documented value (**Confirm**).
- `HUMAN_SMOKE_HEIGHT` 2.0 m is a cell face; which cell FDS+Evac reads
  there (1.75-2.0 or 2.0-2.25 m) could not be determined (**Confirm**) or
  move both to a cell centre.

## The workflow (FDS 6.7.7, Evac 2.6.1)

Fire and evacuation never run together, and all three phases share
CHID `cvm2_ballroom`:

1. Phase 1 `cvm2_ballroom_evac.fds` (`EVACUATION_INITIALIZATION`):
   evacuation mesh only, serial. Writes `.eff` and `.xyz`.
2. Phase 2 `cvm2_ballroom_evac_fed.fds` (`EVACUATION_WRITE_FED`): fire
   meshes only, MPI (21). Needs the phase 1 `.xyz`. Writes the slices and
   `.fed`.
3. Phase 3 `cvm2_ballroom_evac_mc.fds` (`EVACUATION_MC_MODE`):
   evacuation only, serial, reads `.eff` and `.fed`. Run ten times. It
   writes `cvm2_ballroom_evmc.csv`, overwritten by every run, so each
   repeat has its own directory.

Run directories under `$PROJECT/$USER/fds-evac-runs/cvm2-ballroom/`:
`phase1`, `phase2` (gets `.xyz` copied from `phase1`), `rep01`..`rep10`
(each gets `.eff` from `phase1` and `.fed` from `phase2`). Optional:
`fire-test` (stand-alone `cvm2_ballroom_fire.fds`) and `evac-dx050`
(phase 1 on the 0.5 m grid, CHID `cvm2_ballroom_dx050`).

pyFDS-Evac must read the slices of `phase2`, not those of `fire-test`:
an evacuation run cannot use a fire run without evacuation meshes.

The existing FDS 6.10.1 build is not touched: FDS 6.7.7 lives in
`$PROJECT/$USER/fds-6.7.7`, runs in `$PROJECT/$USER/fds-evac-runs/cvm2-ballroom/`,
and no shell profile is edited.

## Why this build target

Read at tag `FDS6.7.7` (`gh api repos/firemodels/fds/contents/<path>?ref=FDS6.7.7`):

- `Build/` holds `impi_intel_linux_64`, `mpi_intel_linux_64`,
  `mpi_gnu_linux_64` (plus `_db`/`_dv`, osx, win, pgi, aix variants). There
  is no `ompi_gnu_linux_64` at this tag; that name is from later releases.
- `Build/makefile`: `mpi_gnu_linux_64` uses `mpifort`, `-O2 -std=f2018
  -frecursive -fall-intrinsics -fopenmp`; `impi_intel_linux_64` uses
  `mpiifort -O2 -ipo -qopenmp` (classic ifort, no longer shipped by
  current oneAPI). `evac.o` is in `obj_mpi` for all targets.
- The makefile sets `-fallow-argument-mismatch` only when
  `Scripts/gnu_compmajorversion.sh` prints exactly `10`. A newer gfortran
  gets no such flag, so the setup script passes
  `GFORTRAN_OPTIONS=-fallow-argument-mismatch` on the make command line.
- `Build/<target>/make_fds.sh` just runs `make -j4 VPATH="../../Source" -f
  ../makefile <target>` from inside the target directory; the setup script
  does the same. The makefile calls `git describe --long`, so the build
  needs the git clone (not a tarball) and a clean tree.
- `Source/evac.f90` exists at the tag (777,930 bytes via the GitHub API).

Chosen: `mpi_gnu_linux_64` (gfortran + `mpifort`), because it does not need
classic ifort. Fallback: `TARGET=impi_intel_linux_64` with an older Stage.
Binary: `Build/mpi_gnu_linux_64/fds_mpi_gnu_linux_64`.

## Values to confirm on JURECA before step 2

| Item | Where | How |
|---|---|---|
| Module names (`GCC`, `ParaStationMPI`) and Stage | `TOOLCHAIN_MODULES`, `STAGES_MODULE` in `fds677_common.sh` | `module avail`, `module spider GCC`, `module spider ParaStationMPI`; `which gfortran mpifort` after loading |
| gfortran major version (flag logic) | `GFORTRAN_OPTIONS` | `gfortran --version`; set `""` if older than 10 |
| Partition (`dc-cpu` is a guess) | `#SBATCH --partition` in both `.sbatch`; `--partition` of the submit script | `sinfo -s`; check max wall time and cores per node (`NMPI` must fit one node, `--nodes=1`) |
| `srun --mpi=` plugin | env `SRUN_MPI` (empty = site default) | `srun --mpi=list`; set e.g. `export SRUN_MPI=pspmix` only if plain `srun` fails |
| Outbound access from login node to github.com | setup step 1 | else clone on the laptop and rsync the whole directory incl. `.git` to `$PROJECT/$USER/fds-6.7.7` |
| Files phase 3 needs in its directory | `imports` in `submit_ballroom.sh` (`.eff`, `.fed`) | README says `.eff` and `.fed`; to confirm on the first repeat (does it also want `.xyz`?) |
| `_evmc.csv` contents and `_evmc_info.out` | `rep01/` | first repeat: is it what `pyfds-evac` and the analysis expect |
| Repeats differ | `rep*/cvm2_ballroom_evmc.csv` | seed = wall clock; `fetch_ballroom.sh` compares sha256, and also compare the start times in each `run_record.txt` (millisecond) |
| Devices and fire slices skipped silently in phases 1 and 3 | `.out` of phase 1 and 3 | README "Keywords" |
| `EVACUATION=.TRUE.` holes open the visibility mesh | Smokeview, phase 1 | README "Keywords" |
| `&EXIT` behind a wall hole works | phase 1 `.out`, Smokeview | README "Keywords" |
| 1,000 agents placed at 1.0 persons/m2 in one attempt | phase 1 `.out` | README "Keywords" |
| Fuel warning ("not predefined") and yields | phase 2 `.out` | README "Keywords" |
| Phase 1 sanity before phase 2 | Smokeview | flow fields toward all four exits, no agent outside the walls, all agents placed |
| Wall times (`--wall-p1`, `--wall-p2`, `--wall-p3`, `--wall-fire`, `--wall-dx050`) | submit script | phase 2 default 8 h from the README estimate (about 65 core-hours, 3 h on 21 processes, range 35-130 core-hours); phase 1 (1 h), phase 3 (2 h), dx050 (1 h) are guesses, there is no estimate |

## Steps

1. Copy the scripts to JURECA (from the repo checkout on your machine):
   ```
   ssh jureca 'mkdir -p $HOME/cvm2-hpc'   # any directory you like
   rsync -av plans/b16-cvm2-ballroom/hpc/ jureca:cvm2-hpc/
   ```
   Check: `ssh jureca ls cvm2-hpc` lists the scripts.

2. Build (login node):
   ```
   ssh jureca
   jutil env activate -p cias-7
   echo $PROJECT                # expect /p/project1/cias-7
   cd ~/cvm2-hpc
   # edit TOOLCHAIN_MODULES / STAGES_MODULE in fds677_common.sh first
   bash setup_fds677_jsc.sh 2>&1 | tee setup_fds677.log
   ```
   Check: the last lines say `BUILD CHECKED`, with `Evac symbols: yes`;
   the manifest shows `git describe: FDS6.7.7-0-g...`, the commit, modules,
   compiler versions and the binary sha256. On failure read
   `$PROJECT/$USER/fds-6.7.7/build.log` and the "If the build fails" notes
   in `fds677_common.sh`; to rebuild, move `fds-6.7.7` aside (the script
   never deletes). Also confirm the 6.10.1 install is unchanged
   (`which fds` in a fresh login shell is the same as before).

3. Smoke test with one FDS+Evac guide example (the guide's decks are GPL;
   copy one to the cluster, outside the repo, e.g. `evac_example2*.fds`):
   ```
   cd ~/cvm2-hpc
   sbatch -n 1 -t 00:30:00 smoke_test.sbatch ~/guide-decks/evac_example2.fds 1
   squeue -u $USER
   ```
   (Use `-n N` and `N` as last argument if the example has N fire meshes.)
   Check: log `fds677-smoke-<jobid>.log` ends with `SMOKE TEST PASSED`;
   in the run directory, the `.out` file has `STOP: FDS completed
   successfully`, and `<CHID>_evac.csv` shows all agents evacuated. A
   failure message from the job is the verdict; FDS exit status 0 is not.

4. Optional first: stand-alone fire test on a short copy, then in full:
   ```
   python3 make_decks.py --t-end 10 --out short     # in plans/b16-cvm2-ballroom
   ```
   Copy `short/cvm2_ballroom_fire.fds` to the cluster and run
   `bash submit_ballroom.sh ... --fire-deck short/cvm2_ballroom_fire.fds
   --fire-label fire-test-short --wall-fire 00:30:00` (a label is never
   reused, so the full test later uses `fire-test`). The fire test costs
   the same as phase 2 if it runs to 1,200 s. Same for the phase 1 drill
   on the 0.5 m grid: `--dx050-deck cvm2_ballroom_evac_dx050.fds`.

5. Dry run of the real chain (submits nothing):
   ```
   bash submit_ballroom.sh --phase1-deck cvm2_ballroom_evac.fds \
        --phase2-deck cvm2_ballroom_evac_fed.fds \
        --phase3-deck cvm2_ballroom_evac_mc.fds --nmpi 21
   ```
   Check: 12 `WOULD RUN` lines: `phase1` (1 task); `phase2` (21 tasks,
   after `phase1`, imports `phase1:_evac.xyz`); `rep01`..`rep10` (1 task,
   each after `phase2`, imports `phase1:_evac.eff phase2:_evac.fed`).
   The script refuses a deck without its keyword or phase decks with
   different CHIDs. Check the wall times.

6. Submit, only with your go-ahead: the same command plus `--go`.
   Alternative, step by step: phase 1 alone, look at it in Smokeview, then
   phase 2, then the repeats, by hand:
   ```
   sbatch -n NMPI -t HH:MM:SS run_ballroom.sbatch DECK NMPI LABEL [SRC:SUFFIX ...]
   ```
   Check after each job: `ballroom-<jobid>.log` has `verdict: OK`;
   `<run dir>/run_record/run_record.txt` holds job id, mode, deck and
   binary sha256, node list, start, `fds launch` time to the millisecond,
   end, exit status. Judge each run from the `STOP: FDS completed
   successfully` line in `<CHID>.out` and no `Numerical Instability`;
   FDS exit status 0 proves nothing. A failed job cancels its dependents
   (`squeue`, `sacct -j <id> -o JobID,State,ExitCode,Elapsed`). FDS+Evac
   has no seed input (seed = wall clock), so the repeats cannot be
   reproduced by number. Nothing is staggered; **check that the ten
   `rep*/cvm2_ballroom_evmc.csv` files differ** (`fetch_ballroom.sh` does
   it by sha256) and read the launch times in the run records.

7. Fetch (from your machine; read-only on the cluster):
   ```
   bash plans/b16-cvm2-ballroom/hpc/fetch_ballroom.sh \
        ~/sciebo/fds-evac-data/cvm2-ballroom --dry-run
   bash plans/b16-cvm2-ballroom/hpc/fetch_ballroom.sh \
        ~/sciebo/fds-evac-data/cvm2-ballroom
   ```
   Check: `OK` for every run directory; `phase2/` holds the slices
   (`*.sf`), `.smv`, `.out`, `_hrr.csv`, `_devc.csv` and `run_record/`
   (pyFDS-Evac reads these, not the fire test's); each `rep*/` holds
   `*_evmc.csv`; the closing line says the `_evmc.csv` files all differ.
   Add `--with-eff-fed` for the `.eff`/`.fed`/`.xyz` files.

8. Record in the study page: FDS tag and commit from
   `build_manifest.txt`, modules and compiler, deck sha256 from each run
   record.
