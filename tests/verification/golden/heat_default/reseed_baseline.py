"""Rewrite the heat FED baseline after a change of per-agent seeding.

``make_baseline.py`` stays as it ran at 76c9a76 and cannot be rerun (see the
README). When per-agent draws are seeded differently, the agents walk to other
target points, so only the ``x`` and ``y`` columns of ``fed_history.csv`` may
change; the field depends on time alone, so every dose column must not.

This runs the run of ``test_unclothed_outputs_match_the_baseline`` at the
current checkout and rewrites the baseline only if every column other than
``x`` and ``y`` matches the committed one. Run it from the repository root in
a fresh interpreter, since JuPedSim numbers agents per process::

    PYTHONPATH=. python tests/verification/golden/heat_default/reseed_baseline.py
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "verification"))

import test_heat_endpoint_coupled as coupled  # noqa: E402

MAY_CHANGE = {"x", "y"}


def _read(path: pathlib.Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _check_unchanged(header, rows, old_header, old_rows) -> None:
    if header != old_header or len(rows) != len(old_rows):
        sys.exit("header or row count changed; not rewriting the baseline")
    for i, (got, want) in enumerate(zip(rows, old_rows)):
        changed = [
            key
            for key in want
            if key not in MAY_CHANGE and not coupled._same_value(got[key], want[key])
        ]
        if changed:
            sys.exit(f"row {i}: {changed} changed; not rewriting the baseline")


def main() -> None:
    result = coupled._run(
        coupled._table_63_21_field, None, run_s=30.0, clothing="unclothed"
    )
    with tempfile.TemporaryDirectory() as tmp:
        written = pathlib.Path(tmp) / "fed.csv"
        try:
            header, rows = coupled._csv_rows(result, written)
            manifest = coupled._normalised_manifest(result.manifest_file)
        finally:
            result.cleanup()
        old_header, old_rows = _read(HERE / "fed_history.csv")
        _check_unchanged(header, rows, old_header, old_rows)
        (HERE / "fed_history.csv").write_bytes(written.read_bytes())
    # Checked apart by the test; the baseline predates them (#290).
    manifest.pop("heat_clothing")
    manifest.pop("outcome")
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
