"""
los_distance.py

Line-of-sight (LOS) and gunfire-probability estimation between two vehicle
avatars on a 2D map, parsed from a text map file.

-------------------------------------------------------------------------
MAP FILE FORMAT (confirmed from a real sample map):

Each line is a Python dict literal (single-quoted, not JSON). The object
type is identified by a repeated key, e.g. {'Rect': 'Rect', ...}. Fields
seen so far:

    {'map_size': '32X32'}                                  # header line
    {'Rect': 'Rect', 'local_x_qty': W, 'local_y_qty': H,
     'local_starting_x_qty': X, 'local_starting_y_qty': Y, ...}
        -> solid rectangle, (X, Y) is the BOTTOM-LEFT corner, in game
           lengths. Confirmed by the border-wall rects tiling exactly
           around the map with gaps at the StartingPosition gates.

    {'Polygon': 'Polygon',
     'list_of_tuples': [(x1, y1), (x2, y2), ...], ...}
        -> solid polygon. IMPORTANT: unlike every other object type,
           these coordinates are in PIXELS, not game lengths (confirmed:
           a 32-game-length map's far corner shows up as ~1280px in the
           polygon data). We divide by GAME_LENGTH_PX on load so every
           obstacle ends up in the same (game-length) coordinate space.

    {'CarPosition': 'CarPosition', 'player_number': N, 'owner': 'name',
     'local_starting_x_qty': X, 'local_starting_y_qty': Y, ...}
        -> a vehicle avatar. player_number (falling back to owner) is
           used as the car's id.

    {'Circle': 'Circle', 'local_starting_x_qty': CX,
     'local_starting_y_qty': CY, 'radius_qty': R, ...}
    {'Arc': 'Arc', 'local_starting_x_qty': CX, 'local_starting_y_qty': CY,
     'radius_qty': R, 'start_angle': deg, 'end_angle': deg, ...}
        -> not seen in the sample yet, so field names (radius_qty,
           start_angle, end_angle) are a best guess. Update
           `_record_to_obstacle` once a real Circle/Arc line shows up.

    {'StartingPosition': ...}, {'Text': ...}, {'MovementQueue': ...}
        -> parsed but ignored: markers/metadata, not solid geometry.

- All non-Polygon positional fields are in "game lengths"; per the
  to-hit rules, 1 game length == 1 inch == 40 pixels in this system.
- Blank lines are skipped. A line that fails to parse raises a clear
  error naming the line number, rather than failing silently.
-------------------------------------------------------------------------

Core algorithm (as requested):

    1. Given Car A and Car B: is there LOS between them?
       -> straight segment A-B tested against every solid obstacle.
    2. If LOS exists: how far apart are they (game lengths / pixels)?
    3. Combine into a rough hit-probability estimate (placeholder model,
       easy to swap out later for a real ballistics/accuracy curve).
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


GAME_LENGTH_PX = 40  # 1 "game length" unit == 40 pixels


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

Point = Tuple[float, float]


def _orientation(a: Point, b: Point, c: Point) -> float:
    """Cross-product sign test used for segment intersection."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    """True if p lies on segment a-b, given a, b, p are collinear."""
    return (
        min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Standard orientation-based segment/segment intersection test."""
    o1 = _orientation(p1, p2, p3)
    o2 = _orientation(p1, p2, p4)
    o3 = _orientation(p3, p4, p1)
    o4 = _orientation(p3, p4, p2)

    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)):
        return True

    # Collinear special cases
    if abs(o1) < 1e-9 and _on_segment(p1, p2, p3):
        return True
    if abs(o2) < 1e-9 and _on_segment(p1, p2, p4):
        return True
    if abs(o3) < 1e-9 and _on_segment(p3, p4, p1):
        return True
    if abs(o4) < 1e-9 and _on_segment(p3, p4, p2):
        return True

    return False


def point_in_polygon(pt: Point, poly: List[Point]) -> bool:
    """Ray-casting point-in-polygon test (handles convex & concave)."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1
        ):
            inside = not inside
    return inside


def segment_circle_intersects(p1: Point, p2: Point, center: Point, radius: float) -> bool:
    """True if segment p1-p2 passes within `radius` of `center`."""
    (x1, y1), (x2, y2) = p1, p2
    cx, cy = center

    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - cx, y1 - cy

    a = dx * dx + dy * dy
    if a == 0:
        # Degenerate segment (a point) -- just check distance
        return math.hypot(fx, fy) <= radius

    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius

    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return False

    discriminant = math.sqrt(discriminant)
    t1 = (-b - discriminant) / (2 * a)
    t2 = (-b + discriminant) / (2 * a)

    return (0 <= t1 <= 1) or (0 <= t2 <= 1) or (t1 < 0 < t2)


def _angle_deg(center: Point, p: Point) -> float:
    ang = math.degrees(math.atan2(p[1] - center[1], p[0] - center[0]))
    return ang % 360


def _angle_in_arc(angle: float, start_deg: float, end_deg: float) -> bool:
    start, end = start_deg % 360, end_deg % 360
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end  # arc wraps past 360


def segment_arc_intersects(
    p1: Point, p2: Point, center: Point, radius: float, start_deg: float, end_deg: float
) -> bool:
    """
    Treat the arc as the boundary curve of a circle, restricted to an
    angular range. We find where the segment crosses the *full* circle,
    then keep only crossings whose angle (from center) falls within
    [start_deg, end_deg].
    """
    (x1, y1), (x2, y2) = p1, p2
    cx, cy = center
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - cx, y1 - cy

    a = dx * dx + dy * dy
    if a == 0:
        if math.hypot(fx, fy) <= radius:
            return _angle_in_arc(_angle_deg(center, p1), start_deg, end_deg)
        return False

    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return False
    discriminant = math.sqrt(discriminant)

    for t in ((-b - discriminant) / (2 * a), (-b + discriminant) / (2 * a)):
        if 0 <= t <= 1:
            hit_point = (x1 + t * dx, y1 + t * dy)
            if _angle_in_arc(_angle_deg(center, hit_point), start_deg, end_deg):
                return True
    return False


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass
class Car:
    player_id: str
    x: float
    y: float
    orientation_deg: float = 0.0  # facing direction (compass-style: 0=N,90=E,180=S,270=W)
    heading_deg: float = 0.0      # direction of travel (may differ from facing)
    speed_mph: float = 0.0
    # Physical footprint, in inches (== game lengths). Not present in the
    # map file format seen so far -- these are placeholder defaults (the
    # stated 2:1 length:width ratio, no confirmed scale). Override per
    # car once real vehicle dimensions are available. Used by
    # weapon_mount.py to compute where a weapon on a given edge fires
    # from.
    length_inches: float = 1.0
    width_inches: float = 0.5

    @property
    def pos(self) -> Point:
        return (self.x, self.y)


@dataclass
class Obstacle:
    """Base class for solid, LOS-blocking map objects."""

    kind: str

    def blocks(self, p1: Point, p2: Point) -> bool:
        raise NotImplementedError


@dataclass
class RectObstacle(Obstacle):
    x: float
    y: float
    width: float
    height: float
    kind: str = field(default="Rect", init=False)

    def blocks(self, p1: Point, p2: Point) -> bool:
        x0, y0 = self.x, self.y
        x1, y1 = self.x + self.width, self.y + self.height
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

        # Either endpoint inside the rect counts as blocked (car "in cover").
        if x0 <= p1[0] <= x1 and y0 <= p1[1] <= y1:
            return True
        if x0 <= p2[0] <= x1 and y0 <= p2[1] <= y1:
            return True

        for i in range(4):
            edge_a, edge_b = corners[i], corners[(i + 1) % 4]
            if segments_intersect(p1, p2, edge_a, edge_b):
                return True
        return False


@dataclass
class CircleObstacle(Obstacle):
    cx: float
    cy: float
    radius: float
    kind: str = field(default="Circle", init=False)

    def blocks(self, p1: Point, p2: Point) -> bool:
        return segment_circle_intersects(p1, p2, (self.cx, self.cy), self.radius)


@dataclass
class PolygonObstacle(Obstacle):
    vertices: List[Point]
    kind: str = field(default="Polygon", init=False)

    def blocks(self, p1: Point, p2: Point) -> bool:
        if point_in_polygon(p1, self.vertices) or point_in_polygon(p2, self.vertices):
            return True
        n = len(self.vertices)
        for i in range(n):
            edge_a = self.vertices[i]
            edge_b = self.vertices[(i + 1) % n]
            if segments_intersect(p1, p2, edge_a, edge_b):
                return True
        return False


@dataclass
class ArcObstacle(Obstacle):
    cx: float
    cy: float
    radius: float
    start_deg: float
    end_deg: float
    kind: str = field(default="Arc", init=False)

    def blocks(self, p1: Point, p2: Point) -> bool:
        return segment_arc_intersects(
            p1, p2, (self.cx, self.cy), self.radius, self.start_deg, self.end_deg
        )


# ---------------------------------------------------------------------------
# Map parsing
# ---------------------------------------------------------------------------

_NON_GEOMETRY_TYPES = {"StartingPosition", "Text", "MovementQueue"}
_TYPE_KEYS = (
    "Rect",
    "Polygon",
    "Circle",
    "Arc",
    "CarPosition",
    "StartingPosition",
    "Text",
    "MovementQueue",
)


def _identify_record_type(record: dict) -> Optional[str]:
    """The object type is given by a repeated key, e.g. {'Rect': 'Rect', ...}."""
    for key in _TYPE_KEYS:
        if key in record:
            return key
    return None


def _record_to_obstacle(record: dict, record_type: str) -> Optional[Obstacle]:
    if record_type == "Rect":
        return RectObstacle(
            x=float(record["local_starting_x_qty"]),
            y=float(record["local_starting_y_qty"]),
            width=float(record["local_x_qty"]),
            height=float(record["local_y_qty"]),
        )

    if record_type == "Polygon":
        # NOTE: polygon coordinates are in pixels, not game lengths --
        # see the module docstring. Normalize to game lengths here so
        # every obstacle shares one coordinate space.
        verts_px = record["list_of_tuples"]
        verts_gl = [(px / GAME_LENGTH_PX, py / GAME_LENGTH_PX) for px, py in verts_px]
        return PolygonObstacle(verts_gl)

    if record_type == "Circle":
        # Field name for radius hasn't been confirmed against a real
        # sample yet -- adjust here once one is available.
        radius = record.get("radius_qty", record.get("local_radius_qty"))
        return CircleObstacle(
            cx=float(record["local_starting_x_qty"]),
            cy=float(record["local_starting_y_qty"]),
            radius=float(radius),
        )

    if record_type == "Arc":
        radius = record.get("radius_qty", record.get("local_radius_qty"))
        return ArcObstacle(
            cx=float(record["local_starting_x_qty"]),
            cy=float(record["local_starting_y_qty"]),
            radius=float(radius),
            start_deg=float(record.get("start_angle", 0.0)),
            end_deg=float(record.get("end_angle", 360.0)),
        )

    return None


def parse_map_file(path: str) -> Tuple[List[Car], List[Obstacle]]:
    """Parse a map file (one Python dict literal per line) into cars and
    solid obstacles. StartingPosition / Text / MovementQueue records are
    read but ignored, since they aren't LOS-blocking geometry.
    """
    cars: List[Car] = []
    obstacles: List[Obstacle] = []

    with open(path, "r") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = ast.literal_eval(line)
            except (ValueError, SyntaxError) as exc:
                raise ValueError(f"Could not parse map line {line_no}: {line!r}") from exc

            if not isinstance(record, dict):
                continue

            if "map_size" in record and len(record) == 1:
                continue  # header line -- not currently used downstream

            record_type = _identify_record_type(record)
            if record_type is None:
                continue  # unrecognized object type; skip rather than fail

            if record_type == "CarPosition":
                player_id = str(record.get("player_number", record.get("owner")))
                cars.append(
                    Car(
                        player_id,
                        float(record["local_starting_x_qty"]),
                        float(record["local_starting_y_qty"]),
                        orientation_deg=float(record.get("orientation", 0.0)),
                        heading_deg=float(record.get("heading", record.get("orientation", 0.0))),
                        speed_mph=float(record.get("current_speed", 0.0)),
                    )
                )
            elif record_type in _NON_GEOMETRY_TYPES:
                continue
            else:
                obstacle = _record_to_obstacle(record, record_type)
                if obstacle is not None:
                    obstacles.append(obstacle)

    return cars, obstacles


# ---------------------------------------------------------------------------
# Step 1: Line of sight
# ---------------------------------------------------------------------------

def has_line_of_sight(p1: Point, p2: Point, obstacles: List[Obstacle]) -> bool:
    """Returns True if nothing in `obstacles` blocks the straight line
    between p1 and p2."""
    for obstacle in obstacles:
        if obstacle.blocks(p1, p2):
            return False
    return True


# ---------------------------------------------------------------------------
# Step 2: Distance
# ---------------------------------------------------------------------------

def distance_game_lengths(p1: Point, p2: Point) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def distance_pixels(p1: Point, p2: Point) -> float:
    return distance_game_lengths(p1, p2) * GAME_LENGTH_PX


# ---------------------------------------------------------------------------
# Step 3: Distance-to-target (only) LOS/distance report.
#
# The actual to-hit / probability math (base to-hit, range modifier,
# 2d6 odds) now lives in firing_solution.py, since it's game-rule logic
# rather than geometry. This module stays focused on parsing the map and
# answering "is there LOS?" / "how far apart are they?".
# ---------------------------------------------------------------------------

@dataclass
class EngagementResult:
    car_a: str
    car_b: str
    los: bool
    distance_game_lengths: float
    distance_pixels: float


def evaluate_engagement(car_a: Car, car_b: Car, obstacles: List[Obstacle]) -> EngagementResult:
    """Runs steps 1-2 of the algorithm for one pair of cars:
    1. Is there LOS from Car A to Car B?
    2. How far away are they?
    """
    los = has_line_of_sight(car_a.pos, car_b.pos, obstacles)
    dist_gl = distance_game_lengths(car_a.pos, car_b.pos)

    return EngagementResult(
        car_a=car_a.player_id,
        car_b=car_b.player_id,
        los=los,
        distance_game_lengths=dist_gl,
        distance_pixels=dist_gl * GAME_LENGTH_PX,
    )


def evaluate_all_pairs(cars: List[Car], obstacles: List[Obstacle]) -> List[EngagementResult]:
    """Evaluates every unique pair of cars on the map."""
    results = []
    for i in range(len(cars)):
        for j in range(i + 1, len(cars)):
            results.append(evaluate_engagement(cars[i], cars[j], obstacles))
    return results


if __name__ == "__main__":
    cars, obstacles = parse_map_file("sample_map.txt")
    print(f"Parsed {len(cars)} cars and {len(obstacles)} obstacles.\n")

    for result in evaluate_all_pairs(cars, obstacles):
        print(
            f"{result.car_a} -> {result.car_b}: "
            f"LOS={result.los}, "
            f"dist={result.distance_game_lengths:.2f} in "
            f"({result.distance_pixels:.0f} px)"
        )