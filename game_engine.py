import os
import ast
import math
import re
from datetime import datetime
import inflect
from num2words import num2words


GAME_FOLDER = './games'
TC_BONUS_BY_TYPE = {
    "Targeting Computer": 1,
    "Hi-Res Computer": 2,
    "Single-Weapon Computer": 1,
    "Hi-Res SWC (HRSWC)": 2,
    "Cyberlink": 3,
}
POSITION_WIDE_TC_TYPES = {"Targeting Computer", "Hi-Res Computer"}
SINGLE_WEAPON_TC_TYPES = {"Single-Weapon Computer", "Hi-Res SWC (HRSWC)", "Cyberlink"}

class GameEngine:

    @staticmethod
    def _translate_row_id_to_position_id(row_id_based_id: str) -> str:
        """
        Converts a weapon reference saved using the Designer's row_id
        scheme ("weapon-{row_id}-{unit}", row_id 1-based) into the
        0-based array-position scheme get_weapon_facing_and_name /
        get_available_firing_actions actually use
        ("weapon-{idx}-{unit}"). See the patch header for the full
        explanation and the assumption this relies on.
        """
        parts = row_id_based_id.split("-")
        if len(parts) != 3 or parts[0] != "weapon":
            return row_id_based_id  # not a weapon reference -- leave untouched
        row_id = GameEngine.to_int(parts[1], default=-1)
        if row_id is None or row_id < 1:
            return row_id_based_id
        return f"weapon-{row_id - 1}-{parts[2]}"

    @staticmethod
    def _resolve_tc_crew_id(tc_crew_label: str):
        """
        Parses a Targeting Computer's stored 'Crew #<row_id>: <Title>'
        assignment label back into the crew_id scheme (crew_0, crew_1,
        ...) used elsewhere on the server.
 
        ASSUMPTION (flagged): the Designer's crew_row_id is assumed to
        equal (array position + 1) in the saved self.crew_title_{i}
        sequence -- same class of fragility as the weapon row_id issue
        above, and for the same underlying reason (the save format
        doesn't preserve historical row_ids, only current values).
        """
        if not tc_crew_label:
            return None
        match = re.match(r"Crew #(\d+):", tc_crew_label.strip())
        if not match:
            return None
        row_id = int(match.group(1))
        return f"crew_{row_id - 1}"
 
    @staticmethod
    def _resolve_tc_weapon_id(car_record: dict, tc_weapon_label: str):
        """
        Parses a Targeting Computer's stored weapon/link assignment
        (saved as display label text) back into a weapon_id/link_id by
        matching against the car's CURRENT set of available firing
        actions. Returns None if unassigned or if the label no longer
        matches anything (e.g. the assigned weapon was since deleted).
        """
        if not tc_weapon_label or tc_weapon_label == "(none)":
            return None
        all_actions = GameEngine.get_available_firing_actions(car_record) + GameEngine.get_link_actions(car_record)
        match = next((a for a in all_actions if a["label"] == tc_weapon_label), None)
        return match["id"] if match else None
 
    @staticmethod
    def get_targeting_computer_bonus(car_record: dict, crew_id: str, weapon_id: str) -> int:
        """
        Total to-hit bonus from every installed Targeting-Computer-family
        device that applies to this specific (crew_id, weapon_id) firing
        action.
 
        Rules (confirmed):
          - Targeting Computer / Hi-Res Computer: scoped to ONE crew
            position, applies to EVERY weapon/link that position fires --
            including smart links. Weapon assignment is not checked for
            these two types.
          - Single-Weapon Computer / Hi-Res SWC / Cyberlink: scoped to ONE
            crew position AND ONE specific weapon system. Does NOT
            function if that weapon system is a smart link.
 
        If multiple installed devices match, the HIGHEST single bonus
        applies (not summed) -- consistent with the equipment-tier
        convention used elsewhere in this project.
        """
        best_bonus = 0
        tc_index = 0
        while f"self.tc_type_{tc_index}" in car_record:
            tc_type = car_record.get(f"self.tc_type_{tc_index}", "")
            tc_crew_label = car_record.get(f"self.tc_crew_{tc_index}", "")
            tc_weapon_label = car_record.get(f"self.tc_weapon_{tc_index}", "")
 
            assigned_crew_id = GameEngine._resolve_tc_crew_id(tc_crew_label)
            if assigned_crew_id != crew_id:
                tc_index += 1
                continue
 
            bonus = TC_BONUS_BY_TYPE.get(tc_type, 0)
            if bonus == 0:
                tc_index += 1
                continue
 
            if tc_type in POSITION_WIDE_TC_TYPES:
                best_bonus = max(best_bonus, bonus)
 
            elif tc_type in SINGLE_WEAPON_TC_TYPES:
                assigned_weapon_id = GameEngine._resolve_tc_weapon_id(car_record, tc_weapon_label)
                if assigned_weapon_id is None or assigned_weapon_id != weapon_id:
                    tc_index += 1
                    continue
 
                if assigned_weapon_id.startswith("link-"):
                    link = next(
                        (l for l in GameEngine.get_link_actions(car_record) if l["id"] == assigned_weapon_id),
                        None
                    )
                    if link and GameEngine.link_is_smart_link(car_record, link["members"]):
                        tc_index += 1
                        continue
 
                best_bonus = max(best_bonus, bonus)
 
            tc_index += 1
 
        return best_bonus    
    
    @staticmethod
    def to_int(val, default: int = 0) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def _describe_weapon_or_accessory_id(car_record: dict, action_id: str) -> str:
        """Given a stable weapon-<row_id>-<unit> or accessory-<row_id> id, returns
        a short human-readable name by looking up the corresponding row in car_record."""
        # PATCH (bug fix): get_available_firing_actions() generates these
        # IDs directly from its own 0-based loop index (idx starts at 0,
        # so the first weapon's id is "weapon-0-1") -- there was never a
        # "- 1" conversion on the writing side, so there shouldn't be one
        # here either. The old code computed idx = row_id - 1, which for
        # "weapon-0-1" produced idx = -1 and silently returned "" instead
        # of the real weapon name.
        parts = action_id.split("-")
        if parts[0] == "weapon" and len(parts) == 3:
            idx = GameEngine.to_int(parts[1], default=0)
            return car_record.get(f"self.selected_sub_weapon_{idx}_canvas", "")
        elif parts[0] == "accessory" and len(parts) == 2:
            idx = GameEngine.to_int(parts[1], default=0)
            return car_record.get(f"self.selected_accessory_{idx}", "")
        return ""
    
    @staticmethod
    def get_link_actions(car_record: dict) -> list:
        """
        Parses self.link_selections_N (and, when present, self.link_labels_N)
        into fireable "link" actions — pre-linked groups of weapons/accessories
        that fire together as a single firing action, consuming all member
        weapons at once.
        """
        links = []
        idx = 0
        while f"self.link_selections_{idx}" in car_record:
            raw_val = car_record.get(f"self.link_selections_{idx}", "")
            member_ids = raw_val.split("||") if raw_val else []
    
            raw_labels = car_record.get(f"self.link_labels_{idx}", "")
            member_labels = raw_labels.split("||") if raw_labels else []
    
            if len(member_ids) >= 2:
                if not member_labels or len(member_labels) != len(member_ids):
                    # Older design file without saved labels — fall back to lookup
                    member_labels = [
                        GameEngine._describe_weapon_or_accessory_id(car_record, mid)
                        for mid in member_ids
                    ]
                    member_labels = [lbl for lbl in member_labels if lbl]
    
                if member_labels:
                    # PATCH: category for a link is derived from its first
                    # member -- links join weapons that are meant to be
                    # identical (or at least the same general type), so this
                    # is reliable in practice even though it doesn't
                    # explicitly check every member.
                    first_category = ""
                    if member_ids:
                        first_parts = member_ids[0].split("-")
                        if len(first_parts) == 3 and first_parts[0] == "weapon":
                            first_idx = GameEngine.to_int(first_parts[1], default=-1)
                            if first_idx >= 0:
                                first_category = car_record.get(f"self.selected_weapon_alt_{first_idx}", "")
 
                    links.append({
                        "id": f"link-{idx}",
                        "label": "Linked: " + " + ".join(member_labels),
                        "type": "link",
                        "members": member_ids,
                        "category": first_category
                    })
            idx += 1
        return links  
    
    @staticmethod
    def read_game_file(filepath: str) -> list:
        """Reads a game file where each line is either a bare dict literal,
        or (for design-snapshot files copied from the design tool) a single
        line containing a list of dicts."""
        result = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        entry = ast.literal_eval(line)
                        if isinstance(entry, dict):
                            result.append(entry)
                        elif isinstance(entry, list):
                            # Design-tool snapshot format: a list of dicts on one line
                            result.extend(item for item in entry if isinstance(item, dict))
                    except Exception as e:
                        print(f'Skipping unparseable line: {e}')
        except Exception as e:
            print(f'Error reading file: {e}')
        return result

    @staticmethod
    def write_game_file(filepath: str, data: list) -> bool:
        """Writes a list of dicts back to a game file, one dict per line."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for entry in data:
                    f.write(str(entry) + '\n')
            return True
        except Exception as e:
            print(f'Error writing file: {e}')
            return False

    @classmethod
    def confirm_player_movement2(cls, game_id, username):
        """
        Promotes EXACTLY ONE segment length from ProposedCarPosition to CarPosition per click.
        Deductions scale down sequentially, keeping multi-step turns alternating smoothly.
        """
        import os
        try:
            game_files = [f for f in os.listdir(GAME_FOLDER) if f.startswith(game_id) and f.endswith('.txt')]
            if not game_files: 
                return False, "No active game files found."
            game_files.sort()
            filepath = os.path.join(GAME_FOLDER, game_files[-1])
            game_records = cls.read_game_file(filepath)
            
            # 1. Locate the exact ghost node representing our CURRENT active step segment
            proposed_car = None
            for record in game_records:
                norm_record = {str(k).replace(' ', ''): v for k, v in record.items()}
                if (norm_record.get('ProposedCarPosition') == 'ProposedCarPosition'
                        and norm_record.get('owner') == username
                        and int(float(norm_record.get('segment_index', 1))) == 1):
                    proposed_car = norm_record
                    break
                    
            if not proposed_car:
                return False, "No active single-segment preview path coordinates found to lock down."
                
            cleaned_records = []
            for record in game_records:
                norm_rec = {str(k).replace(' ', ''): v for k, v in record.items()}
                
                # SEGMENT FILTER FIX: Delete ONLY segment index 1 since it's the only one being promoted!
                if norm_rec.get('ProposedCarPosition') == 'ProposedCarPosition' and norm_rec.get('owner') == username:
                    seg_idx = int(float(norm_rec.get('segment_index', 1)))
                    if seg_idx == 1:
                        continue # Consume and delete this active step layer
                    else:
                        # Demote subsequent pending ghost segment indexes down by 1 so they hit index 1 on your next choice!
                        record['segment_index'] = seg_idx - 1
                        cleaned_records.append(record)
                        continue
                        
                # Update your permanent vehicle position using ONLY the current segment data
                if norm_rec.get('CarPosition') == 'CarPosition' and norm_rec.get('owner') == username:
                    record['local_starting_x_qty'] = float(proposed_car['local_starting_x_qty'])
                    record['local_starting_y_qty'] = float(proposed_car['local_starting_y_qty'])
                    record['heading'] = int(round(float(proposed_car['heading'])))
                    record['orientation'] = int(round(float(proposed_car['orientation'])))
                    record['last_committed_maneuver'] = proposed_car.get('maneuver_preview_type', 'STR')
                    
                    # Update core attributes to match current segment state limits
                    record['remaining'] = float(proposed_car.get('remaining', 0.0))
                    record['full_remaining'] = int(float(proposed_car.get('full_remaining', 0)))
                    record['half_remaining'] = float(proposed_car.get('half_remaining', 0.0))
                    record['maneuvered'] = bool(proposed_car.get('maneuvered', False))
                    
                cleaned_records.append(record)
                
            if cls.write_game_file(filepath, cleaned_records):
                return True, "Current movement segment advanced and structural queues shifted."
                
            return False, "Failed writing updates to disk."
        except Exception as e:
            return False, f"Engine confirmation failure: {str(e)}"
    
    @classmethod
    def confirm_player_movement(cls, game_id, username):
        """
        Promotes EXACTLY ONE segment length from ProposedCarPosition to CarPosition per click.
        Deductions scale down sequentially, keeping multi-step turns alternating smoothly.
        """
        try:
            game_dir = os.path.join(GAME_FOLDER, game_id)
            if not os.path.isdir(game_dir):
                return False, "Could not identify active game state tracking directory"
    
            game_files = [
                f for f in os.listdir(game_dir)
                if re.match(r'^T\d+P', f) and f.endswith('.txt')
            ]
            game_files.sort()
    
            if not game_files:
                return False, "No active game files found."
    
            filepath = os.path.join(game_dir, game_files[-1])
            game_records = cls.read_game_file(filepath)
    
            # 1. Locate the exact ghost node representing our CURRENT active step segment
            proposed_car = None
            for record in game_records:
                norm_record = {str(k).replace(' ', ''): v for k, v in record.items()}
                if (norm_record.get('ProposedCarPosition') == 'ProposedCarPosition'
                        and norm_record.get('owner') == username
                        and int(float(norm_record.get('segment_index', 1))) == 1):
                    proposed_car = norm_record
                    break
    
            if not proposed_car:
                return False, "No active single-segment preview path coordinates found to lock down."
    
            cleaned_records = []
            for record in game_records:
                norm_rec = {str(k).replace(' ', ''): v for k, v in record.items()}
    
                # SEGMENT FILTER FIX: Delete ONLY segment index 1 since it's the only one being promoted!
                if norm_rec.get('ProposedCarPosition') == 'ProposedCarPosition' and norm_rec.get('owner') == username:
                    seg_idx = int(float(norm_rec.get('segment_index', 1)))
                    if seg_idx == 1:
                        continue  # Consume and delete this active step layer
                    else:
                        # Demote subsequent pending ghost segment indexes down by 1 so they hit index 1 on your next choice!
                        record['segment_index'] = seg_idx - 1
                        cleaned_records.append(record)
                        continue
    
                # Update your permanent vehicle position using ONLY the current segment data
                if norm_rec.get('CarPosition') == 'CarPosition' and norm_rec.get('owner') == username:
                    record['local_starting_x_qty'] = float(proposed_car['local_starting_x_qty'])
                    record['local_starting_y_qty'] = float(proposed_car['local_starting_y_qty'])
                    record['heading'] = int(round(float(proposed_car['heading'])))
                    record['orientation'] = int(round(float(proposed_car['orientation'])))
                    record['last_committed_maneuver'] = proposed_car.get('maneuver_preview_type', 'STR')
    
                    # Update core attributes to match current segment state limits
                    record['remaining'] = float(proposed_car.get('remaining', 0.0))
                    record['full_remaining'] = int(float(proposed_car.get('full_remaining', 0)))
                    record['half_remaining'] = float(proposed_car.get('half_remaining', 0.0))
                    record['maneuvered'] = bool(proposed_car.get('maneuvered', False))
    
                cleaned_records.append(record)
    
            if cls.write_game_file(filepath, cleaned_records):
                return True, "Current movement segment advanced and structural queues shifted."
    
            return False, "Failed writing updates to disk."
        except Exception as e:
            return False, f"Engine confirmation failure: {str(e)}"
        
    @staticmethod
    def process_player_movement2(game_id: str, username: str, maneuver: str) -> tuple[bool, str]:
        """
        Generates a multi-step phase projection path. Checks the vehicle's speed 
        to determine the required car lengths, chains calculations together sequentially, 
        and enforces rule restrictions safely with explicit data typing constraints.
        """
        # 1. IDENTIFY AND LOAD THE ACTIVE PHASE FILE
        all_files = os.listdir(GAME_FOLDER)
        game_files = sorted([f for f in all_files if f.startswith(game_id) and f.endswith('.txt')])
            
        if not game_files:
            return False, "Could not identify active game state tracking file"
                
        filepath = os.path.join(GAME_FOLDER, game_files[-1])
        file_data = GameEngine.read_game_file(filepath)
            
        if not file_data:
            return False, "Active game state file is empty or corrupted"
                
        # 2. LOCATE TARGET ACTIVE VEHICLE AND MOVEMENT QUEUE METADATA
        base_car = next(
            (record for record in file_data
            if str(record.get('CarPosition', '')).replace(' ', '') == 'CarPosition' and record.get('owner') == username),
            None
        )
            
        if not base_car:
            return False, f"No active CarPosition record found for player: {username}"
                
        movement_queue = next(
            (record for record in file_data if str(record.get('MovementQueue', '')).replace(' ', '') == 'MovementQueue'), 
            {}
        )
        current_phase = int(movement_queue.get('phase', 1))
        current_speed = int(base_car.get('current_speed', 0))
            
        # 3. EVALUATE TOTAL REQUIRED LENGTHS SECURELY
        from game_tables import get_phase_movement
        try:
            total_lengths = int(get_phase_movement(current_speed, current_phase))
        except Exception:
            total_lengths = 0
                
        maneuver = maneuver.upper().strip()
            
        # 4. INITIALIZE THE PLAN ARRAY EXPLICITLY
        maneuver_plan = []
        if maneuver == 'STR' or maneuver == '':
            maneuver_plan = ['STR'] * total_lengths
        else:
            maneuver_plan.append(maneuver)
            if total_lengths > 1:
                maneuver_plan.extend(['STR'] * (total_lengths - 1))
                    
        # 5. RUN CHRONOLOGICAL SEGMENT LOOP RUNS
        current_x = float(base_car.get('local_starting_x_qty', 0.0))
        current_y = float(base_car.get('local_starting_y_qty', 0.0))
        current_angle = float(base_car.get('orientation', 0.0))
            
        player_num_clean = int(float(base_car.get('player_number', 1)))
        car_color_clean = str(base_car.get('color', 'blue'))
        car_image_name = str(base_car.get('car_image_name', 'blue_car'))
            
        CAR_LENGTH = 1.0
        CAR_WIDTH = 0.5
        projected_ghosts = []
            
        for idx, step_maneuver in enumerate(maneuver_plan):
            try:
                # --- CASE A: SEGMENT TRAJECTORY IS STRAIGHT ---
                if step_maneuver == 'STR':
                    rad_current = math.radians(current_angle)
                    final_x = current_x + (math.sin(rad_current) * CAR_LENGTH)
                    final_y = current_y + (-math.cos(rad_current) * CAR_LENGTH)
                    final_angle = current_angle
                        
                # --- CASE B: SEGMENT TRAJECTORY IS A COMPOUND MIDPOINT BEND ---
                elif step_maneuver.startswith('D') and len(step_maneuver) >= 3 and step_maneuver[-1] in ['L', 'R']:
                    severity = int(step_maneuver[1:-1])
                    direction = step_maneuver[-1]
                    delta_degrees = severity * 15
                        
                    rad_start = math.radians(current_angle)
                    mid_x = current_x + (math.sin(rad_start) * (CAR_LENGTH / 2.0))
                    mid_y = current_y + (-math.cos(rad_start) * (CAR_LENGTH / 2.0))
                    r_x = math.cos(rad_start)
                    r_y = math.sin(rad_start)
                        
                    if direction == 'L':
                        pivot_x = mid_x - (r_x * (CAR_WIDTH / 2.0))
                        pivot_y = mid_y - (r_y * (CAR_WIDTH / 2.0))
                        rotation_angle = -delta_degrees
                        final_angle = (current_angle - delta_degrees) % 360
                    else:
                        pivot_x = mid_x + (r_x * (CAR_WIDTH / 2.0))
                        pivot_y = mid_y + (r_y * (CAR_WIDTH / 2.0))
                        rotation_angle = delta_degrees
                        final_angle = (current_angle + delta_degrees) % 360
                            
                    # FIX: Safely bind rad_rotation so it can be verified cleanly down the script frame
                    rad_rotation = math.radians(rotation_angle)
                    dx = mid_x - pivot_x
                    dy = mid_y - pivot_y
                    rotated_mid_x = pivot_x + (dx * math.cos(rad_rotation) - dy * math.sin(rad_rotation))
                    rotated_mid_y = pivot_y + (dx * math.sin(rad_rotation) + dy * math.cos(rad_rotation))
                        
                    rad_final = math.radians(final_angle)
                    final_x = rotated_mid_x + (math.sin(rad_final) * (CAR_LENGTH / 2.0))
                    final_y = rotated_mid_y + (-math.cos(rad_final) * (CAR_LENGTH / 2.0))
                else:
                    continue
                        
                final_heading_int = int(round(final_angle)) % 360
                    
                # Deduct lengths sequentially per individual array block slice
                step_cost = 0.5 if step_maneuver == 'half' else 1.0
                total_remaining = float(base_car.get('remaining', 2.0))
                full_remaining = int(base_car.get('full_remaining', 2))
                half_remaining = float(base_car.get('half_remaining', 0.0))
                    
                if step_maneuver == 'half':
                    calc_rem = round(max(0.0, total_remaining - (idx * 0.5)), 1)
                    calc_full = full_remaining
                    calc_half = 0.0
                else:
                    calc_rem = round(max(0.0, total_remaining - (idx * 1.0) - step_cost), 1)
                    calc_full = max(0, full_remaining - idx - 1)
                    calc_half = half_remaining
                    
                ghost_node = {
                    'ProposedCarPosition': 'ProposedCarPosition',
                    'player_number': player_num_clean,
                    'owner': username,
                    'local_starting_x_qty': round(final_x, 2),
                    'local_starting_y_qty': round(final_y, 2),
                    'heading': final_heading_int,
                    'orientation': float(final_heading_int),
                    'color': car_color_clean,
                    'car_image_name': car_image_name,
                    'maneuver_preview_type': step_maneuver,
                    'segment_index': int(idx + 1),
                    'total_segments': int(total_lengths),
                    'remaining': calc_rem,
                    'full_remaining': calc_full,
                    'half_remaining': calc_half,
                    'maneuvered': True if step_maneuver != 'STR' else bool(base_car.get('maneuvered', False)),
                    'timestamp': datetime.now().isoformat()
                }
                projected_ghosts.append(ghost_node)
                    
                # Update tracking constraints for chained calculations
                current_x = final_x
                current_y = final_y
                current_angle = final_angle
                    
            except Exception as loop_err:
                return False, f"Internal engine calculation crash during route handling: {str(loop_err)}"
                    
        # COMMIT PROJECTIONS BACK DOWN TO DISK
        cleaned_file_data = [
            record for record in file_data 
            if not (str(record.get('ProposedCarPosition', '')).replace(' ', '') == 'ProposedCarPosition' and record.get('owner') == username)
        ]
        cleaned_file_data.extend(projected_ghosts)
        GameEngine.write_game_file(filepath, cleaned_file_data)
            
        return True, f"Generated path projection matrix chain containing {total_lengths} steps."
    
    @staticmethod
    def process_player_movement(game_id: str, username: str, maneuver: str) -> tuple[bool, str]:
        """
        Generates a multi-step phase projection path. Checks the vehicle's speed 
        to determine the required car lengths, chains calculations together sequentially, 
        and enforces rule restrictions safely with explicit data typing constraints.
        """
        # 1. IDENTIFY AND LOAD THE ACTIVE PHASE FILE
        game_dir = os.path.join(GAME_FOLDER, game_id)
        if not os.path.isdir(game_dir):
            return False, "Could not identify active game state tracking directory"
    
        game_files = [
            f for f in os.listdir(game_dir)
            if re.match(r'^T\d+P', f) and f.endswith('.txt')
        ]
        game_files.sort()
    
        if not game_files:
            return False, "Could not identify active game state tracking file"
    
        filepath = os.path.join(game_dir, game_files[-1])
        file_data = GameEngine.read_game_file(filepath)
    
        if not file_data:
            return False, "Active game state file is empty or corrupted"
    
        # 2. LOCATE TARGET ACTIVE VEHICLE AND MOVEMENT QUEUE METADATA
        base_car = next(
            (record for record in file_data
             if str(record.get('CarPosition', '')).replace(' ', '') == 'CarPosition' and record.get('owner') == username),
            None
        )
    
        if not base_car:
            return False, f"No active CarPosition record found for player: {username}"
    
        movement_queue = next(
            (record for record in file_data if str(record.get('MovementQueue', '')).replace(' ', '') == 'MovementQueue'), 
            {}
        )
        current_phase = int(movement_queue.get('phase', 1))
        current_speed = int(base_car.get('current_speed', 0))
    
        # 3. EVALUATE TOTAL REQUIRED LENGTHS SECURELY
        from game_tables import get_phase_movement
        try:
            total_lengths = int(get_phase_movement(current_speed, current_phase))
        except Exception:
            total_lengths = 0
    
        maneuver = maneuver.upper().strip()
    
        # 4. INITIALIZE THE PLAN ARRAY EXPLICITLY
        maneuver_plan = []
        if maneuver == 'STR' or maneuver == '':
            maneuver_plan = ['STR'] * total_lengths
        else:
            maneuver_plan.append(maneuver)
            if total_lengths > 1:
                maneuver_plan.extend(['STR'] * (total_lengths - 1))
    
        # 5. RUN CHRONOLOGICAL SEGMENT LOOP RUNS
        current_x = float(base_car.get('local_starting_x_qty', 0.0))
        current_y = float(base_car.get('local_starting_y_qty', 0.0))
        current_angle = float(base_car.get('orientation', 0.0))
    
        player_num_clean = int(float(base_car.get('player_number', 1)))
        car_color_clean = str(base_car.get('color', 'blue'))
        car_image_name = str(base_car.get('car_image_name', 'blue_car'))
    
        CAR_LENGTH = 1.0
        CAR_WIDTH = 0.5
        projected_ghosts = []
    
        for idx, step_maneuver in enumerate(maneuver_plan):
            try:
                # --- CASE A: SEGMENT TRAJECTORY IS STRAIGHT ---
                if step_maneuver == 'STR':
                    rad_current = math.radians(current_angle)
                    final_x = current_x + (math.sin(rad_current) * CAR_LENGTH)
                    final_y = current_y + (-math.cos(rad_current) * CAR_LENGTH)
                    final_angle = current_angle
                elif step_maneuver == 'HALF':
                    rad_current = math.radians(current_angle)
                    final_x = current_x + (math.sin(rad_current) * CAR_LENGTH / 2)
                    final_y = current_y + (-math.cos(rad_current) * CAR_LENGTH / 2)
                    final_angle = current_angle
    
                # --- CASE B: SEGMENT TRAJECTORY IS A COMPOUND MIDPOINT BEND ---
                elif step_maneuver.startswith('D') and len(step_maneuver) >= 3 and step_maneuver[-1] in ['L', 'R']:
                    severity = int(step_maneuver[1:-1])
                    direction = step_maneuver[-1]
                    delta_degrees = severity * 15
    
                    rad_start = math.radians(current_angle)
                    mid_x = current_x + (math.sin(rad_start) * (CAR_LENGTH / 2.0))
                    mid_y = current_y + (-math.cos(rad_start) * (CAR_LENGTH / 2.0))
                    r_x = math.cos(rad_start)
                    r_y = math.sin(rad_start)
    
                    if direction == 'L':
                        pivot_x = mid_x - (r_x * (CAR_WIDTH / 2.0))
                        pivot_y = mid_y - (r_y * (CAR_WIDTH / 2.0))
                        rotation_angle = -delta_degrees
                        final_angle = (current_angle - delta_degrees) % 360
                    else:
                        pivot_x = mid_x + (r_x * (CAR_WIDTH / 2.0))
                        pivot_y = mid_y + (r_y * (CAR_WIDTH / 2.0))
                        rotation_angle = delta_degrees
                        final_angle = (current_angle + delta_degrees) % 360
    
                    # FIX: Safely bind rad_rotation so it can be verified cleanly down the script frame
                    rad_rotation = math.radians(rotation_angle)
                    dx = mid_x - pivot_x
                    dy = mid_y - pivot_y
                    rotated_mid_x = pivot_x + (dx * math.cos(rad_rotation) - dy * math.sin(rad_rotation))
                    rotated_mid_y = pivot_y + (dx * math.sin(rad_rotation) + dy * math.cos(rad_rotation))
    
                    rad_final = math.radians(final_angle)
                    final_x = rotated_mid_x + (math.sin(rad_final) * (CAR_LENGTH / 2.0))
                    final_y = rotated_mid_y + (-math.cos(rad_final) * (CAR_LENGTH / 2.0))
                else:
                    continue
    
                final_heading_int = int(round(final_angle)) % 360
    
                # Deduct lengths sequentially per individual array block slice
                step_cost = 0.5 if step_maneuver == 'half' else 1.0
                total_remaining = float(base_car.get('remaining', 2.0))
                full_remaining = int(base_car.get('full_remaining', 2))
                half_remaining = float(base_car.get('half_remaining', 0.0))
    
                if step_maneuver == 'half':
                    calc_rem = round(max(0.0, total_remaining - (idx * 0.5)), 1)
                    calc_full = full_remaining
                    calc_half = 0.0
                else:
                    calc_rem = round(max(0.0, total_remaining - (idx * 1.0) - step_cost), 1)
                    calc_full = max(0, full_remaining - idx - 1)
                    calc_half = half_remaining
    
                ghost_node = {
                    'ProposedCarPosition': 'ProposedCarPosition',
                    'player_number': player_num_clean,
                    'owner': username,
                    'local_starting_x_qty': round(final_x, 2),
                    'local_starting_y_qty': round(final_y, 2),
                    'heading': final_heading_int,
                    'orientation': float(final_heading_int),
                    'color': car_color_clean,
                    'car_image_name': car_image_name,
                    'maneuver_preview_type': step_maneuver,
                    'segment_index': int(idx + 1),
                    'total_segments': int(total_lengths),
                    'remaining': calc_rem,
                    'full_remaining': calc_full,
                    'half_remaining': calc_half,
                    'maneuvered': True if step_maneuver not in ['STR', "HALF"] else bool(base_car.get('maneuvered', False)),
                    'timestamp': datetime.now().isoformat()
                }
                projected_ghosts.append(ghost_node)
    
                # Update tracking constraints for chained calculations
                current_x = final_x
                current_y = final_y
                current_angle = final_angle
    
            except Exception as loop_err:
                return False, f"Internal engine calculation crash during route handling: {str(loop_err)}"
    
        # COMMIT PROJECTIONS BACK DOWN TO DISK
        cleaned_file_data = [
            record for record in file_data 
            if not (str(record.get('ProposedCarPosition', '')).replace(' ', '') == 'ProposedCarPosition' and record.get('owner') == username)
        ]
        cleaned_file_data.extend(projected_ghosts)
        GameEngine.write_game_file(filepath, cleaned_file_data)
    
        return True, f"Generated path projection matrix chain containing {total_lengths} steps."
    
    @staticmethod
    def extract_pixel_vertices(map_entry, car_length=1.0, car_width=0.5):
        """ Normalizes all game engine map dictionaries into unified pixel-scale vertex arrays. """
        import math
        if 'Polygon' in map_entry:
            return list(map_entry.get('list_of_tuples', []))
            
        elif 'Rect' in map_entry:
            sx = float(map_entry.get('local_starting_x_qty', 0.0)) * 40.0
            sy = float(map_entry.get('local_starting_y_qty', 0.0)) * 40.0
            w = float(map_entry.get('local_x_qty', 0.0)) * 40.0
            h = float(map_entry.get('local_y_qty', 0.0)) * 40.0
            return [(sx, sy), (sx + w, sy), (sx + w, sy + h), (sx, sy + h)]
            
        elif any(k in map_entry for k in ['CarPosition', 'ProposedCarPosition']):
            cx = float(map_entry.get('local_starting_x_qty', 0.0)) * 40.0
            cy = float(map_entry.get('local_starting_y_qty', 0.0)) * 40.0
            angle_rad = math.radians(float(map_entry.get('orientation', 0.0)))
            
            half_l = (car_length * 40.0) / 2.0
            half_w = (car_width * 40.0) / 2.0
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            
            offsets = [(half_l, half_w), (half_l, -half_w), (-half_l, -half_w), (-half_l, half_w)]
            return [(cx + (dx * sin_a + dy * cos_a), cy + (-dx * cos_a + dy * sin_a)) for dx, dy in offsets]
            
        return []

    @staticmethod
    def get_crew_titles(driver_gunner_qty: int) -> list[str]:
        """
        Builds crew member titles from the car's driver_gunner_qty.
        qty 1 -> ["Driver"]
        qty 2 -> ["Driver", "Gunner"]
        qty 3+ -> ["Driver", "First Gunner", "Second Gunner", "Third Gunner", ...]
        """
        if driver_gunner_qty <= 0:
            return []
    
        titles = ["Driver"]
        gunner_count = driver_gunner_qty - 1
    
        if gunner_count == 1:
            titles.append("Gunner")
        elif gunner_count > 1:
            p = inflect.engine()

            for i in range(1, gunner_count + 1):
                # --- Example 1: inflect ---
                word_lower = p.number_to_words(p.ordinal(num=i))
                label  = word_lower.capitalize()
                #label = ordinals[i] if i < len(ordinals) else f"{i + 1}th"
                titles.append(f"{label} Gunner")
    
        return titles
    
    @staticmethod
    def get_available_firing_actions(car_record: dict) -> list[dict]:
        """
        Scans a car's design snapshot for weapons and accessories that represent
        a usable firing action. Returns a list of dicts, each describing one
        linkable/fireable unit:
            {"id": <stable string>, "label": <display text>, "type": "weapon"|"accessory"}
    
        Mirrors the same qty-explosion logic used by the design tool's
        scan_available_firing_actions(), but reads from the flat car-snapshot
        dict format (0-indexed self.* keys) rather than live Tkinter widgets.
        """
        actions = []
    
        linkable_accessory_names = [
            "Fire Extinguisher", "Improved Fire Extinguisher",
            "High Torque Motors (HTM)", "HTMs, Heavy Duty (HDHTM)",
            "Overdrive", "Nitrous Oxide"
        ]
    
        # --- Weapons: explode by qty, one linkable action per physical unit ---
        idx = 0
        while f"self.selected_sub_weapon_{idx}_canvas" in car_record:
            name = car_record.get(f"self.selected_sub_weapon_{idx}_canvas", "")
            if not name or name in ["Weapon", "None", "Select Weapon", "No items available"]:
                idx += 1
                continue
 
            facing = car_record.get(f"self.weapon_armor_facing_{idx}", "Facing")
            qty = GameEngine.to_int(car_record.get(f"self.var_sub_weapon_{idx}_qty", 0), default=0)
            # PATCH: expose the weapon's category (e.g. "DISCHARGERS") so
            # the client can skip to-hit calculation for weapon types that
            # don't have a meaningful aimed shot.
            category = car_record.get(f"self.selected_weapon_alt_{idx}", "")
 
            for unit_num in range(1, qty + 1):
                action_id = f"weapon-{idx}-{unit_num}"
                if qty > 1:
                    label = f"Weapon: {name} ({unit_num} of {qty}) ({facing})"
                else:
                    label = f"Weapon: {name} ({facing})"
                actions.append({"id": action_id, "label": label, "type": "weapon", "category": category})
 
            idx += 1
    
        # --- Accessories: always exactly one action per row, no qty explosion ---
        idx = 0
        while f"self.selected_accessory_{idx}" in car_record:
            name = car_record.get(f"self.selected_accessory_{idx}", "")
            if name in linkable_accessory_names:
                action_id = f"accessory-{idx}"
                label = f"Accessory: {name}"
                actions.append({"id": action_id, "label": label, "type": "accessory"})
            idx += 1
    
        return actions
    
    @staticmethod
    def reset_turn_actions(car_record: dict) -> dict:
        """
        Clears both per-turn 'used' trackers on a car record, making every
        crew member and every weapon/accessory available again for the new turn.
        Returns the same dict, mutated in place, for convenience.
        """
        car_record['firing_actions_used_this_turn'] = []
        car_record['weapons_used_this_turn'] = []
        return car_record
    
    @staticmethod
    def get_player_snapshot_files(game_id: str) -> list:
        """
        Returns full paths to every player design snapshot file
        (player_<N>_<design>.txt) inside a game's directory.
        """
        # PATCH (bug fix): was GameEngine.GAME_FOLDER -- GAME_FOLDER is a
        # module-level global, not a class attribute, so that raised
        # AttributeError on every call. Use the bare global directly, the
        # same way every other method in this class already does.
        game_dir = os.path.join(GAME_FOLDER, game_id)
        if not os.path.isdir(game_dir):
            return []
    
        return [
            os.path.join(game_dir, f)
            for f in os.listdir(game_dir)
            if re.match(r'^player_\d+_', f) and f.endswith('.txt')
        ]

    @classmethod
    def reset_all_players_turn_actions(cls, game_id: str) -> None:
        """
        Iterates every player snapshot file in the game's directory and
        resets their per-turn firing-action tracking, writing each file back.
        Intended to be called once per Turn, during End-Of-Turn processing.
        """
        for snapshot_path in cls.get_player_snapshot_files(game_id):
            car_records = cls.read_game_file(snapshot_path)
            if not car_records or not isinstance(car_records[0], dict):
                continue
    
            car_records[0] = cls.reset_turn_actions(car_records[0])
            cls.write_game_file(snapshot_path, car_records)

    @staticmethod
    def get_weapon_facing_and_name(car_record: dict, weapon_id: str):
        """
        Resolves a canonical weapon/link id ("weapon-<idx>-<unit>" or
        "link-<idx>") to (name, facing) by reading the design snapshot.
        For a link, uses its first member weapon's facing -- linked
        weapons should all share one fire arc by design, since they fire
        as a single action. Returns (None, None) if weapon_id doesn't
        resolve to anything on this car.
        """
        parts = weapon_id.split("-")
 
        if parts[0] == "weapon" and len(parts) == 3:
            idx = GameEngine.to_int(parts[1], default=-1)
            if idx < 0:
                return None, None
            name = car_record.get(f"self.selected_sub_weapon_{idx}_canvas", "")
            if not name:
                return None, None
            facing = car_record.get(f"self.weapon_armor_facing_{idx}", "Front")
            return name, facing
 
        if parts[0] == "link":
            links = GameEngine.get_link_actions(car_record)
            link = next((l for l in links if l["id"] == weapon_id), None)
            if not link or not link.get("members"):
                return None, None
 
            member_facings = []
            for member_id in link["members"]:
                # FIX: link members are saved using row_id, not array
                # position -- translate before resolving. See
                # _translate_row_id_to_position_id's docstring.
                translated_id = GameEngine._translate_row_id_to_position_id(member_id)
                _, member_facing = GameEngine.get_weapon_facing_and_name(car_record, translated_id)
                if member_facing is not None:
                    member_facings.append(member_facing)
 
            if not member_facings:
                return None, None
 
            # If ANY member is Top (turret), the whole link can track the
            # target the same way a lone turret weapon can -- prefer that
            # over just using whichever member happens to be listed first.
            effective_facing = "Top" if "Top" in member_facings else member_facings[0]
            return link["label"], effective_facing
 
        return None, None

    @staticmethod
    def get_crew_roster(car_record: dict) -> list:
        """
        Reads the crew roster directly from the design snapshot's
        per-row crew fields (self.crew_title_{i}, self.crew_skill_driver_{i},
        self.crew_skill_gunner_{i}, self.crew_skill_handgunner_{i}) --
        the format the crew-rows feature actually writes, replacing the
        old single-count self.var_driver_gunner_qty approach
        get_crew_titles() used to synthesize generic titles from.
 
        Returns a list of dicts, each:
            {"id": "crew_<i>", "title": ..., "skill_driver": int,
             "skill_gunner": int, "skill_handgunner": int}
 
        "id" (not title) is the stable identifier to use everywhere a
        crew member needs to be referenced or looked up by -- see the
        design note above.
        """
        roster = []
        i = 0
        while f"self.crew_title_{i}" in car_record:
            roster.append({
                "id": f"crew_{i}",
                "title": car_record.get(f"self.crew_title_{i}", ""),
                "skill_driver": GameEngine.to_int(car_record.get(f"self.crew_skill_driver_{i}", 0), default=0),
                "skill_gunner": GameEngine.to_int(car_record.get(f"self.crew_skill_gunner_{i}", 0), default=0),
                "skill_handgunner": GameEngine.to_int(car_record.get(f"self.crew_skill_handgunner_{i}", 0), default=0),
            })
            i += 1
        return roster

    @staticmethod
    def link_is_smart_link(car_record: dict, member_action_ids: list) -> bool:
        """
        Server-side equivalent of the Designer's
        link_qualifies_for_smart_link(): True if every member of the
        link is the identical weapon (ammo type ignored) and there's at
        most one distinct FIXED (non-Top) facing among them.
        """
        resolved = []
        for aid in member_action_ids:
            translated_id = GameEngine._translate_row_id_to_position_id(aid)
            name, facing = GameEngine.get_weapon_facing_and_name(car_record, translated_id)
            if name is None:
                resolved.append((None, None))
                continue
            base_name = name.split(" - ")[0].strip()  # "ammo type doesn't matter"
            resolved.append((base_name, facing))
 
        if any(name is None for name, facing in resolved):
            return False
        names = {name for name, facing in resolved}
        if len(names) != 1:
            return False
        facings = {facing for name, facing in resolved}
        if len(facings) <= 1:
            return False
        fixed_facings = facings - {"Top"}
        return len(fixed_facings) <= 1
