"""
arc_and_speed.py

Target-speed to-hit modifier, based on firing arc (Front/Back/Side) of
both the firer and the target relative to each other.

-------------------------------------------------------------------------
ASSUMPTIONS (flagged explicitly -- correct these if they don't match the
actual rulebook):

1. SPEED -> PENALTY MAGNITUDE, COMBINED IN RAW MPH.
   "At 30 mph, -1 to hit. At 40 mph, -2 to hit," continuing forever,
   implies a bracket of +10 mph per additional point, starting at 30:

       0-29 mph  : 0
       30-39 mph : 1
       40-49 mph : 2
       50-59 mph : 3   ... etc.

   CONFIRMED: the grid's T Speed / F Speed are combined as RAW MPH
   first (e.g. target_mph - firer_mph), and the mph-to-penalty lookup
   above is applied ONCE, at the end, to that combined number -- not
   applied separately to each car's speed before combining. Any
   negative combined result is clamped to 0 mph (a slow target facing
   a fast pursuer isn't a bonus, just "no penalty").

2. ARC ANGLES. Using the stated 60/60/120/120 degree sectors directly
   (Front: heading +/-30 degrees, Back: heading+180 +/-30 degrees, Side:
   the remaining 120 degrees on each flank) rather than re-deriving the
   angle from the 2:1 rectangle's corner diagonals (which would actually
   give ~53/53/127/127 degrees, not round numbers). Left and Right are
   merged into a single "Side" category since the grid you gave doesn't
   distinguish between them.

3. FACING VS. TRAVEL DIRECTION. Car records carry both `orientation` and
   `heading`. This module uses `orientation` for which way the car (and
   its firing arcs) point, and `heading` only to compute each car's
   velocity vector for the "moving towards each other" test in the
   Side/Side cell. They're identical in the one sample seen so far, so
   this can't be confirmed from data alone.

4. SIDE/SIDE IS HALVED TOO. CONFIRMED: even though the table you first
   gave showed the Side/Side (not-closing) cell as plain "T - F" with no
   "1/2", it should be halved like the cross cells, since side-to-side
   is meant to be the easiest case (smallest penalty) and Row Side /
   Col Front|Back (full, un-halved T) is meant to be the worst.

5. ARC BOUNDARY TIES. "If a vehicle is in more than one arc, rule in the
   defender's favor" is implemented by: when a relative bearing lands
   exactly on a 30 degree or 150 degree boundary, both candidate arcs
   are evaluated and the one giving the larger resulting mph value
   (worse for the shooter, i.e. better for the target/defender) is used.
-------------------------------------------------------------------------

GRID (row = "Firer is in Target's ___ arc", col = "Target is in Firer's
___ arc"), values are combined in raw MPH, then run through the
mph-to-penalty lookup once:

                  Col: Front         Col: Back            Col: Side
    Row Front   | 1/2 T             | 1/2 (T - F)         | 1/2 T
    Row Back    | 1/2 (T - F)       | 1/2 T                | 1/2 T
    Row Side    | T                 | T                    | 1/2 (T - F)*

    * Side/Side: if the two cars are closing on each other, use T alone
      (full, un-halved) instead of 1/2 (T - F).
"""

from __future__ import annotations

import math
from typing import Tuple

from los_distance import Car, Point


ArcLabel = str  # 'Front' | 'Back' | 'Side'

_TIE_EPSILON_DEG = 1e-6


# ---------------------------------------------------------------------------
# Angles and bearings
# ---------------------------------------------------------------------------

def normalize_angle_360(deg: float) -> float:
    """Normalize an angle to [0, 360)."""
    return deg % 360


def normalize_angle_relative(deg: float) -> float:
    """Normalize an angle to (-180, 180]."""
    d = deg % 360
    if d > 180:
        d -= 360
    return d


def heading_unit_vector(orientation_deg: float) -> Tuple[float, float]:
    """Unit vector for a compass-style heading (0=N/-y, 90=E/+x, 180=S/+y,
    270=W/-x) -- matches the convention implied by the map's
    StartingPosition orientations (spawns facing into the arena)."""
    rad = math.radians(orientation_deg)
    return (math.sin(rad), -math.cos(rad))


def bearing_deg(from_pos: Point, to_pos: Point) -> float:
    """Compass bearing (0-360, same convention as heading_unit_vector) of
    the direction from from_pos to to_pos."""
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if dx == 0 and dy == 0:
        return 0.0  # coincident positions; bearing is undefined, default to 0
    return normalize_angle_360(math.degrees(math.atan2(dx, -dy)))


def relative_bearing(observer_orientation_deg: float, bearing_to_target_deg: float) -> float:
    """Bearing to a point, relative to the observer's own facing, in
    (-180, 180]. 0 = dead ahead, positive = to the observer's right."""
    return normalize_angle_relative(bearing_to_target_deg - observer_orientation_deg)


def classify_arc(relative_deg: float) -> Tuple[ArcLabel, ...]:
    """Classifies a relative bearing into Front/Back/Side. Returns a
    single-element tuple, except exactly on a 30/150 degree boundary,
    where both candidate arcs are returned (see assumption #5)."""
    r = normalize_angle_relative(relative_deg)
    a = abs(r)

    if abs(a - 30) < _TIE_EPSILON_DEG:
        return ("Front", "Side")
    if abs(a - 150) < _TIE_EPSILON_DEG:
        return ("Back", "Side")
    if a < 30:
        return ("Front",)
    if a > 150:
        return ("Back",)
    return ("Side",)


# ---------------------------------------------------------------------------
# Speed penalty
# ---------------------------------------------------------------------------

def speed_penalty(speed_mph: float) -> int:
    """Non-negative penalty magnitude: 0 below 30 mph, then +1 for every
    additional 10 mph (30-39 -> 1, 40-49 -> 2, ...). See assumption #1."""
    if speed_mph < 0:
        raise ValueError("speed_mph cannot be negative")
    return max(0, math.floor(speed_mph / 10) - 2)


# ---------------------------------------------------------------------------
# Closing-speed test (for the Side/Side cell's footnote)
# ---------------------------------------------------------------------------

def is_closing(firer: Car, target: Car) -> bool:
    """True if the distance between firer and target is currently
    decreasing, given their travel headings and speeds."""
    fvx, fvy = heading_unit_vector(firer.heading_deg)
    tvx, tvy = heading_unit_vector(target.heading_deg)
    fvx, fvy = fvx * firer.speed_mph, fvy * firer.speed_mph
    tvx, tvy = tvx * target.speed_mph, tvy * target.speed_mph

    rel_pos = (target.x - firer.x, target.y - firer.y)
    rel_vel = (tvx - fvx, tvy - fvy)

    closing_rate = rel_pos[0] * rel_vel[0] + rel_pos[1] * rel_vel[1]
    return closing_rate < 0


# ---------------------------------------------------------------------------
# Grid lookup (operates on raw mph; lookup through speed_penalty happens
# once, after combining, in speed_arc_modifier / arc_classification below)
# ---------------------------------------------------------------------------

def _grid_mph_value(row: ArcLabel, col: ArcLabel, t_mph: float, f_mph: float, closing: bool) -> float:
    if row == "Front":
        if col == "Front":
            return 0.5 * t_mph
        if col == "Back":
            return 0.5 * (t_mph - f_mph)
        if col == "Side":
            return 0.5 * t_mph
    elif row == "Back":
        if col == "Front":
            return 0.5 * (t_mph - f_mph)
        if col == "Back":
            return 0.5 * t_mph
        if col == "Side":
            return 0.5 * t_mph
    elif row == "Side":
        if col == "Front":
            return t_mph
        if col == "Back":
            return t_mph
        if col == "Side":
            return t_mph if closing else 0.5 * (t_mph - f_mph)

    raise ValueError(f"Unrecognized arc combination: row={row!r}, col={col!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def speed_arc_modifier(firer: Car, target: Car) -> int:
    """The final to-hit ROLL modifier (0 or negative) contributed by
    target speed and firing arc. Combine additively with range_modifier()
    from firing_solution.py."""
    closing = is_closing(firer, target)

    col_candidates = classify_arc(
        relative_bearing(firer.orientation_deg, bearing_deg(firer.pos, target.pos))
    )
    row_candidates = classify_arc(
        relative_bearing(target.orientation_deg, bearing_deg(target.pos, firer.pos))
    )

    best_mph = max(
        _grid_mph_value(row, col, target.speed_mph, firer.speed_mph, closing)
        for row in row_candidates
        for col in col_candidates
    )
    net_mph = max(0.0, best_mph)
    return -speed_penalty(net_mph)


def arc_classification(firer: Car, target: Car) -> Tuple[ArcLabel, ArcLabel]:
    """Convenience for UI display: returns (target_arc_in_firer_frame,
    firer_arc_in_target_frame), resolving any boundary ties the same way
    speed_arc_modifier does (favoring the defender)."""
    closing = is_closing(firer, target)

    col_candidates = classify_arc(
        relative_bearing(firer.orientation_deg, bearing_deg(firer.pos, target.pos))
    )
    row_candidates = classify_arc(
        relative_bearing(target.orientation_deg, bearing_deg(target.pos, firer.pos))
    )

    best = max(
        ((row, col) for row in row_candidates for col in col_candidates),
        key=lambda rc: _grid_mph_value(rc[0], rc[1], target.speed_mph, firer.speed_mph, closing),
    )
    row, col = best
    return (col, row)  # (target-in-firer's-arc, firer-in-target's-arc)