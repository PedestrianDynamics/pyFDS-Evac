# agent_scalars Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write an optional `agent_scalars(frame, id, fed, speed)` side table into the JuPedSim `.sqlite` so fds-viewer can colour agents by FED or speed.

**Architecture:** A small pure function `write_agent_scalars(sqlite_path, fed_history)` opens an already-written JuPedSim sqlite, reads `fps` from its `metadata` table, and inserts one row per FED-history sample mapped to `frame = round(time_s * fps)` with `speed = base_speed * speed_factor`. It is called from `run.py` right after the sqlite is copied to `--output-sqlite`, guarded on FED history being present. The base JuPedSim schema is never modified.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, pytest. This is the producer side; the fds-viewer consumer is a separate plan.

**Branch:** `feat/agent-scalars` (already created from `main`).

**Spec:** `PedestrianDynamics/fds-viewer` → `docs/superpowers/specs/2026-06-07-fds-viewer-agent-overlay-design.md` (§Data contract, §Producer).

---

### Task 1: `write_agent_scalars` core writer

**Files:**
- Create: `pyfds_evac/core/agent_scalars.py`
- Test: `tests/test_agent_scalars.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_scalars.py
import sqlite3
from pathlib import Path

from pyfds_evac.core.agent_scalars import write_agent_scalars


def _make_base_sqlite(path: Path, fps: float = 10.0) -> None:
    """Minimal JuPedSim-shaped sqlite: metadata + trajectory_data only."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("INSERT INTO metadata VALUES('fps', ?)", (str(fps),))
    con.execute(
        "CREATE TABLE trajectory_data("
        "frame INTEGER, id INTEGER, pos_x REAL, pos_y REAL, ori_x REAL, ori_y REAL)"
    )
    con.commit()
    con.close()


def test_writes_frame_id_fed_speed(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db, fps=10.0)
    fed_history = [
        {"time_s": 0.0, "agent_id": 1, "fed_cumulative": 0.0,
         "base_speed": 1.2, "speed_factor": 1.0},
        {"time_s": 1.0, "agent_id": 1, "fed_cumulative": 0.25,
         "base_speed": 1.2, "speed_factor": 0.5},
    ]
    write_agent_scalars(db, fed_history)

    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT frame, id, fed, speed FROM agent_scalars ORDER BY frame"
    ).fetchall()
    con.close()
    assert rows == [(0, 1, 0.0, 1.2), (10, 1, 0.25, 0.6)]


def test_noop_on_empty_history(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db)
    write_agent_scalars(db, [])
    con = sqlite3.connect(db)
    exists = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_scalars'"
    ).fetchone()
    con.close()
    assert exists is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_scalars.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pyfds_evac.core.agent_scalars'`

- [ ] **Step 3: Write minimal implementation**

```python
# pyfds_evac/core/agent_scalars.py
"""Write an optional agent_scalars side table into a JuPedSim sqlite.

The base JuPedSim schema (trajectory_data, metadata, geometry, frame_data) is
never touched, so jupedsim replay and Web-Based-JuPedSim still read the file.
fds-viewer reads agent_scalars to colour agents by FED or speed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path


def write_agent_scalars(
    sqlite_path: str | Path, fed_history: Iterable[Mapping[str, object]]
) -> None:
    """Populate agent_scalars(frame, id, fed, speed) in an existing sqlite.

    frame = round(time_s * fps), with fps read from the metadata table. speed =
    base_speed * speed_factor. No-op when fed_history is empty.
    """
    rows = list(fed_history)
    if not rows:
        return

    con = sqlite3.connect(str(sqlite_path))
    try:
        fps = float(
            con.execute(
                "SELECT value FROM metadata WHERE key = 'fps'"
            ).fetchone()[0]
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_scalars("
            "frame INTEGER NOT NULL, id INTEGER NOT NULL, fed REAL, speed REAL)"
        )
        con.executemany(
            "INSERT INTO agent_scalars(frame, id, fed, speed) VALUES (?, ?, ?, ?)",
            [_scalar_row(r, fps) for r in rows],
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS agent_scalars_idx "
            "ON agent_scalars(frame, id)"
        )
        con.commit()
    finally:
        con.close()


def _scalar_row(row: Mapping[str, object], fps: float) -> tuple[int, int, float, float]:
    frame = round(float(row["time_s"]) * fps)
    agent_id = int(row["agent_id"])
    fed = float(row["fed_cumulative"])
    speed = float(row["base_speed"]) * float(row["speed_factor"])
    return (frame, agent_id, fed, speed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_scalars.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pyfds_evac/core/agent_scalars.py tests/test_agent_scalars.py
git commit -m "feat(core): write optional agent_scalars side table into sqlite"
```

---

### Task 2: Wire writer into the `--output-sqlite` path

**Files:**
- Modify: `run.py` (import near the other `pyfds_evac.core` imports; call site at the `--output-sqlite` block, currently `run.py:465-468`)
- Test: `tests/test_agent_scalars.py` (add integration-style guard test)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_agent_scalars.py
def test_output_sqlite_path_calls_writer(tmp_path, monkeypatch):
    """run.py writes agent_scalars into the copied sqlite when FED history exists."""
    import run

    src = tmp_path / "src.sqlite"
    _make_base_sqlite(src, fps=10.0)
    dest = tmp_path / "out.sqlite"

    captured = {}

    def fake_write(path, history):
        captured["path"] = Path(path)
        captured["n"] = len(list(history))

    monkeypatch.setattr(run, "write_agent_scalars", fake_write)
    run._maybe_write_agent_scalars(
        dest, src, [{"time_s": 0.0, "agent_id": 1, "fed_cumulative": 0.0,
                     "base_speed": 1.2, "speed_factor": 1.0}]
    )
    assert captured["path"] == dest.resolve()
    assert captured["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_scalars.py::test_output_sqlite_path_calls_writer -q`
Expected: FAIL with `AttributeError: module 'run' has no attribute '_maybe_write_agent_scalars'`

- [ ] **Step 3: Add the import and helper, and call it from the output block**

Add the import alongside the existing `from pyfds_evac...` imports in `run.py`:

```python
from pyfds_evac.core.agent_scalars import write_agent_scalars
```

Add this helper near the other `_write_*` helpers in `run.py`:

```python
def _maybe_write_agent_scalars(output_path, _src, fed_history) -> None:
    """Write the agent_scalars side table into the copied sqlite if FED ran."""
    if not fed_history:
        return
    write_agent_scalars(pathlib.Path(output_path).resolve(), fed_history)
```

Change the `--output-sqlite` block (currently `run.py:465-468`) from:

```python
    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)
```

to:

```python
    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)
        _maybe_write_agent_scalars(output_path, result.sqlite_file, result.fed_history)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_scalars.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add run.py tests/test_agent_scalars.py
git commit -m "feat(run): populate agent_scalars when writing --output-sqlite"
```

---

### Task 3: End-to-end check against a real demo run

**Files:**
- Test: `tests/test_agent_scalars.py` (add a real-sqlite frame-alignment assertion)

This guards the contract that `agent_scalars.frame` values are a subset of `trajectory_data.frame` (so the viewer can align them).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_agent_scalars.py
def test_frames_align_with_trajectory(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db, fps=10.0)
    con = sqlite3.connect(db)
    con.executemany(
        "INSERT INTO trajectory_data VALUES (?, ?, 0, 0, 1, 0)",
        [(f, 1) for f in range(0, 21)],
    )
    con.commit()
    con.close()

    write_agent_scalars(
        db,
        [{"time_s": 0.0, "agent_id": 1, "fed_cumulative": 0.0,
          "base_speed": 1.0, "speed_factor": 1.0},
         {"time_s": 2.0, "agent_id": 1, "fed_cumulative": 0.1,
          "base_speed": 1.0, "speed_factor": 1.0}],
    )

    con = sqlite3.connect(db)
    traj_frames = {r[0] for r in con.execute("SELECT frame FROM trajectory_data")}
    scalar_frames = {r[0] for r in con.execute("SELECT frame FROM agent_scalars")}
    con.close()
    assert scalar_frames.issubset(traj_frames)
    assert scalar_frames == {0, 20}
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `uv run pytest tests/test_agent_scalars.py::test_frames_align_with_trajectory -q`
Expected: PASS (the writer already produces aligned frames; this locks the contract).

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `uv run pytest -q`
Expected: PASS (previous count + 4 new tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_scalars.py
git commit -m "test(core): lock agent_scalars frame alignment with trajectory_data"
```

---

### Task 4: Document the new output + regenerate the demo sqlite

**Files:**
- Modify: `README.md` (output/visualisation section)
- Modify: `docs/usage.md` (`--output-sqlite` row in the scenario-export table)

Per project rule, every new feature updates `README.md` (and the paper once the viewer side ships — defer the paper edit to the consumer plan).

- [ ] **Step 1: Update `docs/usage.md`**

Change the `--output-sqlite` row in the "Scenario selection and export" table to:

```markdown
| `--output-sqlite PATH` | Copy the JuPedSim trajectory SQLite here. When FED is computed, also writes an optional `agent_scalars(frame, id, fed, speed)` side table (base JuPedSim schema untouched) so fds-viewer can colour agents by FED or speed. |
```

- [ ] **Step 2: Add a short note to `README.md`**

Add under the visualisation/output documentation a sentence:

```markdown
When `--output-sqlite` is combined with FED computation, the SQLite also
carries an `agent_scalars(frame, id, fed, speed)` table consumed by
[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) to colour
agents by FED dose or speed. The base JuPedSim schema is unchanged.
```

- [ ] **Step 3: Verify the real end-to-end output once**

Run:

```bash
uv run python run.py --scenario assets/demo/config_full.json --fds-dir fds_data/demo \
  --vis-cache fds_data/demo/vismap_cache.npz --output-sqlite demo4.sqlite \
  --output-fed-history fed.csv
sqlite3 demo4.sqlite "SELECT count(*), min(frame), max(frame) FROM agent_scalars;"
```

Expected: a non-zero row count with `min(frame)=0` and `max(frame)` near `max(trajectory_data.frame)`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/usage.md
git commit -m "docs: document agent_scalars side table in --output-sqlite"
```

---

## Self-Review

- **Spec coverage:** Data-contract table (Task 1), producer integration on `--output-sqlite` (Task 2), frame-mapping `round(time_s*fps)` and `speed=base_speed*speed_factor` (Task 1 `_scalar_row`), optionality when FED off (Task 1 `test_noop_on_empty_history`), frame alignment (Task 3), docs (Task 4). Consumer side is intentionally out of scope (separate plan).
- **Placeholders:** none — every step has full code/commands.
- **Type consistency:** `write_agent_scalars(sqlite_path, fed_history)` and `_scalar_row(row, fps)` signatures are used identically across Tasks 1–3; `run._maybe_write_agent_scalars(output_path, _src, fed_history)` matches its call site in Task 2.

## Next plan

After this lands, the consumer plan in the `fds-viewer` fork (`feat/agent-overlay`): `trajectory-reader.js` (sql.js), `agent-overlay.js` (instanced spheres, colour-by Speed/FED), persistent-overlay wiring in `output-page.js`, and the shared-clock time sync.
