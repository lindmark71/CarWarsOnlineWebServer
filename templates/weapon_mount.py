"""
weapon_mount.py

Where a weapon's shots actually originate on the vehicle, based on which
edge it's mounted on (or the turret). Range and LOS are measured from
this point, not the car's center: a front-mounted weapon's range is
drawn from the midpoint of the front edge, a left-mounted weapon's from
the midpoint of the left edge, a turreted weapon's from the vehicle's
exact center, etc.

-------------------------------------------------------------------------
ASSUMPTIONS:

1. CAR DIMENSIONS. The map file format seen so far doesn't carry a car's
   physical length/width, so Car (in los_distance.py) now has
   length_inches / width_inches fields with placeholder defaults (1.0" x
   0.5", the stated 2:1 ratio, no confirmed scale). Override these per
   car once real vehicle dimensions are available -- this module reads
   whatever is on the Car object.

2. MOUNT DOESN'T RESTRICT WHICH TARGETS CAN BE ENGAGED. This module only
   changes WHERE a shot originates, for range/LOS purposes. It does not
   restrict which arc a given mount can fire into (e.g. a Left-mounted
   weapon can still target something in the vehicle's front arc). The
   speed/arc grid in arc_and_speed.py is computed from the car's center
   and orientation regardless of which specific weapon is firing. If
   mount-based firing-arc restrictions are wanted, that's a separate
   rule to add on top of this.
-------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass

from los_distance import Car, Point
from arc_and_speed import heading_unit_vector


WeaponFacing = str  # 'Front' | 'Back' | 'Left' | 'Right' | 'Turret'

_VALID_FACINGS = {"Front", "Back", "Left", "Right", "Turret"}


@dataclass
class Weapon:
    weapon_id: str
    name: str
    facing: WeaponFacing
    base_to_hit: int


def weapon_mount_position(car: Car, facing: WeaponFacing) -> Point:
    """World position (inches / game lengths) that a weapon on the given
    facing fires from. Turret weapons fire from the car's exact center;
    edge-mounted weapons fire from the midpoint of that edge."""
    if facing not in _VALID_FACINGS:
        raise ValueError(
            f"Unrecognized weapon facing: {facing!r} (expected one of {sorted(_VALID_FACINGS)})"
        )

    if facing == "Turret":
        return car.pos

    fwd = heading_unit_vector(car.orientation_deg)
    right = heading_unit_vector(car.orientation_deg + 90)
    half_length = car.length_inches / 2
    half_width = car.width_inches / 2

    if facing == "Front":
        dx, dy = fwd[0] * half_length, fwd[1] * half_length
    elif facing == "Back":
        dx, dy = -fwd[0] * half_length, -fwd[1] * half_length
    elif facing == "Right":
        dx, dy = right[0] * half_width, right[1] * half_width
    else:  # "Left"
        dx, dy = -right[0] * half_width, -right[1] * half_width

    return (car.x + dx, car.y + dy)