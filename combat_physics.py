import random
import re
from collision_engine import CollisionEngine
from game_tables import get_speed_control

def roll_car_wars_dice(damage_expression: str) -> int:
    """Parses a standard damage string (e.g., '1d-4', '7d', '12d') and rolls pools."""
    if not damage_expression or damage_expression == "None":
        return 0
    match = re.match(r'^(\d+)d(?:([+-]\d+))?$', damage_expression.strip())
    if not match:
        return 0
    num_dice = int(match.group(1))
    modifier = int(match.group(2)) if match.group(2) else 0
    return max(0, sum(random.randint(1, 6) for _ in range(num_dice)) + modifier)

class CombatPhysicsEngine:
    """Calculates mechanical kinetic force and applies linear/flank internal components cascades."""

    @staticmethod
    def get_damage_modifier_class(weight_lbs: float) -> str:
        if weight_lbs <= 2000: return "DM_TINY"
        if weight_lbs <= 4000: return "DM_LIGHT"
        if weight_lbs <= 8000: return "DM_STANDARD" # 4000 to 8000 lbs (DM1 Default)
        return "DM_HEAVY"

    @classmethod
    def resolve_impact_telemetry(cls, striker: dict, target: dict, impact_type: str) -> dict:
        """Resolves speed formulas, enforcement cuts, and conformation actions."""
        s_speed = float(striker.get('current_speed', 0.0))
        t_speed = float(target.get('current_speed', 0.0))
        s_weight = float(striker.get('weight_lbs', 5000.0))
        t_weight = float(target.get('weight_lbs', 5000.0))
        
        s_dm = cls.get_damage_modifier_class(s_weight)
        
        s_head = int(striker.get('heading', 0)) % 360
        t_head = int(target.get('heading', 0)) % 360
        same_dir = (abs(s_head - t_head) % 360) < 90 or (abs(s_head - t_head) % 360) > 270
        
        resultant_speed = 0.0
        striker_conforms, target_conforms = False, False

        if impact_type == "HEAD_TO_HEAD":
            resultant_speed = s_speed + t_speed
            striker_conforms, target_conforms = True, True
        elif impact_type == "T_BONE":
            resultant_speed = s_speed
            striker_conforms = True
            if s_dm not in ["DM_TINY", "DM_LIGHT"]:
                target_conforms = True
        elif impact_type == "REAR_END":
            resultant_speed = s_speed - t_speed
            striker_conforms = True
        elif impact_type == "SIDESWIPE":
            resultant_speed = abs(s_speed - t_speed) / 4.0 if same_dir else (s_speed + t_speed) / 4.0
            if s_dm == "DM_STANDARD" and cls.get_damage_modifier_class(t_weight) == "DM_STANDARD":
                striker_conforms = True  # Only T-bones cause target to conform at identical DM1

        if resultant_speed <= 0.0:
            return {"active": False, "collision_speed": 0.0}

        return {"active": True, "collision_speed": round(resultant_speed, 1), 
                "s_conforms": striker_conforms, "t_conforms": target_conforms}

    @staticmethod
    def map_armor_and_components(car: dict, facing: str) -> dict:
        """Extracts standard internal objects and structural DP values from layout schemas."""
        mapping = {
            "Front": "self.var_outer_front_armor_allocation_qty",
            "Back": "self.var_outer_back_armor_allocation_qty",
            "Left": "self.var_outer_left_armor_allocation_qty",
            "Right": "self.var_outer_right_armor_allocation_qty"
        }
        armor_key = mapping.get(facing, "self.var_outer_front_armor_allocation_qty")
        
        # Weapons parsing
        w_list = []
        for i in range(1, 11):
            w_name = car.get(f'self.selected_sub_weapon_{i}_canvas', 'None')
            if w_name != 'None' and car.get(f'self.weapon_armor_facing_{i}', 'Facing') == facing:
                w_list.append({"name": w_name, "dp": int(car.get(f'self.var_sub_weapon_{i}_qty', 1)) * 5})

        crew_dp = (int(car.get('self.var_driver_gunner_qty', 1)) + int(car.get('self.var_passenger_qty', 0))) * 3
        return {
            "armor_key": armor_key, "armor_val": int(car.get(armor_key, 0)),
            "weapons": w_list, "engine": {"name": "Engine Block", "dp": int(car.get('engine_dp', 8))},
            "crew_armor": {"name": "Crew Component Armor", "dp": int(car.get('self.var_component_armor_count_qty_1', 0))},
            "crew": {"name": "Crew", "dp": crew_dp},
            "gas_tank": {"name": "Gas Tank", "dp": int(car.get('gas_tank_dp', 0))}
        }

    @classmethod
    def apply_damage_cascade(cls, car: dict, total_damage: int, facing: str, is_linear: bool = True):
        """Processes linear front/rear cascades or round-robin side breaches."""
        comp = cls.map_armor_and_components(car, facing)
        log = []
        
        # Armor absorption check
        if comp["armor_val"] >= total_damage:
            car[comp["armor_key"]] = comp["armor_val"] - total_damage
            return [f"Armor absorbed all damage. {car[comp['armor_key']]} points remaining on {facing}."]
            
        overflow = total_damage - comp["armor_val"]
        car[comp["armor_key"]] = 0
        log.append(f"Armor panel breached on {facing}! {overflow} points heading internal.")

        if is_linear:
            sequence = [comp["weapons"], comp["engine"], comp["crew_armor"], comp["crew"], comp["gas_tank"]]
            if facing == "Back":
                sequence = [comp["gas_tank"], comp["crew"], comp["crew_armor"], comp["engine"], comp["weapons"]]
                
            for target in sequence:
                if overflow <= 0: break
                if isinstance(target, list):
                    for w in target:
                        if overflow <= 0: break
                        absorbed = min(overflow, w["dp"])
                        overflow -= absorbed
                        log.append(f"Internal Weapon {w['name']} takes {absorbed} damage.")
                else:
                    if target["dp"] > 0:
                        absorbed = min(overflow, target["dp"])
                        target["dp"] -= absorbed
                        overflow -= absorbed
                        log.append(f"Internal Component {target['name']} sustained {absorbed} DP shock.")
        else:
            # Round-Robin Side Breach Matrix Allocation
            for w in comp["weapons"]:
                if overflow <= 0: break
                absorbed = min(overflow, w["dp"])
                overflow -= absorbed
                log.append(f"Flank Weapon {w['name']} absorbs {absorbed} damage.")
                
            compartments = [comp["engine"], comp["crew"], comp["gas_tank"]]
            while overflow > 0:
                active = [c for c in compartments if c["dp"] > 0]
                if not active: break
                for c in active:
                    if overflow <= 0: break
                    c["dp"] -= 1
                    overflow -= 1
                    log.append(f"Flank Tick: 1 point applied to internal {c['name']}.")

        if overflow > 0:
            log.append(f"BROKEN BLENDER! {overflow} leftover force points shredded structural limits.")
        return log
