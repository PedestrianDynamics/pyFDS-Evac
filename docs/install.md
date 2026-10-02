---
title: "Install"
weight: 0
---

Install pyFDS-Evac with pip, run one scenario to check the install, and know
what else you need for your own FDS cases. To work on the code or run the
examples and scripts of the repository, use the
[source checkout](#install-from-the-repository).

## Requirements

| Needed | For |
|---|---|
| Python 3.12, 3.13 or 3.14 | pyFDS-Evac itself (`requires-python = ">=3.12,<3.15"`) |
| [uv](https://github.com/astral-sh/uv), git | the source checkout; git also for `pip install -r requirements.txt` of an example zip |
| [FDS](https://github.com/firemodels/fds) (optional) | only to run your own fire; pyFDS-Evac reads the output of a finished FDS run and never starts FDS |
| ffmpeg (optional) | only for the MP4 of `scripts/animate_cognitive_map.py` |

## Install with pip

pyFDS-Evac is on [PyPI](https://pypi.org/project/pyfds-evac/). Install it in
a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install pyfds-evac
```

For the optional [web GUI](web-gui.md), install the `gui` extra:

```bash
pip install "pyfds-evac[gui]"
```

You can then run:

| Command | What it does |
|---|---|
| `pyfds-evac` | Runs a scenario. Same flags, defaults, outputs and exit codes as `run.py` in the repository ([Usage](usage.md)). |
| `python -m pyfds_evac` | The same command, run through the Python interpreter. |
| `pyfds-evac-gui` | Starts the [web GUI](web-gui.md) on <http://127.0.0.1:5001>. Needs the `gui` extra. |

The package contains the `pyfds_evac` library with its command line and GUI.
It contains no scenarios, examples or scripts: `assets/`, `examples/` and
`scripts/` stay in the repository. Get them from the example zip of a page,
such as the [Quickstart](quickstart.md), or from a
[source checkout](#install-from-the-repository).

### Check the pip install

```bash
pyfds-evac --help
```

The first line reads `usage: pyfds-evac [-h] --scenario SCENARIO ...`.

For a full check, run a scenario. Download the
[Quickstart example files](downloads/pyfds-evac-quickstart.zip) and unpack
them. The zip unpacks into a folder named `pyfds-evac-quickstart`. Run the
command from inside it:

```bash
cd pyfds-evac-quickstart
pyfds-evac --scenario assets/ISO-table21 --cleanup
```

{{< checkpoint title="Install works" >}}
The last line reads:

```text
Simulation finished in 79.24 s (1/1 evacuated).
```

One agent walks the ISO 20414 Test 18 corridor in clear air. If you see this
line, the install works.
{{< /checkpoint >}}

## Install from the repository

The source checkout is the route for developing pyFDS-Evac and for running
the examples, the scripts and the tracked scenarios with their FDS output.
Every command on this site that starts with `uv run` assumes it. Clone the
repository and install the environment with uv:

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
```

For the optional [web GUI](web-gui.md), add its extra:

```bash
uv sync --extra gui
```

`uv sync` installs pyFDS-Evac in editable mode, so the `pyfds-evac` and
`pyfds-evac-gui` commands are also available with `uv run`. `run.py` and
`app.py` at the repository root run the same command line and GUI.

### Check the checkout

```bash
uv run python run.py --scenario assets/ISO-table21 --cleanup
```

{{< checkpoint title="Install works" >}}
The last line reads:

```text
Simulation finished in 79.24 s (1/1 evacuated).
```

The same corridor and the same result as the pip check.
{{< /checkpoint >}}

## Next steps

- [Quickstart](quickstart.md): one run with smoke, and what the numbers mean.
- [Troubleshooting](troubleshooting.md): if a command on this site fails.
