# Default-mode heat FED baseline

`fed_history.csv` and `manifest.json` are the outputs of a run without
`--heat-endpoint`, made on main at commit 76c9a76, before the option existed.
At that commit the default law was SFPE Eq. 63.44, which is ISO 13571:2012
Eq. (10); since #290 the default is ISO Eq. (9) and Eq. (10) is selected
with `clothing="unclothed"` (`--heat-clothing unclothed`).
`test_heat_endpoint_coupled.py::test_unclothed_outputs_match_the_baseline`
checks that such a run still writes the same CSV header, the same rows
(floats to a relative tolerance of 1e-9, as JuPedSim builds differ in the
last bits between platforms) and the same manifest keys and values, apart
from the `heat_clothing` key added with #290, which it checks separately.

The run is the 30 s corridor of that test under the Table 63.21 temperature
history (SFPE Handbook Ch. 63, p. 2385) with Eq. 63.44. Manifest values that
depend on the machine, the time or the checkout read `"<normalised>"`.

`make_baseline.py` is kept as it ran at 76c9a76: it builds the model without
a clothing argument, so on a checkout after #290 it would write the clothed
law. Regenerate only from a checkout whose default heat output is meant to be
the reference:

    PYTHONPATH=. python tests/verification/golden/heat_default/make_baseline.py
