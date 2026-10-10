"""Open FDS output with fdsreader, leaving the case directory unchanged.

A local copy of ``pyfds_evac.core.fdsreader_adapter.open_fds_simulation``
for the verification figure scripts, which read the FDS slices without
pyFDS-Evac code and also run as standalone scripts (PEP 723) that do not
install pyFDS-Evac. fdsreader 1.11.7 writes ``<CHID>.pickle`` next to the
``.smv`` and deletes it when caching is off (#716); this turns the cache
off and points the pickle path at an empty temporary folder while the
case is parsed. Keep in step with the adapter; remove with it.
"""

import tempfile
from pathlib import Path

import fdsreader
from fdsreader.simulation import Simulation


def open_fds_case(path):
    """``fdsreader.Simulation(path)`` that writes and deletes nothing."""
    if "_get_pickle_filename" not in vars(Simulation):
        raise RuntimeError(
            "cannot open FDS output without writing fdsreader's cache into "
            f"the case directory: fdsreader {fdsreader.__version__} has no "
            "Simulation._get_pickle_filename"
        )
    caching = fdsreader.settings.ENABLE_CACHING
    pickle_filename = vars(Simulation)["_get_pickle_filename"]
    with tempfile.TemporaryDirectory(prefix="fdsreader-") as tmp:
        empty = str(Path(tmp) / "simulation.pickle")
        fdsreader.settings.ENABLE_CACHING = False
        Simulation._get_pickle_filename = classmethod(lambda cls, root, chid: empty)
        try:
            return Simulation(str(path))
        finally:
            Simulation._get_pickle_filename = pickle_filename
            fdsreader.settings.ENABLE_CACHING = caching
