"""Write the derived scenario configs of the profiling study (one key changed each).

Reads the base configs from fds-evac at the frozen commit with `git show`,
changes exactly one documented key, and writes JSON (indent=2) next to this
script, plus a copy of each geometry.wkt the run needs. Prints sha256 of every
file written. Re-running reproduces the same bytes.
"""

import copy
import hashlib
import json
import pathlib
import subprocess

REPO = "/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/pyFDS-EVAC"
COMMIT = "8f7d29a2e056db46183e8cccabce338c398606a1"
FIX_COMMIT = "29f9d3a583ac82d796fa113143dbf9ab4dae793a"  # fix/243-fed-rate-memo head
HERE = pathlib.Path(__file__).resolve().parent


def show(path, commit=COMMIT):
    return subprocess.check_output(["git", "-C", REPO, "show", f"{commit}:{path}"])


def write(rel, data: bytes):
    out = HERE / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(hashlib.sha256(data).hexdigest(), rel)


def derive(base, rel_dir, name, setter, wkt, commit=COMMIT):
    cfg = json.loads(show(base, commit))
    new = copy.deepcopy(cfg)
    setter(new)
    write(f"{rel_dir}/{name}", (json.dumps(new, indent=2) + "\n").encode())
    write(f"{rel_dir}/geometry.wkt", show(wkt, commit))


def set_max_time(value):
    def _s(cfg):
        cfg["config"]["simulation_settings"]["simulationParams"]["max_simulation_time"] = value
    return _s


def set_fed_rate_memo(value):
    def _s(cfg):
        cfg["routing"]["fed_rate_memo"] = value
    return _s


def set_number(value):
    def _s(cfg):
        cfg["distributions"]["jps-distributions_0"]["parameters"]["number"] = value
    return _s


SCH = "assets/schroeder2015_route/evac"
for n in (100, 400):
    derive(f"{SCH}/config_gate.json", f"w1_scaling_n{n}", "config_gate.json",
           set_number(n), f"{SCH}/geometry.wkt")
# G5 (#243): the fix head's W1 with the FED-rate memo switched off, nothing else changed.
derive(f"{SCH}/config_gate.json", "w1_nomemo", "config_gate.json",
       set_fed_rate_memo(False), f"{SCH}/geometry.wkt", commit=FIX_COMMIT)
derive("assets/t_junction/config_discovery.json", "w3_t_junction_cap270",
       "config_discovery_cap270.json", set_max_time(270), "assets/t_junction/geometry.wkt")
derive("assets/cognitive_map_memory/config.json", "w4_cmm_cap120",
       "config_cap120.json", set_max_time(120), "assets/cognitive_map_memory/geometry.wkt")


def make_flow_saturated(cfg):
    """#739 fixture: a 28 m2 area held full by waiting agents while a flow asks for more.

    Clear air (familiarity full, run without --fds-dir). Both distributions
    share the t_junction spawn polygon and wait a constant 100 s before
    moving: 150 standing agents at t = 0 and a flow of 300 over 0-60 s, so the
    area fills and the flow defers its spawns. One extra journey for the
    second distribution; max_simulation_time 200 s. Flow-spawned agents get no
    pre-movement entry at this commit, so the flow keeps use_premovement
    false; the saturation comes from the 150 standing agents.
    """
    set_max_time(200)(cfg)
    dists = cfg["distributions"]
    flow = dists["jps-distributions_0"]["parameters"]
    flow.update({"number": 300, "flow_start_time": 0, "flow_end_time": 60,
                 "familiarity": "full"})
    standing = copy.deepcopy(dists["jps-distributions_0"])
    standing["parameters"].update({"number": 150, "use_flow_spawning": False,
                                   "use_premovement": True,
                                   "premovement_distribution": "constant",
                                   "premovement_param_a": 100})
    dists["jps-distributions_1"] = standing
    journey = copy.deepcopy(cfg["journeys"][0])
    journey["id"] = "journey_1"
    journey["stages"][0] = "jps-distributions_1"
    for t in journey["transitions"]:
        t["journey_id"] = "journey_1"
    journey["transitions"][0]["from"] = "jps-distributions_1"
    cfg["journeys"].append(journey)
    cfg["transitions"].extend(copy.deepcopy(journey["transitions"]))
    routing = cfg["waypoint_routing"]["jps-checkpoints_0"]
    routing["journey_1"] = copy.deepcopy(routing["journey_0"])


derive("assets/t_junction/config_discovery.json", "w4_flow_saturated",
       "config_flow_saturated.json", make_flow_saturated, "assets/t_junction/geometry.wkt")


STAGE = pathlib.Path("/Users/chraibi/profiling-stage")


def make_w1r_cap250():
    """World100 stream-east deck with max_simulation_time 330 -> 250 and nothing else.

    The FDS output ends at 250 s (guard 252 s); the deck is read from the
    staged copy of sciebo world100/evac_4exits, the geometry copied byte for byte.
    """
    deck = STAGE / "decks/world100_evac_4exits"
    cfg = json.loads((deck / "deck_config_stream_east.json").read_text())
    set_max_time(250)(cfg)
    write("w1r_cap250/config_stream_east_cap250.json", (json.dumps(cfg, indent=2) + "\n").encode())
    write("w1r_cap250/geometry.wkt", (deck / "deck_geometry.wkt").read_bytes())


make_w1r_cap250()
