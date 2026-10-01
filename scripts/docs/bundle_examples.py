"""Build the downloadable input zips of the example pages.

Reads ``site/data/examples.toml`` and writes, for each example:

- ``site/static/downloads/<zip>``: the files the page uses, in the
  repository layout, plus ``README.txt``, ``requirements.txt`` and
  ``LICENSE``;
- one entry in ``site/data/example_bundles.json``: size, sha256, commit and
  package versions, which the ``example-files`` shortcode shows.

The README's versions come from ``git``, ``pyproject.toml`` and
``uv.lock``, so they match the commit the zip is built from. The zips are
reproducible: sorted entries, fixed timestamps and permissions. Two builds
of the same commit give the same bytes. Run from anywhere:

    uv run python scripts/docs/bundle_examples.py

It needs ``git`` and ``uv`` (for ``uv export``) on the PATH.
"""

import argparse
import hashlib
import io
import json
import subprocess
import textwrap
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "site" / "data" / "examples.toml"
OUT_DIR = ROOT / "site" / "static" / "downloads"
FACTS = ROOT / "site" / "data" / "example_bundles.json"
REPO_URL = "https://github.com/PedestrianDynamics/pyFDS-Evac"
SITE_URL = "https://pedestriandynamics.org/pyFDS-Evac/"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
# Packages whose versions the README lists; all come from uv.lock.
KEY_PACKAGES = (
    "jupedsim",
    "pedpy",
    "fdsreader",
    "fdsvismap",
    "numpy",
    "shapely",
    "matplotlib",
    "pandas",
)
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
WRAP = 72


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit() -> dict:
    """The commit the zips are built from, and whether tracked files differ."""
    return {
        "sha": _git("rev-parse", "HEAD"),
        "date": _git("show", "-s", "--format=%cs", "HEAD"),
        "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
    }


def _locked_versions() -> dict:
    """Name -> version (or git revision) of every package in uv.lock."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    versions = {}
    for package in lock["package"]:
        git = package.get("source", {}).get("git")
        if git:
            versions[package["name"]] = f"git {git.rsplit('#', 1)[-1][:7]}"
        else:
            versions[package["name"]] = package.get("version", "?")
    return versions


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def _requirements(sha: str, extra: list[str], versions: dict) -> str:
    """Pinned requirements from uv.lock plus pyFDS-Evac itself at ``sha``."""
    exported = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-hashes",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    header = (
        "# Pinned from uv.lock of pyFDS-Evac at commit "
        f"{sha[:7]}.\n# Install with: pip install -r requirements.txt\n"
    )
    lines = [f"{name}=={versions[name]}" for name in extra]
    lines.append(f"pyfds-evac @ git+{REPO_URL}@{sha}")
    return header + exported.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


def _para(text: str, indent: str = "", hanging: str = "") -> str:
    return textwrap.fill(
        " ".join(text.split()),
        WRAP,
        initial_indent=indent,
        subsequent_indent=hanging or indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _readme(example: dict, commit: dict, versions: dict, entries: list) -> str:
    project = _project()
    title = f"pyFDS-Evac example: {example['title']}"
    width = max(len(path) for path, _ in entries)
    contents = "\n".join(f"  {path:<{width}}  {about}" for path, about in entries)
    built = f"{commit['sha']} ({commit['date']})"
    if commit["dirty"]:
        built += ", with uncommitted changes"
    package_lines = [f"  pyFDS-Evac   {project['version']}, git commit {built}"]
    package_lines.append(f"  Python       {project['requires-python']}")
    for name in (*KEY_PACKAGES, *example["extra_packages"]):
        package_lines.append(f"  {name:<12} {versions[name]}")
    fds = example["fds"] or "not needed"
    package_lines.append(f"  FDS          {fds}")

    steps = []
    for number, (what, commands) in enumerate(example["steps"], start=2):
        block = "\n".join(f"     {line}" for line in commands)
        steps.append(_para(f"{number}. {what}:", hanging="   ") + "\n\n" + block)
    runtime = [f"  pyFDS-Evac: {example['evac_runtime']}"]
    if example["fds_runtime"]:
        runtime.insert(0, f"  FDS: {example['fds_runtime']}")
    expected = "\n".join(f"  {line}" for line in example["expected"])

    sections = [
        f"{title}\n{'=' * len(title)}",
        _para(example["summary"]),
        f"Page: {SITE_URL}{example['page']}",
        _para(
            "Run every command from this folder, the folder that holds "
            "this README.txt. The files keep the layout of the pyFDS-Evac "
            "repository, so the commands are the ones on the page, with "
            "python instead of uv run python."
        ),
        f"Contents\n--------\n{contents}",
        "Versions\n--------\n"
        + _para(
            "The zip was built from this commit. requirements.txt pins "
            "every Python package to the version in its uv.lock."
        )
        + "\n\n"
        + "\n".join(package_lines),
        "Run it\n------\n"
        + _para(
            "The commands are for a POSIX shell (Linux, macOS; on Windows, "
            "WSL or Git Bash)."
        )
        + "\n\n"
        + _para("1. Install pyFDS-Evac and the pinned packages:")
        + "\n\n     python -m venv .venv\n"
        + "     source .venv/bin/activate    # Windows: .venv\\Scripts\\activate\n"
        + "     pip install -r requirements.txt\n\n"
        + "\n\n".join(steps),
        "Runtime\n-------\n" + "\n".join(runtime),
        "Expected result\n---------------\n"
        + _para(
            f"The page shows these lines. They were produced at commit "
            f"{example['results_commit']} with Python "
            f"{example['results_python']} on {example['results_machine']}"
            + (f", from FDS output of {example['fds']}" if example["fds"] else "")
            + "."
        )
        + f"\n\n{expected}\n\n"
        + _para(example["expected_note"]),
        "Licence\n-------\n"
        + _para(
            "Code (the .py files): MIT, see LICENSE. FDS decks, scenario "
            f"files and geometry: CC-BY-4.0, {CC_BY}. Attribution: "
            f"pyFDS-Evac, {REPO_URL}."
        ),
        _para("pyFDS-Evac is research software, provided without warranty."),
    ]
    return "\n\n".join(sections) + "\n"


def _zip_bytes(prefix: str, members: dict[str, bytes]) -> bytes:
    """A zip of ``members`` under ``prefix/``, identical for identical input."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(f"{prefix}/{name}", date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name], compresslevel=9)
    return buffer.getvalue()


def build_one(name: str, example: dict, commit: dict, versions: dict) -> tuple:
    """Return the zip bytes and the facts of one example."""
    members = {path: (ROOT / path).read_bytes() for path, _ in example["files"]}
    entries = [
        ("README.txt", "this file"),
        ("LICENSE", "MIT licence of the code"),
        ("requirements.txt", "pinned Python packages, from uv.lock"),
        *[(path, about) for path, about in example["files"]],
    ]
    members["README.txt"] = _readme(example, commit, versions, entries).encode()
    members["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    members["requirements.txt"] = _requirements(
        commit["sha"], example["extra_packages"], versions
    ).encode()
    data = _zip_bytes(Path(example["zip"]).stem, members)
    facts = {
        "zip": example["zip"],
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "commit": commit["sha"],
        "dirty": commit["dirty"],
        "entries": [[path, about] for path, about in entries],
    }
    return data, facts


def build(out_dir: Path = OUT_DIR, facts_file: Path = FACTS) -> dict:
    """Write every zip and the facts file; return the facts."""
    spec = tomllib.loads(SPEC.read_text())
    commit = _commit()
    versions = _locked_versions()
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = {}
    for name, example in spec.items():
        data, facts[name] = build_one(name, example, commit, versions)
        (out_dir / example["zip"]).write_bytes(data)
    facts_file.parent.mkdir(parents=True, exist_ok=True)
    facts_file.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n")
    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--facts", type=Path, default=FACTS)
    args = parser.parse_args()
    for name, item in build(args.out_dir, args.facts).items():
        size = item["bytes"] / 1000
        print(f"wrote {args.out_dir / item['zip']} ({size:.0f} kB) for {name}")


if __name__ == "__main__":
    main()
