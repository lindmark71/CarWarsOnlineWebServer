"""
firing_solution.py

To-hit calculation for the Firing Action dialog, built on top of
los_distance.py's LOS and distance functions.

-------------------------------------------------------------------------
MECHANIC (2d6, roll-high system):

    Roll 2d6. Add the range modifier to the roll. If the modified roll
    is >= the weapon's base to-hit number, the shot hits.

        (2d6 roll + range_modifier) >= base_to_hit

INTERPRETATION NOTE ON SIGN CONVENTION:
    The range-modifier table you gave goes +4 (<=1"), 0 (1-4"), -1 (4-8"),
    -2 (8-12"), decreasing by another -1 every additional 4" -- and you
    said this should create a functional maximum range beyond which
    hitting is mathematically impossible.

    For that to be true, the modifier has to make shots *harder* as it
    gets more negative. That only works if the modifier is a bonus/
    penalty applied to the die roll (the standard tabletop convention:
    "+4 to hit" = roll better, "-2 to hit" = roll worse) -- NOT something
    added to the target number itself (which would do the opposite:
    close-range shots would get harder and long-range shots easier).
    This module implements the roll-modifier interpretation.

    For convenience/display, this is restated as a single adjusted
    target number:

        adjusted_to_hit = base_to_hit - range_modifier

    which is algebraically identical (roll >= base - modifier is the
    same statement as roll + modifier >= base), but easier to show on a
    dialog as one number. At long range, adjusted_to_hit climbs past 12
    (the max possible 2d6 roll), which is exactly the "impossible to
    hit" cutoff you described.

    If this reads backwards from what you intended, the fix is a
    one-line flip in `to_hit_target_number` below -- everything else
    (dice odds, tests) stays valid either way.
-------------------------------------------------------------------------

RANGE MODIFIER TABLE (distance in inches; recall 1 inch == 1 game length
== 40 pixels in this system, so distances from los_distance.py's
distance_game_lengths() can be used directly as inches):

    distance <= 1                : +4
    1 <  distance <= 4            :  0
    4 <  distance <= 8            : -1
    8 <  distance <= 12           : -2
    12 <  distance <= 16          : -3
    ... an additional -1 for every further 4" beyond 12"
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from los_distance import Car, Obstacle, has_line_of_sight, distance_game_lengths
from arc_and_speed import speed_arc_modifier, arc_classification
from weapon_mount import Weapon, WeaponFacing, weapon_mount_position
from to_hit_modifiers import (
    TargetProfile,
    FiringEquipment,
    Obscurant,
    body_type_modifier,
    sloped_armor_modifier,
    called_shot_modifier,
    target_facing_modifier,
    stationary_modifier,
    equipment_modifier,
    cloud_los_modifier,
)


# ---------------------------------------------------------------------------
# Range modifier
# ---------------------------------------------------------------------------

_EPSILON = 1e-9  # guards against float rounding landing just past a boundary


def range_modifier(distance_inches: float) -> int:
    """Returns the roll modifier for a given range, per the table above."""
    if distance_inches < 0:
        raise ValueError("distance_inches cannot be negative")

    if distance_inches <= 1 + _EPSILON:
        return 4
    if distance_inches <= 4 + _EPSILON:
        return 0

    # Every 4" beyond the first 4" knocks off another -1, and the first
    # such bracket (4", 8"] is -1 (not -0), hence the +1.
    steps_beyond_four = math.ceil((distance_inches - 4 - _EPSILON) / 4)
    return -steps_beyond_four


# ---------------------------------------------------------------------------
# 2d6 dice odds
# ---------------------------------------------------------------------------

# Number of ways (out of 36) to roll each sum on 2d6.
_DICE_SUM_COMBINATIONS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
_TOTAL_COMBINATIONS = 36


def hit_probability_2d6(target_number: int) -> float:
    """P(2d6 roll >= target_number). 0.0 for target_number > 12 (impossible),
    1.0 for target_number <= 2 (guaranteed, since 2 is the minimum roll)."""
    if target_number <= 2:
        return 1.0
    if target_number > 12:
        return 0.0
    favorable = sum(count for roll, count in _DICE_SUM_COMBINATIONS.items() if roll >= target_number)
    return favorable / _TOTAL_COMBINATIONS


# ---------------------------------------------------------------------------
# To-hit target number
# ---------------------------------------------------------------------------

def to_hit_target_number(base_to_hit: int, distance_inches: float) -> int:
    """The single adjusted target number a 2d6 roll must meet or beat.
    See the sign-convention note in the module docstring."""
    return base_to_hit - range_modifier(distance_inches)


# ---------------------------------------------------------------------------
# Orchestration: LOS + distance + to-hit, in one call, per the algorithm
# ("is there LOS? -> how far away? -> [now] what's the to-hit?")
# ---------------------------------------------------------------------------

@dataclass
class FiringSolution:
    shooter_id: str
    target_id: str
    weapon_id: Optional[str]        # None when called without a specific weapon (legacy center-to-center mode)
    weapon_name: Optional[str]
    origin: tuple                   # the point range/LOS were actually measured from
    los: bool
    distance_inches: float
    base_to_hit: int
    range_modifier: int
    speed_arc_modifier: int
    target_arc: Optional[str]   # target's position in the shooter's arc: 'Front'/'Back'/'Side'
    firer_arc: Optional[str]    # shooter's position in the target's arc: 'Front'/'Back'/'Side'
    other_modifiers: dict       # name -> int, e.g. {'stationary': 1, 'sloped_armor': -1, ...}
    total_modifier: int
    adjusted_to_hit: Optional[int]  # None when there's no LOS at all
    possible: bool                  # False if no LOS, or modifiers make it unhittable
    hit_probability: float


def compute_firing_solution(
    shooter: Car,
    target: Car,
    obstacles: List[Obstacle],
    base_to_hit: int,
    target_profile: Optional[TargetProfile] = None,
    equipment: Optional[FiringEquipment] = None,
    clouds: Optional[List[Obscurant]] = None,
    weapon_facing: Optional[WeaponFacing] = None,
    weapon_id: Optional[str] = None,
    weapon_name: Optional[str] = None,
) -> FiringSolution:
    """Computes one weapon's firing solution against one target. If
    weapon_facing is given, range and LOS are measured from that
    weapon's actual mount point on the vehicle (edge midpoint, or the
    exact center for a turret) rather than the car's center -- per the
    rule that different weapons on the same car can measure genuinely
    different ranges to the same target. Arc/speed classification still
    uses the car's overall center and orientation regardless of mount."""
    origin = weapon_mount_position(shooter, weapon_facing) if weapon_facing else shooter.pos

    los = has_line_of_sight(origin, target.pos, obstacles)
    distance = distance_game_lengths(origin, target.pos)  # already inches

    if not los:
        return FiringSolution(
            shooter_id=shooter.player_id,
            target_id=target.player_id,
            weapon_id=weapon_id,
            weapon_name=weapon_name,
            origin=origin,
            los=False,
            distance_inches=distance,
            base_to_hit=base_to_hit,
            range_modifier=0,
            speed_arc_modifier=0,
            target_arc=None,
            firer_arc=None,
            other_modifiers={},
            total_modifier=0,
            adjusted_to_hit=None,
            possible=False,
            hit_probability=0.0,
        )

    r_modifier = range_modifier(distance)
    s_modifier = speed_arc_modifier(shooter, target)
    target_arc, firer_arc = arc_classification(shooter, target)

    other = {
        "stationary": stationary_modifier(shooter.speed_mph, target.speed_mph),
        "target_body_type": body_type_modifier(target_profile),
        "target_facing": target_facing_modifier(firer_arc),
        "sloped_armor": sloped_armor_modifier(target_profile),
        "called_shot": called_shot_modifier(target_profile),
        "equipment": equipment_modifier(equipment),
        "clouds": cloud_los_modifier(origin, target.pos, clouds),
    }
    # Drop zero-value entries so the breakdown only shows what mattered.
    other = {name: value for name, value in other.items() if value != 0}

    total_modifier = r_modifier + s_modifier + sum(other.values())
    adjusted = base_to_hit - total_modifier
    possible = adjusted <= 12
    probability = hit_probability_2d6(adjusted) if possible else 0.0

    return FiringSolution(
        shooter_id=shooter.player_id,
        target_id=target.player_id,
        weapon_id=weapon_id,
        weapon_name=weapon_name,
        origin=origin,
        los=True,
        distance_inches=distance,
        base_to_hit=base_to_hit,
        range_modifier=r_modifier,
        speed_arc_modifier=s_modifier,
        target_arc=target_arc,
        firer_arc=firer_arc,
        other_modifiers=other,
        total_modifier=total_modifier,
        adjusted_to_hit=adjusted,
        possible=possible,
        hit_probability=probability,
    )


def compute_weapon_firing_solutions(
    shooter: Car,
    weapons: List[Weapon],
    target: Car,
    obstacles: List[Obstacle],
    target_profile: Optional[TargetProfile] = None,
    equipment: Optional[FiringEquipment] = None,
    clouds: Optional[List[Obscurant]] = None,
) -> dict:
    """Computes a separate FiringSolution per weapon against one target,
    keyed by weapon_id -- for the Firing Action dialog to present every
    weapon's odds independently once a crew member/weapon combination is
    selected."""
    return {
        weapon.weapon_id: compute_firing_solution(
            shooter,
            target,
            obstacles,
            weapon.base_to_hit,
            target_profile=target_profile,
            equipment=equipment,
            clouds=clouds,
            weapon_facing=weapon.facing,
            weapon_id=weapon.weapon_id,
            weapon_name=weapon.name,
        )
        for weapon in weapons
    }


if __name__ == "__main__":
    from los_distance import parse_map_file

    cars, obstacles = parse_map_file("sample_map.txt")
    cars_by_id = {c.player_id: c for c in cars}

    p1, p2 = cars_by_id["1"], cars_by_id["2"]

    weapons = [
        Weapon(weapon_id="w_front", name="Front MG", facing="Front", base_to_hit=7),
        Weapon(weapon_id="w_turret", name="Turret Cannon", facing="Turret", base_to_hit=8),
        Weapon(weapon_id="w_left", name="Left Rocket Pod", facing="Left", base_to_hit=7),
    ]

    solutions = compute_weapon_firing_solutions(p1, weapons, p2, obstacles)

    print(f"Player {p1.player_id} firing at Player {p2.player_id}, per weapon:")
    for weapon in weapons:
        s = solutions[weapon.weapon_id]
        print(f"\n  {s.weapon_name} ({weapon.facing}):")
        print(f"    Origin: ({s.origin[0]:.2f}, {s.origin[1]:.2f})")
        print(f"    LOS: {s.los}")
        print(f"    Distance: {s.distance_inches:.2f} inches")
        if s.los:
            print(f"    Range modifier: {s.range_modifier:+d}")
            print(f"    Speed/arc modifier: {s.speed_arc_modifier:+d} "
                  f"(target in shooter's {s.target_arc} arc, shooter in target's {s.firer_arc} arc)")
            for name, value in s.other_modifiers.items():
                print(f"    {name}: {value:+d}")
            print(f"    Total modifier: {s.total_modifier:+d}")
            print(f"    Adjusted to-hit: {s.adjusted_to_hit}")
            print(f"    Possible: {s.possible}")
            print(f"    Hit probability: {s.hit_probability:.2%}")