from __future__ import annotations

from dataclasses import dataclass

from fdsreader import Simulation


@dataclass
class FdsQuantityInventory:
    """Inventory of FDS quantities available for future fire-behavior models."""

    slices: list[str]
    smoke_3d: list[str]
    data_3d: list[str]
    devices: list[str]


def _quantity_names(collection) -> list[str]:
    quantities = getattr(collection, "quantities", [])
    names: list[str] = []
    for quantity in quantities:
        name = getattr(quantity, "name", quantity)
        names.append(str(name))
    return sorted(set(names))


def inspect_fds_quantities(sim_dir: str) -> FdsQuantityInventory:
    """Read an FDS case and list the exposed quantity families.

    This is the bridge toward FED/incapacitation work:
    - `fdsvismap` covers extinction/visibility-centric data well
    - `fdsreader` gives us the broader raw-FDS quantity inventory needed for
      gases, temperature, radiation, and other hazard terms.
    """

    sim = Simulation(str(sim_dir))
    return FdsQuantityInventory(
        slices=_quantity_names(sim.slices),
        smoke_3d=_quantity_names(sim.smoke_3d),
        data_3d=_quantity_names(sim.data_3d),
        devices=_quantity_names(sim.devices),
    )
