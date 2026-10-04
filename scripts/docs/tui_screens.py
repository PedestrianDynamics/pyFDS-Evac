"""Terminal screenshots for the Terminal UI page, from a real fire run.

Drives ``pyfds-evac-tui`` through Textual's test pilot on ``assets/t_junction``
(``config.json``, seed 42) against the FDS output of
``assets/t_junction/t_junction.fds`` (``fire_2MW_PVC``), and saves the FDS,
Review, Run, Results and full-plan screens as SVG. The run is a real child
process, as in the TUI.

The screens show absolute paths, so the script builds its working folder at
``--demo`` (default ``/Users/Shared/pyfds-evac-demo``): a copy of
``assets/t_junction`` with the FDS output copied in as ``fire_2MW_PVC``. It
uses a private ``recent.json``, so the caller's Recent list is untouched.
From the repository root::

    uv run --extra tui python scripts/docs/tui_screens.py --data FDS

Writes ``site/assets/images/tui/tui-{fds,review,run,results}.svg`` at
120x35 in the evac-dark theme and ``tui-plan-solarized.svg`` at 80x24 in
Solarized Light. The Scenario and Configure figures are the snapshot tests'
SVGs (``tests/__snapshots__/test_tui``), not made here.
"""

import argparse
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "assets" / "images" / "tui"
GROUPS = ("config", "inspect", "suggest")
RUN_SHOT_SIM_S = 30.0
REPLAY_SIM_S = 60.0


async def settle(pilot, app) -> None:
    """Wait for the configuration, inspection and suggestion workers."""
    for _ in range(2000):
        await pilot.pause()
        busy = [w for w in app.workers if w.group in GROUPS and not w.is_finished]
        if not busy:
            await pilot.pause()
            return
        await asyncio.sleep(0.02)
    raise RuntimeError("workers did not finish")


async def shot(pilot, app, path: Path) -> None:
    for widget in app.screen.query("*"):
        if hasattr(widget, "cursor_blink"):
            widget.cursor_blink = False
    await pilot.pause(0.3)
    app.save_screenshot(path.name, str(path.parent))
    print("wrote", path.relative_to(ROOT))


async def wait_for_run(pilot, app, run_shot: Path | None) -> None:
    taken = run_shot is None
    for _ in range(30000):
        await asyncio.sleep(0.02)
        run = app.current_run
        progress = run.progress if run else None
        if not taken and progress is not None and progress.sim_time >= RUN_SHOT_SIM_S:
            await shot(pilot, app, run_shot)
            taken = True
        if run is not None and run.done:
            await pilot.pause(0.5)
            return
    raise RuntimeError("the run did not finish")


def replay_at(app, sim_time: float) -> None:
    times = [frame.sim_time for frame, _grid in app.current_run.frames]
    if not times:
        raise RuntimeError("the run sent no plan frames")
    app.scrub_index = min(range(len(times)), key=lambda i: abs(times[i] - sim_time))
    app.refresh_plans()


async def capture(demo: Path, size: tuple[int, int], theme: str, names: dict) -> None:
    from pyfds_evac.tui.app import EvacTui

    scenario = demo / "assets" / "t_junction"
    app = EvacTui(cwd=demo, theme=theme)
    async with app.run_test(size=size) as pilot:
        await settle(pilot, app)
        app.select_scenario(scenario)
        await settle(pilot, app)
        app.set_fds_dir(str(scenario / "fire_2MW_PVC"))
        await settle(pilot, app)
        app.goto(1)
        await settle(pilot, app)
        if "fds" in names:
            await shot(pilot, app, names["fds"])
        app.goto(3)
        await settle(pilot, app)
        if "review" in names:
            await shot(pilot, app, names["review"])
        await pilot.press("ctrl+r")
        await pilot.pause()
        await wait_for_run(pilot, app, names.get("run"))
        replay_at(app, REPLAY_SIM_S)
        await pilot.pause()
        if "results" in names:
            await shot(pilot, app, names["results"])
        await pilot.press("v")
        await pilot.pause()
        if "plan" in names:
            await shot(pilot, app, names["plan"])


def build_demo(demo: Path, data: Path) -> None:
    if demo.exists():
        shutil.rmtree(demo)
    target = demo / "assets" / "t_junction"
    shutil.copytree(ROOT / "assets" / "t_junction", target)
    shutil.copytree(data, target / "fire_2MW_PVC")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="FDS output directory of assets/t_junction/t_junction.fds",
    )
    parser.add_argument(
        "--demo",
        type=Path,
        default=Path("/Users/Shared/pyfds-evac-demo"),
        help="working folder to create; its path shows on the screens",
    )
    args = parser.parse_args()
    if not any(args.data.glob("*.smv")):
        parser.error(f"{args.data} has no .smv file")
    build_demo(args.demo, args.data)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as config:
        os.environ["XDG_CONFIG_HOME"] = config
        os.environ.pop("PYFDS_EVAC_RESULTS_DIR", None)
        wide = {k: OUT / f"tui-{k}.svg" for k in ("fds", "review", "run", "results")}
        asyncio.run(capture(args.demo, (120, 35), "evac-dark", wide))
        small = {"plan": OUT / "tui-plan-solarized.svg"}
        asyncio.run(capture(args.demo, (80, 24), "solarized-light", small))


if __name__ == "__main__":
    main()
