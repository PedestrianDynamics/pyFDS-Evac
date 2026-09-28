# Default-mode heat FED baseline

`fed_history.csv` and `manifest.json` are the outputs of a run without
`--heat-endpoint`, made on main at commit 76c9a76, before the option existed.
`test_heat_endpoint_coupled.py::test_default_outputs_match_the_baseline`
checks that a run without an endpoint still writes the same CSV header, the
same rows (floats to a relative tolerance of 1e-9, as JuPedSim builds differ
in the last bits between platforms) and the same manifest keys and values.

The run is the 30 s corridor of that test under the Table 63.21 temperature
history (SFPE Handbook Ch. 63, p. 2385) with Eq. 63.44. Manifest values that
depend on the machine, the time or the checkout read `"<normalised>"`.

Regenerate only from a checkout whose default heat output is meant to be the
reference:

    PYTHONPATH=. python tests/verification/golden/heat_default/make_baseline.py
