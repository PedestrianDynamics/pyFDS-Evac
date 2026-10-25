"""Every heat option warns once when no heat model is built (#325).

The options come from ``PARAMETERS``, so a heat option added later must get a
probe value here, and then must warn like the others.
"""

from __future__ import annotations

import logging

import pytest

from pyfds_evac import cli
from pyfds_evac.config.parameters import PARAMETERS
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario

SCENARIO = "assets/t_junction"
FDS_DIR = "assets/iso_table22_coupled/fds/a"

# A value away from the parser default for each heat option, valid on its own.
NON_DEFAULT = {
    "heat_clothing": "unclothed",
    "heat_endpoint": "injury",
    "heat_fed_method": "total-flux",
    "heat_emissivity": "0.6",
    "heat_convective_coefficient": "6",
    "heat_skin_temperature": "36",
    "heat_radiant_source": "integrated-intensity",
    "heat_u_factor": "0.5",
    "heat_regime": "layer",
    "heat_layer_height": "2.5",
    "heat_view_factor": "0.5",
    "heat_layer_emissivity": "0.9",
    "heat_fed_threshold": "0.5",
    "heat_incapacitation_mode": "probabilistic",
    "heat_susceptibility_sigma": "0.5",
}

HEAT_DESTS = sorted(p.dest for p in PARAMETERS if p.dest.startswith("heat_"))


def test_every_heat_option_has_a_probe_value():
    assert sorted(NON_DEFAULT) == HEAT_DESTS


@pytest.mark.parametrize("with_fds", [False, True], ids=["no-fds-dir", "fds-dir"])
@pytest.mark.parametrize("dest", HEAT_DESTS)
def test_a_heat_option_without_enable_warns_once(dest, with_fds, caplog):
    flag = "--" + dest.replace("_", "-")
    argv = ["--scenario", SCENARIO, flag, NON_DEFAULT[dest]]
    if with_fds:
        argv += ["--fds-dir", FDS_DIR]
    opts = cli._build_parser().parse_args(argv)
    with caplog.at_level(logging.WARNING):
        build_run_kwargs(load_scenario(opts.scenario), opts)
    reason = "--enable-heat-fed" if with_fds else "--fds-dir"
    hits = [m for m in caplog.messages if m.startswith(f"{flag} ")]
    assert hits == [f"{flag} has no effect without {reason}."]
