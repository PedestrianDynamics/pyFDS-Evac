# FDS 6.7.7 + C/VM2 ballroom on JURECA: command sequence (#808)

Every command is run by hand. Nothing here has been run: JURECA was not
reachable and there is no FDS on the machine where the scripts were
written. Stop at the first failed check. Do not submit anything
(`--go`) without your own go-ahead.

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
| Evac meshes and MPI ranks | the evac deck | guide §8.1: how the evacuation mesh is attached to a rank when `NMPI` equals the number of fire meshes (`MPI_PROCESS` on the evac `&MESH`) |
| Files read by `EVACUATION_MC_MODE` | `rsync --exclude` list in `run_ballroom.sbatch` | guide §9.2; the copy keeps everything except slices, boundary, 3D, particle data, `.out`, `_evac.csv` |
| Seed of an MC repeat | the MC deck | guide §8: confirm repeats differ (compare `_evac.csv` of run01 and run02) |
| Wall times (`--wall-*`, defaults 2 h, 24 h, 12 h) | submit script | guesses; measure with the smoke test and the fire-only test |

## Steps

1. Copy the scripts to JURECA (from the repo checkout on your machine):
   ```
   ssh jureca 'mkdir -p $HOME/cvm2-hpc'   # any directory you like
   rsync -av plans/b16-cvm2-ballroom/hpc/ jureca:cvm2-hpc/
   ```
   Check: `ssh jureca ls cvm2-hpc` lists 7 files.

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

4. Dry run of the real chain (submits nothing), once the decks exist:
   ```
   bash submit_ballroom.sh --fire-deck cvm2_ballroom_fire.fds \
        --evac-deck cvm2_ballroom_evac.fds --mc-deck cvm2_ballroom_evac_mc.fds \
        --nmpi <number of fire meshes>
   ```
   Check: it prints 10 `WOULD RUN` lines: `fire-only`, `run01` (after
   `fire-only`), `run02`..`run10` (each after `run01`, with `run01` as
   FROM). Verify NMPI equals the number of fire meshes, and the wall times.
   The submit script refuses a fire deck without `NO_EVACUATION=.TRUE.` and
   an MC deck without `EVACUATION_MC_MODE=.TRUE.`.

5. Submit, only with your go-ahead: the same command plus `--go`.
   Alternative, step by step: submit `fire-only` alone, read it, then run 1,
   then the repeats, by hand:
   ```
   sbatch -n NMPI -t HH:MM:SS run_ballroom.sbatch DECK NMPI LABEL [FROM]
   ```
   Check after each job: `ballroom-<jobid>.log` has `verdict: OK`;
   `<run dir>/run_record/run_record.txt` holds job id, deck and binary
   sha256, node list, start, end, exit status; `build_manifest.txt` and the
   job script are copied beside it. After run 1 and each repeat, check the
   `STOP: FDS completed successfully` line in `<CHID>.out` yourself, the
   `.out` has no `Numerical Instability`, and `_evac.csv` ends with all
   1,000 agents out. A failed job cancels the jobs that depend on it
   (`squeue`, `sacct -j <id> -o JobID,State,ExitCode,Elapsed`).

6. Fetch (from your machine; read-only on the cluster):
   ```
   bash plans/b16-cvm2-ballroom/hpc/fetch_ballroom.sh \
        ~/sciebo/fds-evac-data/cvm2-ballroom --dry-run
   bash plans/b16-cvm2-ballroom/hpc/fetch_ballroom.sh \
        ~/sciebo/fds-evac-data/cvm2-ballroom
   ```
   Check: the closing list shows `OK` for every run directory; slices
   (`*.sf`), `*_evac.csv`, `*.out` and `run_record/` are present. Add
   `--with-eff-fed` for the evacuation `.eff`/`.fed` files.

7. Record in the study page: FDS tag and commit from
   `build_manifest.txt`, modules and compiler, deck sha256 from each run
   record.
