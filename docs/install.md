---
title: "Install"
weight: 0
---

Install pyFDS-Evac, run one scenario to check the install, and know what else
you need for your own FDS cases.

## Requirements

| Needed | For |
|---|---|
| Python 3.11 or 3.12 | pyFDS-Evac itself (`requires-python = ">=3.11,<3.13"`) |
| [uv](https://github.com/astral-sh/uv) | the environment, the examples and every command on this site |
| git and network access | fdsvismap is installed from its git repository, pinned to one commit |
| [FDS](https://github.com/firemodels/fds) (optional) | only to run your own fire; pyFDS-Evac reads the output of a finished FDS run and never starts FDS |
| ffmpeg (optional) | only for the MP4 of `scripts/animate_cognitive_map.py` |

pyFDS-Evac is not on PyPI yet. The release waits on an upstream fdsvismap
merge.

## Install from the repository

The examples and the tracked scenarios live in the repository (`examples/`,
`assets/`), so clone it:

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
```

For the optional [web GUI](web-gui.md), add its extra:

```bash
uv sync --extra gui
```

### Check the install

```bash
uv run python run.py --scenario assets/ISO-table21 --cleanup
```

{{< checkpoint title="Install works" >}}
The last line reads:

```text
Simulation finished in 79.24 s (1/1 evacuated).
```

One agent walks the ISO 20414 Test 18 corridor in clear air. If you see this
line, the install works.
{{< /checkpoint >}}

## Library only

To use pyFDS-Evac as a library in another project, install the package from
git:

```bash
pip install "pyfds-evac @ git+https://github.com/PedestrianDynamics/pyFDS-Evac.git"
```

The package contains `pyfds_evac` only. `run.py`, `examples/`, `scripts/` and
`assets/` are not in it.

## Next steps

- [Quickstart](quickstart.md): one run with smoke, and what the numbers mean.
- [Troubleshooting](troubleshooting.md): if a command on this site fails.
