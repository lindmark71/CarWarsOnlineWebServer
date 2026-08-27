import random

# ==============================================================================
# ── VEHICULAR FIRE MATRIX ─────────────────────────────────────────────────────
# ==============================================================================
VEHICULAR_FIRE_TABLE = {
    "Flamethrower":                   {"modifier": 4, "duration": 3},
    "Heavy-Duty Flamethrower":        {"modifier": 5, "duration": 3},
    "Portable Flamethrower":          {"modifier": 3, "duration": 2},
    "Light Flamethrower":             {"modifier": 2, "duration": 3},
    "High-Temp FT Ammunition":        {"modifier": 1, "duration": 1}, 
    "Flaming Oil Jet":                {"modifier": 3, "duration": 2},
    "Heavy-Duty Flaming Oil Jet":     {"modifier": 3, "duration": 2},
    "Machine Gun Incendiary Ammo":    {"modifier": 2, "duration": 1},
    "Rocket Launcher Incendiary Ammo":{"modifier": 3, "duration": 2},
    "MML Incendiary Ammo":            {"modifier": 2, "duration": 1},
    "Incendiary Mini-Rocket":         {"modifier": 1, "duration": 0},
    "Incendiary Light Rocket":        {"modifier": 2, "duration": 1},
    "Incendiary Medium Rocket":       {"modifier": 3, "duration": 2},
    "Incendiary Heavy Rocket":        {"modifier": 4, "duration": 3}, 
    "Incendiary MFR":                 {"modifier": 3, "duration": 1}, 
    "Light Laser":                    {"modifier": 0, "duration": 0},
    "Medium Laser":                   {"modifier": 1, "duration": 0},
    "Laser":                          {"modifier": 1, "duration": 0},
    "Heavy Laser":                    {"modifier": 2, "duration": 0},
    "Twin Laser":                     {"modifier": 1, "duration": 0},
    "Napalm Mine":                    {"modifier": 4, "duration": 3},
    "Flame Cloud Ejector":            {"modifier": 3, "duration": 1},
    "Heavy-Duty Flame Cloud Ejector": {"modifier": 3, "duration": 1},
    "Flame Cloud Gas Streamer":       {"modifier": 3, "duration": 1}
}

class FireAndExplosionEngine:
    """
    Manages thermal ignition tests using a 2D6 threshold mechanic,
    residual burning lifetimes, and destructive end-of-turn flame cascades.
    """

    @classmethod
    def test_incendiary_ignition(cls, weapon_name: str, target_vehicle: dict) -> dict:
        """
        Rolls 2D6 for the target vehicle to resist ignition.
        If the target rolls ABOVE the Burn Modifier, it does not catch on fire.
        If it rolls EQUAL TO or BELOW the modifier, ignition is confirmed.
        """
        weapon_profile = VEHICULAR_FIRE_TABLE.get(weapon_name, {"modifier": 0, "duration": 0})
        burn_mod = weapon_profile["modifier"]
        max_duration = weapon_profile["duration"]

        if burn_mod == 0 and max_duration == 0:
            return {"ignited": False, "msg": "Weapon lacks thermal or incendiary properties."}

        # Target vehicle rolls 2D6 to resist catching fire
        resistance_roll = random.randint(1, 6) + random.randint(1, 6)
        
        # Fire catches if the resistance roll fails to exceed the weapon's intensity modifier
        is_ignited = resistance_roll <= burn_mod

        if is_ignited and max_duration > 0:
            current_duration = int(target_vehicle.get('fire_burn_duration_remaining', 0))
            target_vehicle['is_on_fire'] = True
            target_vehicle['fire_burn_duration_remaining'] = max(current_duration, max_duration)
            target_vehicle['active_fire_modifier'] = max(int(target_vehicle.get('active_fire_modifier', 0)), burn_mod)
            
            return {
                "ignited": True, "resistance_roll": resistance_roll, "burn_modifier": burn_mod,
                "duration": max_duration,
                "msg": f"IGNITION CONFIRMED! Target rolled {resistance_roll} against a Burn Modifier of {burn_mod}. Hull bursts into flames for {max_duration} turns."
            }

        return {
            "ignited": False, "resistance_roll": resistance_roll, "burn_modifier": burn_mod,
            "msg": f"Ignition resisted. Target rolled {resistance_roll}, successfully beating the Burn Modifier of {burn_mod}."
        }

    @classmethod
    def process_end_of_turn_fire_damage(cls, target_vehicle: dict) -> list:
        """
        Processes damage for burning vehicles at the end of a turn phase.
        A burning vehicle takes 1D6 damage to a randomly determined panel, 
        and the duration counter ticks down by 1.
        """
        if not target_vehicle.get('is_on_fire', False):
            return []

        duration = int(target_vehicle.get('fire_burn_duration_remaining', 0))
        burn_mod = int(target_vehicle.get('active_fire_modifier', 1))
        
        if duration <= 0:
            target_vehicle['is_on_fire'] = False
            return ["The flames on the hull naturally burn out due to lack of fuel components."]

        log = []
        # Roll 1D6 thermal damage. Heavy fire modifiers increase heat intensity.
        flame_damage = random.randint(1, 6) + (burn_mod - 2)
        flame_damage = max(1, flame_damage)

        # Pick a random outer panel facing to absorb the fire damage
        facings = ["Front", "Back", "Left", "Right", "Top", "Underbody"]
        hit_facing = random.choice(facings)

        log.append(f"FIRESTORM TICK: Vehicle burns for {duration} more turns! Flames target the {hit_facing} section.")

        # Route damage down into the structural cascade module
        from combat_physics import CombatPhysicsEngine
        is_linear_cascade = hit_facing in ["Front", "Back"]
        cascade_log = CombatPhysicsEngine.apply_damage_cascade(target_vehicle, flame_damage, hit_facing, is_linear_cascade)
        log.extend(cascade_log)

        # Tick down the burning timeline duration counter
        duration -= 1
        target_vehicle['fire_burn_duration_remaining'] = duration

        if duration == 0:
            target_vehicle['is_on_fire'] = False
            log.append("The fire consumes its remaining thermal energy and goes out at turn conclusion.")

        return log
