"""Geometry of the route-choice case after Schroeder et al. (2015), Fig. 6.

Single source for the walkable area (WKT), the stage polygons and the FDS
deck. Coordinates in metres. Extents are the plan's digitised values from
Schroeder et al. 2015 Figs. 2-3 (+-0.5-1 m), snapped to the 0.2 m FDS grid.
Tags: [D] digitised (plan section 1), [P] paper, [A] assumed here.

- Room 2, corridor: x -5..0, y -10..35 [D].
- Room 1, hall: x 0.2..10.6, y 0..24. [D] gives x 0..10.5; the 0.2 m
  hall/corridor wall is placed on the hall side (x 0..0.2) and the far wall
  moved to 10.6 so the interior is 10.4 m wide and on the grid [A].
- Room 3, vestibule: y 24.2..31 [D], x 0.2..10.6, same width as the hall
  [A: the plan gives no x range]. Wall to the hall y 24..24.2 [A].
- Doors, all 2 m [P, 2015 p. 9], centred on the digitised positions and
  snapped to the grid [A]: A y 0.6..2.6 (digitised y ~1-2), B y 20.6..22.6
  (digitised y ~21-22), D y 26.6..28.6 (corridor wall of Room 3), C x
  4.4..6.4 (hall/Room 3 wall).
- Exits E (bottom, y = -10) and F (top, y = 35), 2 m, centred on the
  corridor axis and snapped: x -3.6..-1.6 [A]. In the walkable area each
  exit is a 2 m passage 0.8 m deep (jambs), so agents enter the passage
  before the exit removes them (issue #349); in FDS the corridor runs the
  full -10..35 and the exits are open vents on the end walls.

Room 3 and doors C, D are not walkable (plan section 4); they are open in
FDS so smoke can leave Room 3 through them.
"""

from shapely import Polygon, box, unary_union
from shapely.geometry.polygon import orient

WALL = 0.2  # one 0.2 m cell

CORRIDOR = (-5.0, -10.0, 0.0, 35.0)  # xmin, ymin, xmax, ymax
HALL = (WALL, 0.0, 10.6, 24.0)
ROOM3 = (WALL, 24.0 + WALL, 10.6, 31.0)

DOOR_A = (0.6, 2.6)  # y range in the wall x 0..0.2
DOOR_B = (20.6, 22.6)
DOOR_D = (26.6, 28.6)  # Room 3 -> corridor, y range in the wall x 0..0.2
DOOR_C = (4.4, 6.4)  # hall -> Room 3, x range in the wall y 24..24.2
EXIT_X = (-3.6, -1.6)
JAMB = 0.8
# Burner 3 x 2 m centred in Room 3 (design fire), on the grid: x0, x1, y0, y1.
BURNER_XY = (4.0, 7.0, 26.6, 28.6)

# Digitised source outline (plan section 1), before snapping, for the figure.
SOURCE = {
    "Room 1": (0.0, 0.0, 10.5, 24.0),
    "Room 2": (-5.0, -10.0, 0.0, 35.0),
    "Room 3": (0.0, 24.0, 10.5, 31.0),
}
SOURCE_DOORS = {"A": (1.0, 2.0), "B": (21.0, 22.0)}  # y ranges on x = 0


def walkable() -> Polygon:
    """Corridor, hall and the A, B door gaps; Room 3 excluded.

    The wall between doors A and B (x 0..0.2, y 2.6..20.6) is the one hole.
    """
    x0, y0, x1, y1 = CORRIDOR
    parts = [
        box(x0, y0 + JAMB, x1, y1 - JAMB),
        box(EXIT_X[0], y0, EXIT_X[1], y0 + JAMB),
        box(EXIT_X[0], y1 - JAMB, EXIT_X[1], y1),
        box(*HALL),
        box(0.0, DOOR_A[0], WALL, DOOR_A[1]),
        box(0.0, DOOR_B[0], WALL, DOOR_B[1]),
    ]
    poly = orient(unary_union(parts).simplify(0))
    assert poly.geom_type == "Polygon" and len(poly.interiors) == 1
    return poly


def exit_polygon(name: str) -> list[list[float]]:
    """A 0.2 m strip at the far end of the exit passage."""
    x0, x1 = EXIT_X
    y = CORRIDOR[1] if name == "E" else CORRIDOR[3] - WALL
    return [[x0, y], [x1, y], [x1, y + WALL], [x0, y + WALL], [x0, y]]


def door_checkpoint(name: str) -> list[list[float]]:
    """Waypoint polygon spanning the door gap, 0.2 m into each room."""
    ya, yb = DOOR_A if name == "A" else DOOR_B
    return [[-0.2, ya], [0.4, ya], [0.4, yb], [-0.2, yb], [-0.2, ya]]


def spawn_area(margin: float = 0.3) -> list[list[float]]:
    """Room 1 inset by ``margin`` from its walls."""
    x0, y0, x1, y1 = HALL
    return [
        [x0 + margin, y0 + margin],
        [x1 - margin, y0 + margin],
        [x1 - margin, y1 - margin],
        [x0 + margin, y1 - margin],
        [x0 + margin, y0 + margin],
    ]


if __name__ == "__main__":
    w = walkable()
    print(w.wkt)
    print(f"walkable area {w.area:.1f} m2")
