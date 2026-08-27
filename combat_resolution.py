import random
import math
from combat_geometry import CombatGeometryEngine
from combat_modifiers import CombatModifiersEngine
from combat_physics import roll_car_wars_dice, CombatPhysicsEngine
from fire_and_explosions import FireAndExplosionEngine

def execute_tactical_firing_loop(attacker: dict, defender: dict, weapon: dict, 
                                 map_obstacles: list, target_sub_item: str = "Chassis") -> dict:
    """
    Executes a full turn combat action step: checks fire arc limits, verifies LOS,
    calculates targeting modifiers, rolls 2D6 to-hit, and applies damage.
    """
    ax, ay = float(attacker['local_starting_x_qty']), float(attacker['local_starting_y_qty'])
    dx, dy = float(defender['local_starting_x_qty']), float(defender['local_starting_y_qty'])
    
    distance = math.hypot(dx - ax, dy - ay)
    
    # 1. Pinpoint Weapon Mount Origin
    w_facing = weapon.get('facing', 'Front')
    w_x, w_y = CombatGeometryEngine.get_weapon_origin(ax, ay, float(attacker['orientation']), w_facing)
    
    # 2. Enforce Fire Arc Boundaries
    target_arc = CombatGeometryEngine.determine_relative_arc(w_x, w_y, float(attacker['orientation']), dx, dy)
    if w_facing != "Top" and w_facing != target_arc:
        return {"hit": False, "msg": f"Target falls inside your {target_arc} arc, out of bounds for weapon facing {w_facing}."}
        
    # 3. Line-of-Sight Validation
    if CombatGeometryEngine.is_line_of_sight_blocked((w_x, w_y), (dx, dy), map_obstacles):
        return {"hit": False, "msg": "Line of Sight blocked by a solid map barrier."}
        
    # 4. Modifiers and To-Hit Evaluation
    modifiers = CombatModifiersEngine.evaluate_attack_modifiers(attacker, defender, weapon, target_sub_item, distance)
    
    # Base target number to hit is an unmodified 7+ on 2D6
    needed_to_hit = 7 - modifiers
    needed_to_hit = max(2, min(12, needed_to_hit)) 
    
    hit_roll = random.randint(1, 6) + random.randint(1, 6)
    is_successful_hit = hit_roll >= needed_to_hit
    
    if not is_successful_hit:
        return {"hit": False, "roll": hit_roll, "needed": needed_to_hit, 
                "msg": f"Missed shot. Rolled {hit_roll}, needed {needed_to_hit} after modifiers."}
        
    # --- SUCCESSFUL HIT: PROCESS ATTRITION ---
    w_dice_expr = weapon.get('damage_expression', '2d') 
    rolled_damage_points = roll_car_wars_dice(w_dice_expr)
    
    # Identify which panel face absorbs the blow based on target perspective
    impact_panel = CombatGeometryEngine.determine_relative_arc(dx, dy, float(defender['orientation']), ax, ay)
    
    is_linear_cascade = impact_panel in ["Front", "Back"]
    damage_log = CombatPhysicsEngine.apply_damage_cascade(defender, rolled_damage_points, impact_panel, is_linear_cascade)
    
    # --- PROCESS INCENDIARY IGNITION RESISTANCE ROLLS ---
    w_name = weapon.get('name', 'Machine Gun')
    fire_results = FireAndExplosionEngine.test_incendiary_ignition(w_name, defender)
    
    if fire_results.get("ignited"):
        damage_log.append(fire_results["msg"])
        
    return {
        "hit": True, "roll": hit_roll, "needed": needed_to_hit,
        "damage_points": rolled_damage_points, "impact_facing": impact_panel,
        "cascade_history": damage_log, "fire_results": fire_results,
        "msg": f"DIRECT HIT! Rolled {hit_roll} (needed {needed_to_hit}). Inflicted {rolled_damage_points} damage to {impact_panel} panel."
    }
