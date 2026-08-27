"""
to_hit_modifiers.py

The rest of the to-hit modifiers beyond range and speed/arc: stationary
bonuses, target size/armor/facing, called shots against specific
components, firing-vehicle targeting equipment, and LOS-obscuring
clouds (smoke/flame/paint).

Every function here returns a signed integer ROLL modifier, using the
same convention as range_modifier() and speed_arc_modifier(): positive
= bonus (easier), negative = penalty (harder). Sum everything and add
it to the roll (equivalently, subtract the total from the base to-hit
to get a single adjusted target number) -- see compute_firing_solution()
in firing_solution.py, which does this.

-------------------------------------------------------------------------
ASSUMPTIONS (flagged explicitly):

1. TARGETING EQUIPMENT TIERS DON'T STACK. "Targeting computer or single
   weapon computer" (+1), "hi-res ..." (+2), and cyberlink (+3) are
   treated as tiers of one system -- a car has at most one -- so the
   HIGHEST applicable bonus is used, not a sum of all installed
   equipment. If a vehicle can genuinely carry more than one of these
   at once and they should stack, change `equipment_modifier()` to sum
   instead of `max()`.

2. TARGET FACING REUSES THE ARC ROW. "-1 if target facing is front or
   back" is implemented as: -1 when the FIRER falls in the TARGET's
   front or back arc (the same "row" classification used for the speed/
   arc grid), since that's what determines whether the target presents
   its narrow (front/back) or broad (side) silhouette to the shot.

3. CLOUDS ARE CIRCLES. Smoke/flame/paint clouds aren't in the map file
   format seen so far, so `Obscurant` models them as a circle (center +
   radius) in game lengths/inches -- the common representation for
   blast/gas clouds in this genre of game. Update this once a real
   dropped-weapon map record format is available.

4. OBSCURATION IS TOTALED, THEN ROUNDED ONCE. If the LOS line passes
   through multiple clouds, their intersection lengths are summed first,
   and "-1 per 1/2 inch or fraction thereof" is applied to that total --
   not computed and rounded up separately per cloud. (E.g. 0.3" through
   one cloud plus 0.3" through another totals 0.6" -> 2 units of
   penalty, not 1+1 computed independently, though in this example the
   two approaches happen to agree; they can diverge for smaller
   fractions.)

5. GUNNER SKILL: NOT YET IMPLEMENTED. Per your note that crew skills are
   coming later, no gunner-skill modifier is computed here. Once that
   system exists, it slots in as one more term summed into
   `compute_firing_solution()`'s total modifier (+1 for skill 1, +2 for
   skill 2, per what you described).

6. DROPPED WEAPONS (dropped solid/liquid/gas) beyond the LOS-obscuration
   rule above aren't implemented yet, since no further rules have been
   given.
-------------------------------------------------------------------------
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from los_distance import Point


_SMALL_BODY_TYPES = {"subcompact", "compact"}
_HALF_INCH = 0.5


# ---------------------------------------------------------------------------
# Target profile (vehicle-spec data, not part of the position map file)
# ---------------------------------------------------------------------------

@dataclass
class TargetProfile:
    body_type: Optional[str] = None      # e.g. "Subcompact", "Compact", "Sedan", ...
    sloped_armor: bool = False
    aimed_component: str = "hull"        # "hull" | "turret" | "wheel"


def body_type_modifier(target_profile: Optional[TargetProfile]) -> int:
    if target_profile is None or target_profile.body_type is None:
        return 0
    return -1 if target_profile.body_type.strip().lower() in _SMALL_BODY_TYPES else 0


def sloped_armor_modifier(target_profile: Optional[TargetProfile]) -> int:
    if target_profile is None:
        return 0
    return -1 if target_profile.sloped_armor else 0


def called_shot_modifier(target_profile: Optional[TargetProfile]) -> int:
    if target_profile is None:
        return 0
    component = target_profile.aimed_component.strip().lower()
    if component == "turret":
        return -2
    if component == "wheel":
        return -3
    return 0


def target_facing_modifier(firer_arc: Optional[str]) -> int:
    """-1 if the firer falls within the target's front or back arc
    (narrow silhouette); 0 if in the target's side arc (broad
    silhouette) or unknown."""
    if firer_arc in ("Front", "Back"):
        return -1
    return 0


# ---------------------------------------------------------------------------
# Stationary bonuses
# ---------------------------------------------------------------------------

def stationary_modifier(shooter_speed_mph: float, target_speed_mph: float) -> int:
    bonus = 0
    if shooter_speed_mph == 0:
        bonus += 1
    if target_speed_mph == 0:
        bonus += 1
    return bonus


# ---------------------------------------------------------------------------
# Firing-vehicle equipment
# ---------------------------------------------------------------------------

@dataclass
class FiringEquipment:
    targeting_computer: bool = False
    single_weapon_computer: bool = False
    hires_targeting_computer: bool = False
    hires_single_weapon_computer: bool = False
    cyberlink: bool = False
    # gunner_skill intentionally omitted -- see assumption #5 above.


def equipment_modifier(equipment: Optional[FiringEquipment]) -> int:
    if equipment is None:
        return 0

    best = 0
    if equipment.targeting_computer or equipment.single_weapon_computer:
        best = max(best, 1)
    if equipment.hires_targeting_computer or equipment.hires_single_weapon_computer:
        best = max(best, 2)
    if equipment.cyberlink:
        best = max(best, 3)
    return best


# ---------------------------------------------------------------------------
# Smoke / flame / paint clouds (LOS obscuration)
# ---------------------------------------------------------------------------

@dataclass
class Obscurant:
    """A cloud (smoke, flame, or paint) that degrades LOS through it
    without blocking it outright. See assumption #3 -- modeled as a
    circle until a real map format is available."""

    cx: float
    cy: float
    radius: float

    def intersection_length(self, p1: Point, p2: Point) -> float:
        """Length of the segment p1-p2 that lies inside this cloud."""
        (x1, y1), (x2, y2) = p1, p2
        dx, dy = x2 - x1, y2 - y1
        fx, fy = x1 - self.cx, y1 - self.cy

        a = dx * dx + dy * dy
        if a == 0:
            return 0.0

        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - self.radius * self.radius
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return 0.0

        sqrt_disc = math.sqrt(discriminant)
        t_enter = max(0.0, (-b - sqrt_disc) / (2 * a))
        t_exit = min(1.0, (-b + sqrt_disc) / (2 * a))
        if t_exit <= t_enter:
            return 0.0

        segment_length = math.sqrt(a)
        return (t_exit - t_enter) * segment_length


def cloud_los_modifier(p1: Point, p2: Point, clouds: Optional[List[Obscurant]]) -> int:
    """-1 for every 1/2 inch (or fraction thereof) of total obscured
    distance along the LOS line, per assumption #4."""
    if not clouds:
        return 0
    total_length = sum(cloud.intersection_length(p1, p2) for cloud in clouds)
    if total_length <= 0:
        return 0
    units = math.ceil(total_length / _HALF_INCH - 1e-9)
    return -units