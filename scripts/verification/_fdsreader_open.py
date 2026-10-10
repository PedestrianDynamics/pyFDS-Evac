"""Open FDS output with fdsreader, leaving the case directory unchanged.

A local copy of ``pyfds_evac.core.fdsreader_adapter.open_fds_simulation``
for the verification figure scripts, which read the FDS slices without
pyFDS-Evac code and also run as standalone scripts (PEP 723) that do not
install pyFDS-Evac. fdsreader 1.11.7 writes ``<CHID>.pickle`` next to the
``.smv`` and deletes it when caching is off (#716); this turns the cache
off and points the pickle path at an empty temporary folder while the
case is parsed. Keep in step with the adapter; remove with it.

Narrower than the adapter, for scripts that only read slices: no lock,
and the plain ``Simulation`` it returns does not guard
``clear_cache(clear_persistent_cache=True)``, ``copy.deepcopy`` or
pickling, which fdsreader lets delete ``<CHID>.pickle`` in the case
directory. The scripts do none of these.
"""

import tempfile
from pathlib import Path

import fdsreader
from fdsreader.simulation import Simulation


def open_fds_case(path):
    """``fdsreader.Simulation(path)`` that writes and deletes nothing."""
    missing = [
        name
        for name, present in (
            ("settings.ENABLE_CACHING", hasattr(fdsreader.settings, "ENABLE_CACHING")),
            (
                "Simulation._get_pickle_filename",
                "_get_pickle_filename" in vars(Simulation),
            ),
        )
        if not present
    ]
    if missing:
        raise RuntimeError(
            "cannot open FDS output without writing fdsreader's cache into "
            f"the case directory: fdsreader {fdsreader.__version__} has no "
            + " or ".join(missing)
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
