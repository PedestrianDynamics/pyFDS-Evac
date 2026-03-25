"""Inspect which FDS quantities are available for smoke and FED models."""

from dataclasses import dataclass
import pathlib

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    Simulation = None


@dataclass
class FdsQuantityInventory:
    """Describe the FDS quantity families available in one case directory."""

    slices: list[str]
    smoke_3d: list[str]
    data_3d: list[str]
    devices: list[str]

    def canonical_slice_names(self) -> dict[str, str]:
        """Map known slice quantities to the names used by this project."""
        canonical = {}
        for quantity in self.slices:
            upper = quantity.upper()
            if upper == "SOOT EXTINCTION COEFFICIENT":
                canonical["extinction"] = quantity
            elif upper == "TEMPERATURE":
                canonical["temperature"] = quantity
            elif upper == "CARBON MONOXIDE VOLUME FRACTION":
                canonical["co"] = quantity
            elif upper == "CARBON DIOXIDE VOLUME FRACTION":
                canonical["co2"] = quantity
            elif upper == "OXYGEN VOLUME FRACTION":
                canonical["o2"] = quantity
        return canonical

    def supports_default_fed(self) -> bool:
        """Return whether the default CO/CO2/O2 FED path can run."""
        return {"co", "co2", "o2"}.issubset(self.canonical_slice_names())


def _quantity_names(collection) -> list[str]:
    """Extract unique quantity names from one `fdsreader` collection."""
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

    if Simulation is None:
        raise ModuleNotFoundError(
            "fdsreader is required to inspect FDS quantities."
        )
    sim = Simulation(str(sim_dir))
    return FdsQuantityInventory(
        slices=_quantity_names(sim.slices),
        smoke_3d=_quantity_names(sim.smoke_3d),
        data_3d=_quantity_names(sim.data_3d),
        devices=_quantity_names(sim.devices),
    )


def list_simulations(base_dir: str) -> list[str]:
    """Return child directories containing exactly one `.smv` file."""

    root = pathlib.Path(base_dir)
    candidates: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and len(list(child.glob("*.smv"))) == 1:
            candidates.append(str(child))
    return candidates
