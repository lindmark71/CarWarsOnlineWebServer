class CombatModifiersEngine:
    """
    Evaluates multi-tiered Car Wars Targeting Modifier matrices, manages
    speed-band velocity calculations, and handles specific hit components.
    """

    @staticmethod
    def calculate_range_modifier(distance_inches: float) -> int:
        """Point Blank (< 1"): +4. Long Range: -1 for every full 4\"."""
        if distance_inches < 1.0:
            return 4
        if distance_inches >= 4.0:
            return -int(distance_inches // 4)
        return 0

    @staticmethod
    def calculate_relative_movement_modifier(firer_arc: str, target_arc: str, 
                                             f_speed: float, t_speed: float, 
                                             heading_diff_deg: float) -> int:
        """
        Resolves the speed-based relative modifier matrix based on mutual arcs.
        Also evaluates the 'moving towards each other' side arc edge case.
        """
        if f_speed == 0 and t_speed == 0:
            return 2 # (+1 target stationary, +1 firer stationary)
            
        speed_mod = 0
        if 30 <= t_speed <= 37.5: speed_mod = -1
        elif 40 <= t_speed <= 47.5: speed_mod = -2
        elif 50 <= t_speed <= 57.5: speed_mod = -3
        elif 60 <= t_speed <= 67.5: speed_mod = -4
        elif 70 <= t_speed <= 77.5: speed_mod = -5
        elif t_speed >= 80.0: speed_mod = -6

        # Firer is in Target's Front Arc
        if target_arc == "Front":
            if firer_arc == "Front": return int(- (t_speed / 2))
            if firer_arc == "Back":  return int(- (abs(t_speed - f_speed) / 2))
            if firer_arc == "Side":  return int(- (t_speed / 2))

        # Firer is in Target's Back Arc
        elif target_arc == "Back":
            if firer_arc == "Front": return int(- (abs(t_speed - f_speed) / 2))
            if firer_arc == "Back":  return int(- (t_speed / 2))
            if firer_arc == "Side":  return int(- (t_speed / 2))

        # Firer is in Target's Side Arc
        elif target_arc == "Side":
            if 135 <= heading_diff_deg <= 225:
                return int(- t_speed) # Moving directly towards each other
            return int(- abs(t_speed - f_speed))

        return speed_mod

    @classmethod
    def evaluate_attack_modifiers(cls, attacker: dict, defender: dict, 
                                  weapon: dict, specific_target: str = "Chassis",
                                  distance: float = 2.0, visibility: str = "Clear",
                                  sustained_count: int = 0) -> int:
        """Sums up the total targeting modifiers for the combat sequence."""
        total = 0
        
        # Base Gunner Skill
        total += int(attacker.get('gunner_skill_level', 0))
        total += cls.calculate_range_modifier(distance)
        
        # Computers
        comp = attacker.get('computer_type', 'None')
        if comp == 'Standard': total += 1
        elif comp == 'Hi-Res': total += 2
        elif comp == 'Cyberlink': total += 3
        
        # Chassis Target Size Profiles
        v_size = defender.get('vehicle_size_class', 'Car')
        if v_size in ['Compact', 'Subcompact']: total -= 1
        elif v_size == 'Motorcycle': total -= 2
        
        # Target facings for standard cars
        if v_size == 'Car' and specific_target == "Chassis":
            # Passively tracks -1 from front/back face targeting implicitly handled by arcs later
            pass

        # Specific Targets
        if specific_target == "Tire": total -= 3
        elif specific_target == "Turret": total -= 2
        elif specific_target == "Pedestrian": total -= 3
        elif specific_target == "Ground": total += 4
        
        # Visibility Layers
        if visibility == "Rain": total -= 2
        elif visibility in ["Heavy Rain", "Fog", "Night"]: total -= 3
        
        # Unstable Turn Maneuver Penalties (from the current turn phase)
        mode = attacker.get('active_driving_mode', 'STABLE')
        if mode in ['SKID_TRIVIAL', 'FISHTAIL_MINOR']: total -= 3
        elif mode in ['SKID_MINOR', 'SKID_MODERATE', 'FISHTAIL_MAJOR']: total -= 6
        
        if attacker.get('performed_maneuver_this_phase', False):
            total -= int(attacker.get('last_maneuver_difficulty', 0))
            
        # Sustained Firing Loops
        if sustained_count == 1: total += 1
        elif sustained_count >= 2: total += 2
            
        return total
