"""Helper of ``scripts/release_check.sh``: run the documented commands and report.

Standard library only (Python 3.11 or newer, for ``tomllib``). Subcommands:

``versions``
    The supported Python versions: the ``Programming Language :: Python ::
    3.N`` classifiers of ``pyproject.toml`` that satisfy ``requires-python``.
``external-skips``
    Fail when a test marked ``external_data`` was skipped, from a pytest
    JUnit XML file and the node IDs that ``pytest -m external_data
    --collect-only -q`` lists.
``docs``
    Run the steps of ``scripts/release_check.toml``, page by page, and check
    the exit codes and expected output lines.
``bundles``
    Unpack each download bundle of ``site/data/examples.toml``, install its
    ``requirements.txt`` and follow its ``README.txt`` up to the FDS step.
``report``
    Print the results file as a Markdown table and write it to a file.

Every subcommand that runs something appends one tab-separated line per
check to the results file: gate, page, step, status, seconds, detail.
Statuses: PASS, FAIL, STALE (exit code fine, output differs on a page that
an open issue already lists), MANUAL (not run: needs FDS, the GUI or data
that is not available), SKIP (not run: an earlier step of the page failed,
or the mode excludes it).
"""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "release_check.toml"
EXAMPLES = ROOT / "site" / "data" / "examples.toml"
TRACEBACK = "Traceback (most recent call last)"
FDS_STEP = re.compile(r"(^|[\s;(&|])(fds|mpiexec)\s")
ORDER = {"FAIL": 0, "STALE": 1, "MANUAL": 2, "SKIP": 3, "PASS": 4}


# --- results file -----------------------------------------------------------


def record(results: Path, gate: str, page: str, step: str, status: str, secs, detail):
    line = "\t".join(
        [gate, page, step, status, f"{secs:.0f}", " ".join(str(detail).split())]
    )
    with results.open("a") as f:
        f.write(line + "\n")
    print(f"[{status:<6}] {gate} / {page} / {step}  {detail}", flush=True)


# --- versions ---------------------------------------------------------------


def _version_ok(version: tuple, spec: str) -> bool:
    for clause in filter(None, (c.strip() for c in spec.split(","))):
        op, number = re.match(r"(>=|<=|==|!=|>|<)\s*([\d.]+)", clause).groups()
        bound = tuple(int(p) for p in number.split(".")[:2])
        checks = {
            ">=": version >= bound,
            "<=": version <= bound,
            ">": version > bound,
            "<": version < bound,
            "==": version == bound,
            "!=": version != bound,
        }
        if not checks[op]:
            return False
    return True


def cmd_versions(_args) -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    found = []
    for classifier in project.get("classifiers", []):
        match = re.fullmatch(r"Programming Language :: Python :: 3\.(\d+)", classifier)
        if match and _version_ok((3, int(match[1])), project["requires-python"]):
            found.append(f"3.{match[1]}")
    if not found:
        sys.exit("no Python 3.N classifier satisfies requires-python")
    print(" ".join(found))
    return 0


# --- external_data skips ----------------------------------------------------


def _junit_cases(junit: Path):
    for case in ET.parse(junit).getroot().iter("testcase"):
        yield case


def cmd_external_skips(args) -> int:
    ids = [
        line.strip()
        for line in args.ids.read_text().splitlines()
        if "::" in line and not line.startswith(" ")
    ]
    wanted = {(i.split("::")[0], i.split("::")[-1]) for i in ids}
    totals = {"passed": 0, "failed": 0, "skipped": 0}
    skipped_external = []
    for case in _junit_cases(args.junit):
        outcome = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        totals[outcome] += 1
        key = (case.get("file", ""), case.get("name", ""))
        if outcome == "skipped" and key in wanted:
            reason = case.find("skipped").get("message", "")
            skipped_external.append(f"{key[0]}::{key[1]} ({reason})")
    summary = (
        f"{totals['passed']} passed, {totals['failed']} failed or errors, "
        f"{totals['skipped']} skipped, {len(ids)} external_data collected"
    )
    status = "PASS" if args.pytest_rc == 0 else "FAIL"
    if args.pytest_rc not in (0, 1):
        summary += f"; pytest exit {args.pytest_rc}"
    if skipped_external:
        status = "FAIL"
        summary += f"; {len(skipped_external)} external_data skipped: " + "; ".join(
            skipped_external[:5]
        )
    if not ids:
        status = "FAIL"
        summary += "; no external_data test collected"
    record(
        args.results,
        "tests",
        f"Python {args.python}",
        "pytest -rs",
        status,
        args.seconds,
        summary,
    )
    return 0 if status == "PASS" else 1


# --- running one step -------------------------------------------------------


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        os.killpg(proc.pid, signal.SIGKILL)


def run_shell(script: str, cwd: Path, env: dict, timeout: float, log: Path):
    """Run ``script`` with bash in its own process group; return (rc, output, secs).

    rc is None on a timeout; the whole group is killed, so the worker
    processes of a script die with it.
    """
    start = time.monotonic()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as out:
        out.write(f"$ cd {cwd}\n{script}\n----\n")
        out.flush()
        proc = subprocess.Popen(
            ["bash", "-c", script],
            cwd=cwd,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            rc = proc.wait(timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            rc = None
    output = log.read_text(errors="replace").split("\n----\n", 1)[-1]
    return rc, output, time.monotonic() - start


def _norm(text: str) -> str:
    return " ".join(text.split())


def missing_lines(expected: list[str], output: str) -> list[str]:
    flat = _norm(output)
    return [line for line in expected if _norm(line) not in flat]


def _last_line(output: str) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return lines[-1][:200] if lines else "(no output)"


def judge(step: dict, rc, output: str, secs: float, timeout: float):
    """Return (status, detail) of one finished step."""
    if rc is None:
        return "FAIL", f"timeout after {timeout:.0f} s"
    exit_ok = step.get("exit_ok", [0])
    if rc == 2 and 2 not in exit_ok:
        return "FAIL", "exit 2 (incomplete run), the page expects completion"
    if rc not in exit_ok:
        return "FAIL", f"exit {rc}: {_last_line(output)}"
    if TRACEBACK in output and not step.get("traceback_ok", False):
        return "FAIL", f"traceback in output: {_last_line(output)}"
    missing = missing_lines(step.get("expect", []), output)
    if missing:
        return "FAIL", "missing: " + " | ".join(missing)
    stale = missing_lines(step.get("expect_stale", []), output)
    if stale:
        issue = step.get("stale", "?")
        return "STALE", f"#{issue}; missing: " + " | ".join(stale)
    note = f"exit {rc}"
    if step.get("stored_runs"):
        note += f"; analysis of stored runs {step['stored_runs']}"
    return "PASS", note


# --- docs -------------------------------------------------------------------


def _clone_copy(src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst``; a copy-on-write clone where the OS has one."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    flag = ["-c"] if sys.platform == "darwin" else ["--reflink=auto"]
    done = subprocess.run(["cp", "-R", *flag, str(src), str(dst)], check=False)
    if done.returncode != 0:
        shutil.copytree(src, dst, symlinks=True)


def _bundle_expected() -> dict:
    return {
        k: v.get("expected", []) for k, v in tomllib.loads(EXAMPLES.read_text()).items()
    }


def _step_applies(step: dict, mode: str) -> bool:
    return step.get("mode", "all") in ("all", mode)


def _prepare_data(page: dict, mode: str, data: Path, work: Path) -> str:
    """Copy the page's data into ``work``; return the first missing source."""
    entries = page.get("copy", []) + page.get(f"copy_{mode}", [])
    for dest, src in entries:
        source = data / src
        if not source.exists():
            return str(source)
        _clone_copy(source, work / dest)
    return ""


def _step_env(base: dict, page: dict, work: Path) -> dict:
    env = dict(base)
    env["WORK"] = str(work)
    for key, value in page.get("env", {}).items():
        env[key] = os.path.expandvars(value.replace("$WORK", str(work)))
    return env


def run_page(page: dict, args, base_env: dict, expected: dict) -> None:
    name = page["name"]
    work = args.work / name
    work.mkdir(parents=True, exist_ok=True)
    missing = _prepare_data(page, args.mode, args.data, work)
    blocked = f"data missing: {missing}" if missing else ""
    env = _step_env(base_env, page, work)
    for step in page["step"]:
        label = step["name"]
        if not _step_applies(step, args.mode):
            continue
        if step.get("manual"):
            record(args.results, "docs", name, label, "MANUAL", 0, step["manual"])
            continue
        if blocked:
            record(args.results, "docs", name, label, "SKIP", 0, blocked)
            continue
        if step.get("expect_bundle"):
            step = {
                **step,
                "expect": step.get("expect", []) + expected[step["expect_bundle"]],
            }
        timeout = float(step.get("timeout", 600))
        log = args.logs / f"{name}__{re.sub(r'[^A-Za-z0-9]+', '_', label)}.log"
        cwd = args.repo / step.get("cwd", ".")
        rc, output, secs = run_shell(step["run"], cwd, env, timeout, log)
        status, detail = judge(step, rc, output, secs, timeout)
        record(args.results, "docs", name, label, status, secs, detail)
        if status == "FAIL" and step.get("blocks", True):
            blocked = f"after the failure of '{label}'"


def cmd_docs(args) -> int:
    manifest = tomllib.loads(args.manifest.read_text())
    expected = _bundle_expected()
    base_env = dict(os.environ)
    base_env.update({"REPO": str(args.repo), "FDS_EVAC_DATA": str(args.data)})
    for page in manifest["page"]:
        if args.only and page["name"] not in args.only:
            continue
        run_page(page, args, base_env, expected)
    return 0


# --- bundles ----------------------------------------------------------------


def readme_steps(readme: str) -> list[tuple[int, str, str]]:
    """The numbered steps of the README's "Run it" section.

    Returns (number, title, commands) per step. Step 1, the installation,
    is left out: the bundles gate installs requirements.txt with uv.
    """
    section = readme.split("Run it\n------\n", 1)[1].split("\nRuntime\n-------\n", 1)[0]
    steps = []
    for chunk in re.split(r"\n(?=\d+\. )", section):
        number = re.match(r"(\d+)\. ", chunk)
        if not number or number[1] == "1":
            continue
        title, _, body = chunk.partition("\n\n")
        commands = "\n".join(
            line[5:] for line in body.splitlines() if line.startswith("     ")
        )
        title = " ".join(title.split()[1:])
        steps.append((int(number[1]), title, commands))
    return steps


def _pushed(repo: Path) -> bool:
    out = subprocess.run(
        ["git", "branch", "-r", "--contains", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(out.stdout.strip())


def _install_bundle(folder: Path, args, env: dict, log: Path):
    requirements = folder / "requirements.txt"
    note = "requirements.txt as built"
    if not _pushed(args.repo):
        text = re.sub(
            r"^pyfds-evac @ git\+\S+$",
            f"pyfds-evac @ file://{args.repo}",
            requirements.read_text(),
            flags=re.M,
        )
        requirements.write_text(text)
        note = "commit not on the remote: pyfds-evac installed from the local clone"
    script = (
        f"uv venv -q --python {args.python} .venv && "
        "uv pip install -q --python .venv/bin/python -r requirements.txt"
    )
    rc, output, secs = run_shell(script, folder, env, 1800, log)
    return rc, output, secs, note


def run_bundle(key: str, example: dict, args, env: dict, overrides: dict) -> None:
    zip_path = args.repo / "site" / "static" / "downloads" / example["zip"]
    if not zip_path.exists():
        record(
            args.results, "bundles", key, "unzip", "FAIL", 0, f"{zip_path} not built"
        )
        return
    target = args.work / "bundles" / key
    shutil.rmtree(target, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target)
    folder = target / Path(example["zip"]).stem
    log = args.logs / f"bundle_{key}__install.log"
    rc, output, secs, note = _install_bundle(folder, args, env, log)
    if rc != 0:
        record(
            args.results,
            "bundles",
            key,
            "1. install (uv)",
            "FAIL",
            secs,
            f"exit {rc}: {_last_line(output)}",
        )
        return
    record(args.results, "bundles", key, "1. install (uv)", "PASS", secs, note)
    steps = readme_steps((folder / "README.txt").read_text())
    reached_fds = False
    for number, title, commands in steps:
        label = f"{number}. {title[:60]}"
        if FDS_STEP.search(commands):
            record(
                args.results, "bundles", key, label, "MANUAL", 0, "FDS step: stop here"
            )
            reached_fds = True
            break
        step = dict(overrides.get(key, {}).get(str(number), {}))
        log = args.logs / f"bundle_{key}__step{number}.log"
        script = f"source .venv/bin/activate\n{commands}"
        rc, output, secs = run_shell(
            script, folder, env, float(step.get("timeout", 900)), log
        )
        status, detail = judge(step, rc, output, secs, float(step.get("timeout", 900)))
        record(args.results, "bundles", key, label, status, secs, detail)
        if status == "FAIL":
            return
    if reached_fds:
        return
    missing = missing_lines(example.get("expected", []), _bundle_output(args.logs, key))
    status = "FAIL" if missing else "PASS"
    detail = (
        "missing: " + " | ".join(missing) if missing else "README expected lines found"
    )
    record(args.results, "bundles", key, "expected result", status, 0, detail)


def _bundle_output(logs: Path, key: str) -> str:
    return "\n".join(
        p.read_text(errors="replace")
        for p in sorted(logs.glob(f"bundle_{key}__step*.log"))
    )


def cmd_bundles(args) -> int:
    examples = tomllib.loads(EXAMPLES.read_text())
    overrides = tomllib.loads(args.manifest.read_text()).get("bundle", {})
    home = args.work / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # The README steps write to $HOME/...; keep them out of the real home,
    # but keep uv's cache.
    env.setdefault("UV_CACHE_DIR", _uv_cache_dir())
    env["HOME"] = str(home)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    for key, example in examples.items():
        if args.only and key not in args.only:
            continue
        run_bundle(key, example, args, env, overrides)
    return 0


def _uv_cache_dir() -> str:
    out = subprocess.run(
        ["uv", "cache", "dir"], capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


# --- report -----------------------------------------------------------------


def _rows(results: Path) -> list[list[str]]:
    if not results.exists():
        return []
    return [line.split("\t") for line in results.read_text().splitlines() if line]


def _worst(statuses) -> str:
    ranked = sorted(statuses, key=lambda s: ORDER.get(s, 0))
    real = [s for s in ranked if s != "SKIP"] or ranked
    return real[0] if real else "PASS"


def cmd_report(args) -> int:
    rows = _rows(args.results)
    pages: dict[tuple, list[str]] = {}
    for gate, page, _step, status, *_ in rows:
        pages.setdefault((gate, page), []).append(status)
    lines = [f"# Release check: {args.title}", "", "## Per page", ""]
    lines += ["| Gate | Page | Result | Checks |", "|---|---|---|---|"]
    for (gate, page), statuses in pages.items():
        counts = ", ".join(f"{s} {statuses.count(s)}" for s in ORDER if s in statuses)
        lines.append(f"| {gate} | {page} | **{_worst(statuses)}** | {counts} |")
    lines += ["", "## Per check", "", "| Gate | Page | Step | Result | s | Detail |"]
    lines.append("|---|---|---|---|---|---|")
    for gate, page, step, status, secs, detail in rows:
        detail = detail.replace("|", "\\|")
        lines.append(f"| {gate} | {page} | {step} | {status} | {secs} | {detail} |")
    failed = sum(1 for r in rows if r[3] == "FAIL")
    stale = sum(1 for r in rows if r[3] == "STALE")
    verdict = "FAIL" if failed or not rows else "PASS"
    lines += ["", f"**Verdict: {verdict}** ({failed} failed, {stale} stale checks)", ""]
    text = "\n".join(lines)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(text)
    return 0 if verdict == "PASS" else 1


# --- command line -----------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("versions")

    p = sub.add_parser("external-skips")
    p.add_argument("--junit", type=Path, required=True)
    p.add_argument("--ids", type=Path, required=True)
    p.add_argument("--python", required=True)
    p.add_argument("--pytest-rc", type=int, required=True)
    p.add_argument("--seconds", type=float, default=0)
    p.add_argument("--results", type=Path, required=True)

    for name in ("docs", "bundles"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--work", type=Path, required=True)
        p.add_argument("--logs", type=Path, required=True)
        p.add_argument("--results", type=Path, required=True)
        p.add_argument("--manifest", type=Path, default=MANIFEST)
        p.add_argument("--data", type=Path)
        p.add_argument("--mode", choices=("quick", "full"), default="quick")
        p.add_argument("--python", default="3.12")
        p.add_argument("--only", nargs="*", default=[])

    p = sub.add_parser("report")
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--title", default="")

    args = parser.parse_args()
    commands = {
        "versions": cmd_versions,
        "external-skips": cmd_external_skips,
        "docs": cmd_docs,
        "bundles": cmd_bundles,
        "report": cmd_report,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
