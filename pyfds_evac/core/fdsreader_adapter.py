"""Open FDS output with fdsreader without touching the case directory.

fdsreader 1.11.7 to 1.14.0 keep a ``<CHID>.pickle`` cache next to the ``.smv``
(``Simulation._get_pickle_filename``). With caching on, it writes that
file when none exists, and on every open after the first in a process,
and deletes a pickle it cannot read or that is stale; with ``settings.ENABLE_CACHING = False``
it deletes an existing pickle instead. Either way, opening a case writes
to or deletes from the user's FDS directory (#716).

``fdsreader_without_cache`` turns the cache off and points the pickle
path at an empty temporary folder for the duration of a block, so
fdsreader neither writes nor deletes anything in the case directory.
This also reaches fdsreader calls made by fdsvismap. Both values are
restored on exit. The block also drops fdsreader's ``Module smoke3d``
warnings: fdsreader logs one with a traceback for every mesh whose
``.s3d`` files are missing, and pyfds-evac never reads 3D smoke (#978). The cache only saves parsing the ``.smv`` and slice
headers: 0.1-0.4 s for a 64-mesh case with 768 slice files.

Both values are process-global. Inside the block, any fdsreader call in
the process, in any thread, runs without the cache; a lock makes blocks
in different threads wait for each other, so a block always restores the
values it found. fdsreader calls in another thread that do not use this
module are not held by the lock. Child processes start with fdsreader's
defaults and must open cases through this module too.

``open_fds_simulation`` returns a ``CaseSafeSimulation``, an
``fdsreader.Simulation`` that keeps this promise after the block: a copy
(``copy.deepcopy``) or an unpickled instance is created inside the block
again, as fdsreader creates it through ``Simulation.__new__``, and
``clear_cache(clear_persistent_cache=True)`` clears the memory cache
only. fdsreader's own function, called as
``Simulation.clear_cache(sim, True)``, still deletes ``<CHID>.pickle``.

Workaround record. Reason: fdsreader has no setting for the cache
folder and deletes the pickle when caching is off. Affected versions:
fdsreader 1.11.7 to 1.14.0, checked by the regression test (the pickle
handling in Simulation.__new__ and _get_pickle_filename is the same in
both, so the workaround is still needed); pyproject.toml pins fdsreader
to >=1.11.7,<1.15 without 1.11.9 and 1.12.0, which fail on cell-centred
slices. Re-verify a new fdsreader minor with
tests/test_fdsreader_adapter.py before widening the pin. An fdsreader
without the two names refuses to open. Upstream issue: none yet. Regression test:
tests/test_fdsreader_adapter.py. Remove when fdsreader lets the cache
folder be set, or turns caching off without deleting the pickle.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()


def _not_smoke3d(record: logging.LogRecord) -> bool:
    """Drop fdsreader's ``Module smoke3d`` warning (``utils/misc.py``)."""
    return not str(record.msg).startswith("Module smoke3d:")


def _check_fdsreader(fdsreader: Any, settings: Any, simulation_cls: Any) -> None:
    """Refuse an fdsreader without the two names this module replaces."""
    missing = [
        name
        for name, present in (
            ("settings.ENABLE_CACHING", hasattr(settings, "ENABLE_CACHING")),
            (
                "Simulation._get_pickle_filename",
                "_get_pickle_filename" in vars(simulation_cls),
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


@contextmanager
def fdsreader_without_cache() -> Iterator[None]:
    """Run a block with fdsreader's on-disk cache off and redirected.

    Every ``fdsreader.Simulation`` opened inside the block, also by
    fdsvismap, reads the FDS output and leaves its directory unchanged.
    """
    try:
        import fdsreader
        from fdsreader import settings
        from fdsreader.simulation import Simulation
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("fdsreader is required to read FDS output.") from exc
    _check_fdsreader(fdsreader, settings, Simulation)
    with _LOCK, tempfile.TemporaryDirectory(prefix="pyfds-evac-fdsreader-") as tmp:
        caching = settings.ENABLE_CACHING
        pickle_filename = Simulation.__dict__["_get_pickle_filename"]

        def no_pickle(cls: Any, root_path: str, chid: str) -> str:
            # Never created: caching is off, so fdsreader only checks for it.
            # One name for every CHID, which a path in the .smv cannot
            # move out of the empty folder.
            return str(Path(tmp) / "simulation.pickle")

        # A fresh filter per block, so a nested block removes only its own.
        smoke3d_filter = logging.Filter()
        smoke3d_filter.filter = _not_smoke3d  # type: ignore[method-assign]
        settings.ENABLE_CACHING = False
        Simulation._get_pickle_filename = classmethod(no_pickle)
        logging.getLogger().addFilter(smoke3d_filter)
        try:
            yield
        finally:
            logging.getLogger().removeFilter(smoke3d_filter)
            Simulation._get_pickle_filename = pickle_filename
            settings.ENABLE_CACHING = caching


def _case_safe_class() -> type:
    """``CaseSafeSimulation``, built on first use to keep imports cheap."""
    cls = globals().get("_CASE_SAFE")
    if cls is not None:
        return cls
    from fdsreader.simulation import Simulation

    class CaseSafeSimulation(Simulation):
        """``fdsreader.Simulation`` that never touches the case's pickle."""

        def __new__(cls, *args: Any, **kwargs: Any) -> Any:
            # Also the path of copy.deepcopy and pickle.load, which pass
            # the .smv path from Simulation.__getnewargs__.
            with fdsreader_without_cache():
                return super().__new__(cls, *args, **kwargs)

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # Parses the .smv, where fdsreader logs the smoke3d warnings.
            with fdsreader_without_cache():
                super().__init__(*args, **kwargs)

        def clear_cache(self, clear_persistent_cache: bool = False) -> None:
            """Free the loaded data; there is no pickle of this one to delete."""
            super().clear_cache(clear_persistent_cache=False)

    CaseSafeSimulation.__module__ = __name__
    CaseSafeSimulation.__qualname__ = "CaseSafeSimulation"
    globals()["_CASE_SAFE"] = CaseSafeSimulation
    return CaseSafeSimulation


def __getattr__(name: str) -> Any:
    # pickle finds CaseSafeSimulation here by name.
    if name == "CaseSafeSimulation":
        return _case_safe_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def open_fds_simulation(path: str | Path) -> Any:
    """``fdsreader.Simulation(path)`` that leaves the case directory unchanged."""
    with fdsreader_without_cache():
        return _case_safe_class()(str(path))
