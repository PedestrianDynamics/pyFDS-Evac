"""Run JSON-first JuPedSim scenarios from the fds-evac repository.

Source-checkout entry point. The command line interface lives in
``pyfds_evac.cli`` and installs as the ``pyfds-evac`` command; this file
runs it, and ``import run`` returns that module, so existing callers of
``run._build_parser``, ``run.apply_outputs`` and the CSV writers keep
working.
"""

import sys

from pyfds_evac import cli

if __name__ == "__main__":
    raise SystemExit(cli.main())

sys.modules[__name__] = cli
