import random

# game_tables.py
# Speed Control Table
# Columns: d1-d5 = number of dice rolled for that control check
#          ram   = ram damage expression (None = no damage)
#
# Source: Car Wars rulebook

SPEED_CONTROL = {
      0: {'p1': 0,   'p2': 0,   'p3': 0,   'p4': 0,   'p5': 0,   'ram': None},
      5: {'p1': 0.5, 'p2': 0,   'p3': 0,   'p4': 0,   'p5': 0,   'ram': '1d-4'},
     10: {'p1': 1,   'p2': 0,   'p3': 0,   'p4': 0,   'p5': 0,   'ram': '1d-2'},
     15: {'p1': 1,   'p2': 0,   'p3': 0.5, 'p4': 0,   'p5': 0,   'ram': '1d-1'},
     20: {'p1': 1,   'p2': 0,   'p3': 1,   'p4': 0,   'p5': 0,   'ram': '1d'},
     25: {'p1': 1,   'p2': 0,   'p3': 1,   'p4': 0,   'p5': 0.5, 'ram': '1d'},
     30: {'p1': 1,   'p2': 0,   'p3': 1,   'p4': 0,   'p5': 1,   'ram': '1d'},
     35: {'p1': 1,   'p2': 0.5, 'p3': 1,   'p4': 0,   'p5': 1,   'ram': '2d'},
     40: {'p1': 1,   'p2': 1,   'p3': 1,   'p4': 0,   'p5': 1,   'ram': '3d'},
     45: {'p1': 1,   'p2': 1,   'p3': 1,   'p4': 0.5, 'p5': 1,   'ram': '4d'},
     50: {'p1': 1,   'p2': 1,   'p3': 1,   'p4': 1,   'p5': 1,   'ram': '5d'},
     55: {'p1': 1.5, 'p2': 1,   'p3': 1,   'p4': 1,   'p5': 1,   'ram': '6d'},
     60: {'p1': 2,   'p2': 1,   'p3': 1,   'p4': 1,   'p5': 1,   'ram': '7d'},
     65: {'p1': 2,   'p2': 1,   'p3': 1.5, 'p4': 1,   'p5': 1,   'ram': '8d'},
     70: {'p1': 2,   'p2': 1,   'p3': 2,   'p4': 1,   'p5': 1,   'ram': '9d'},
     75: {'p1': 2,   'p2': 1,   'p3': 2,   'p4': 1,   'p5': 1.5, 'ram': '10d'},
     80: {'p1': 2,   'p2': 1,   'p3': 2,   'p4': 1,   'p5': 2,   'ram': '11d'},
     85: {'p1': 2,   'p2': 1.5, 'p3': 2,   'p4': 1,   'p5': 2,   'ram': '12d'},
     90: {'p1': 2,   'p2': 2,   'p3': 2,   'p4': 1,   'p5': 2,   'ram': '13d'},
     95: {'p1': 2,   'p2': 2,   'p3': 2,   'p4': 1.5, 'p5': 2,   'ram': '14d'},
    100: {'p1': 2,   'p2': 2,   'p3': 2,   'p4': 2,   'p5': 2,   'ram': '15d'},
    105: {'p1': 2.5, 'p2': 2,   'p3': 2,   'p4': 2,   'p5': 2,   'ram': '16d'},
    110: {'p1': 3,   'p2': 2,   'p3': 2,   'p4': 2,   'p5': 2,   'ram': '17d'},
    115: {'p1': 3,   'p2': 2,   'p3': 2.5, 'p4': 2,   'p5': 2,   'ram': '18d'},
    120: {'p1': 3,   'p2': 2,   'p3': 3,   'p4': 2,   'p5': 2,   'ram': '19d'},
    125: {'p1': 3,   'p2': 2,   'p3': 3,   'p4': 2,   'p5': 2.5, 'ram': '20d'},
    130: {'p1': 3,   'p2': 2,   'p3': 3,   'p4': 2,   'p5': 3,   'ram': '21d'},
    135: {'p1': 3,   'p2': 2.5, 'p3': 3,   'p4': 2,   'p5': 3,   'ram': '22d'},
    140: {'p1': 3,   'p2': 3,   'p3': 3,   'p4': 2,   'p5': 3,   'ram': '23d'},
    145: {'p1': 3,   'p2': 3,   'p3': 3,   'p4': 2.5, 'p5': 3,   'ram': '24d'},
    150: {'p1': 3,   'p2': 3,   'p3': 3,   'p4': 3,   'p5': 3,   'ram': '25d'},
    155: {'p1': 3.5, 'p2': 3,   'p3': 3,   'p4': 3,   'p5': 3,   'ram': '26d'},
    160: {'p1': 4,   'p2': 3,   'p3': 3,   'p4': 3,   'p5': 3,   'ram': '27d'},
    165: {'p1': 4,   'p2': 3,   'p3': 3.5, 'p4': 3,   'p5': 3,   'ram': '28d'},
    170: {'p1': 4,   'p2': 3,   'p3': 4,   'p4': 3,   'p5': 3,   'ram': '29d'},
    175: {'p1': 4,   'p2': 3,   'p3': 4,   'p4': 3,   'p5': 3.5, 'ram': '30d'},
    180: {'p1': 4,   'p2': 3,   'p3': 4,   'p4': 3,   'p5': 4,   'ram': '31d'},
    185: {'p1': 4,   'p2': 3.5, 'p3': 4,   'p4': 3,   'p5': 4,   'ram': '32d'},
    190: {'p1': 4,   'p2': 4,   'p3': 4,   'p4': 3,   'p5': 4,   'ram': '33d'},
    195: {'p1': 4,   'p2': 4,   'p3': 4,   'p4': 3.5, 'p5': 4,   'ram': '34d'},
    200: {'p1': 4,   'p2': 4,   'p3': 4,   'p4': 4,   'p5': 4,   'ram': '35d'},
    205: {'p1': 4.5, 'p2': 4,   'p3': 4,   'p4': 4,   'p5': 4,   'ram': '36d'},
    210: {'p1': 5,   'p2': 4,   'p3': 4,   'p4': 4,   'p5': 4,   'ram': '37d'},
    215: {'p1': 5,   'p2': 4,   'p3': 4.5, 'p4': 4,   'p5': 4,   'ram': '38d'},
    220: {'p1': 5,   'p2': 4,   'p3': 5,   'p4': 4,   'p5': 4,   'ram': '39d'},
    225: {'p1': 5,   'p2': 4,   'p3': 5,   'p4': 4,   'p5': 4.5, 'ram': '40d'},
    230: {'p1': 5,   'p2': 4,   'p3': 5,   'p4': 4,   'p5': 5,   'ram': '41d'},
    235: {'p1': 5,   'p2': 4.5, 'p3': 5,   'p4': 4,   'p5': 5,   'ram': '42d'},
    240: {'p1': 5,   'p2': 5,   'p3': 5,   'p4': 4,   'p5': 5,   'ram': '43d'},
    245: {'p1': 5,   'p2': 5,   'p3': 5,   'p4': 4.5, 'p5': 5,   'ram': '44d'},
    250: {'p1': 5,   'p2': 5,   'p3': 5,   'p4': 5,   'p5': 5,   'ram': '45d'},
    255: {'p1': 5.5, 'p2': 5,   'p3': 5,   'p4': 5,   'p5': 5,   'ram': '46d'},
    260: {'p1': 6,   'p2': 5,   'p3': 5,   'p4': 5,   'p5': 5,   'ram': '47d'},
    265: {'p1': 6,   'p2': 5,   'p3': 5.5, 'p4': 5,   'p5': 5,   'ram': '48d'},
    270: {'p1': 6,   'p2': 5,   'p3': 6,   'p4': 5,   'p5': 5,   'ram': '49d'},
    275: {'p1': 6,   'p2': 5,   'p3': 6,   'p4': 5,   'p5': 5.5, 'ram': '50d'},
    280: {'p1': 6,   'p2': 5,   'p3': 6,   'p4': 5,   'p5': 6,   'ram': '51d'},
    285: {'p1': 6,   'p2': 5.5, 'p3': 6,   'p4': 5,   'p5': 6,   'ram': '52d'},
    290: {'p1': 6,   'p2': 6,   'p3': 6,   'p4': 5,   'p5': 6,   'ram': '53d'},
    295: {'p1': 6,   'p2': 6,   'p3': 6,   'p4': 5.5, 'p5': 6,   'ram': '54d'},
    300: {'p1': 6,   'p2': 6,   'p3': 6,   'p4': 6,   'p5': 6,   'ram': '55d'},
}

def get_speed_control(speed: int) -> dict:
    """
    Return the control difficulty row for a given speed.
    Rounds down to the nearest 5 mph increment.
    Returns the row for speed 0 if speed is below 0.
    Returns the row for speed 300 if speed exceeds 300.
    """
    speed = max(0, min(300, (speed // 5) * 5))
    return SPEED_CONTROL[speed]

# Control Table
# Columns represent die roll results from 7 down to -6.
# Values: 'safe' = no effect, 'XX' = crash, integers = maneuver result code
# Each key is a tuple (speed_min, speed_max) representing the speed band.
# 'modifier' is the die roll modifier applied before looking up the result.
#
# Usage: look up the row by speed band, apply modifier to the die roll,
# then look up the result in the columns list (index 0 = roll of 7,
# index 13 = roll of -6).

CONTROL_COLUMNS = [7, 6, 5, 4, 3, 2, 1, 0, -1, -2, -3, -4, -5, -6]

CONTROL_TABLE = {
    (  5,  10): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe',2   ], 'modifier': -3},
    ( 15,  20): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    3   ], 'modifier': -2},
    ( 25,  30): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    4   ], 'modifier': -1},
    ( 35,  40): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    3,    4   ], 'modifier':  0},
    ( 45,  50): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    3,    4,    5   ], 'modifier': +1},
    ( 55,  60): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    3,    4,    4,    5   ], 'modifier': +1},
    ( 65,  70): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe',2,    3,    4,    5,    6   ], 'modifier': +2},
    ( 75,  80): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe','safe',3,    4,    5,    5,    6   ], 'modifier': +2},
    ( 85,  90): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe',2,    3,    5,    5,    6,    'XX'], 'modifier': +2},
    ( 95, 100): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe',2,    4,    5,    6,    6,    'XX'], 'modifier': +3},
    (105, 110): {'results': ['safe','safe','safe','safe','safe','safe','safe','safe',3,    4,    6,    6,    'XX', 'XX'], 'modifier': +3},
    (115, 120): {'results': ['safe','safe','safe','safe','safe','safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX'], 'modifier': +3},
    (125, 130): {'results': ['safe','safe','safe','safe','safe','safe','safe',2,    4,    5,    6,    'XX', 'XX', 'XX'], 'modifier': +4},
    (135, 140): {'results': ['safe','safe','safe','safe','safe','safe','safe',3,    4,    6,    'XX', 'XX', 'XX', 'XX'], 'modifier': +4},
    (145, 150): {'results': ['safe','safe','safe','safe','safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX', 'XX'], 'modifier': +4},
    (155, 160): {'results': ['safe','safe','safe','safe','safe','safe',2,    4,    5,    6,    'XX', 'XX', 'XX', 'XX'], 'modifier': +5},
    (165, 170): {'results': ['safe','safe','safe','safe','safe','safe',3,    4,    6,    'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +5},
    (175, 180): {'results': ['safe','safe','safe','safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +5},
    (185, 190): {'results': ['safe','safe','safe','safe','safe',2,    4,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +6},
    (195, 200): {'results': ['safe','safe','safe','safe','safe',3,    4,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +6},
    (205, 210): {'results': ['safe','safe','safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +6},
    (215, 220): {'results': ['safe','safe','safe','safe',2,    4,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +7},
    (225, 230): {'results': ['safe','safe','safe','safe',3,    4,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +7},
    (235, 240): {'results': ['safe','safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +7},
    (245, 250): {'results': ['safe','safe','safe',2,    4,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +8},
    (255, 260): {'results': ['safe','safe',2,    3,    4,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +8},
    (265, 270): {'results': ['safe','safe',2,    3,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +8},
    (275, 280): {'results': ['safe',2,    3,    4,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +9},
    (285, 290): {'results': ['safe',2,    3,    4,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +9},
    (295, 300): {'results': ['safe',3,    4,    5,    6,    'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX', 'XX'], 'modifier': +9},
}

def get_control_row(speed: int) -> dict:
    """
    Return the control table row for a given speed.
    Returns None if speed is below 5 (no control check needed)
    or above 300.
    """
    for (speed_min, speed_max), row in CONTROL_TABLE.items():
        if speed_min <= speed <= speed_max:
            return row
    return None

def lookup_control_result(speed: int, die_roll: int) -> str:
    """
    Given a speed and a raw die roll (before modifier),
    return the control result: 'safe', 'XX', or an integer
    maneuver code.

    The modifier from the speed band is applied to the die roll
    before the column is looked up.
    """
    row = get_control_row(speed)
    if row is None:
        return 'safe'

    modified_roll = die_roll + row['modifier']

    # Clamp to valid column range
    modified_roll = max(-6, min(7, modified_roll))

    # Find the index of this roll value in CONTROL_COLUMNS
    col_index = CONTROL_COLUMNS.index(modified_roll)

    return row['results'][col_index]

def roll_d6() -> int:
    """Roll a single six-sided die."""
    return random.randint(1, 6)

def resolve_control_check(speed: int, die_roll: int) -> dict:
    """
    Given a speed and a raw die roll, resolve the full control check.

    Returns a dict with:
        'modified_roll'  : the die roll after applying the speed modifier
        'result'         : 'safe', 'crash', or 'check'
        'threshold'      : the minimum roll needed (None if safe/crash directly)
        'passed'         : True if the control check was passed
        'description'    : human-readable outcome
    """
    row = get_control_row(speed)
    if row is None:
        return {
            'modified_roll': die_roll,
            'result':        'safe',
            'threshold':     None,
            'passed':        True,
            'description':   'No control check required at this speed.'
        }

    modified_roll = max(-6, min(7, die_roll + row['modifier']))
    col_index     = CONTROL_COLUMNS.index(modified_roll)
    cell          = row['results'][col_index]

    if cell == 'safe':
        return {
            'modified_roll': modified_roll,
            'result':        'safe',
            'threshold':     None,
            'passed':        True,
            'description':   'Control maintained — no check required.'
        }

    if cell == 'XX':
        return {
            'modified_roll': modified_roll,
            'result':        'crash',
            'threshold':     None,
            'passed':        False,
            'description':   'Automatic crash — no save possible.'
        }

    # Integer threshold — player must roll this or higher on a D6 to stay safe
    threshold  = cell
    d6_roll    = roll_d6()
    passed     = d6_roll >= threshold

    return {
        'modified_roll': modified_roll,
        'result':        'safe' if passed else 'crash',
        'threshold':     threshold,
        'd6_roll':       d6_roll,
        'passed':        passed,
        'description':   (
            f'Control check required: needed {threshold}+, '
            f'rolled {d6_roll} — {"PASSED" if passed else "FAILED"}.'
        )
    }

def get_phase_movement(speed: int, phase: int) -> float:
    """
    Return the number of car lengths a vehicle moves in a given phase
    based on its current speed.

    Phase is 1-5. Returns a float (0, 0.5, 1.0, 1.5, 2.0, etc.)
    Returns 0 if speed is 0 or phase is out of range.

    The phase column mapping from the SPEED_CONTROL table:
        phase 1 = p1, phase 2 = p2, phase 3 = p3,
        phase 4 = p4, phase 5 = p5
    """
    if phase < 1 or phase > 5:
        return 0.0
    row = get_speed_control(speed)
    if row is None:
        return 0.0
    phase_key = f'p{phase}'
    return float(row.get(phase_key, 0.0))

def build_movement_queue(players: list, phase: int) -> dict:
    """
    Build the compact movement queue structure for a phase.
    players: list of dicts, each with 'username', 'current speed'
    Returns a MovementQueue dict ready to be written to the phase file.
    """
    # Speeds where the only movement in any phase that yields 0.5
    # is a forced straight with no maneuver and no order choice
    HALF_ONLY_SPEEDS = (15, 25, 35, 45)
    
    queue_players = []
    for p in players:
        username = p['username']
        speed = int(p.get('current_speed', p.get('current speed', 0)))
        lengths = get_phase_movement(speed, phase)
        
        if lengths == 0.0:
            continue
            
        # Determine half and full components
        full_lengths = int(lengths)
        has_half = (lengths % 1) == 0.5
        
        # Is the half forced straight with no order choice?
        half_forced = has_half and (speed in HALF_ONLY_SPEEDS or full_lengths == 0)
        
        queue_players.append({
            'username': username,
            'speed': speed,
            'car_lengths': lengths,
            'remaining': lengths,
            'full_remaining': full_lengths,
            'half_remaining': 0.5 if has_half else 0.0,
            'half_forced': half_forced,
            'maneuvered': False,
            'done': False
        })
        
    # Sort descending by speed
    queue_players.sort(key=lambda p: p['speed'], reverse=True)
    
    # Seeds the subphase and initiative trackers directly into the core object payload
    return {
        'MovementQueue': 'MovementQueue',
        'phase': phase,
        'players': queue_players,
        'round': 1,
        'complete': False,
        'current_system_subphase': 'Movement',
        'active_player_turn': queue_players[0]['username'] if queue_players else 'None',
        'game_name': 'Car Wars Arena',
        'turn_count': 1
    }

def get_current_mover(queue: dict) -> dict | None:
    """
    Return the player entry whose turn it currently is,
    or None if the phase is complete.

    Rules:
    - Find the first player in sorted order who still has remaining > 0
      for this round
    - If that player is already maneuvered (forced Straight) or their
      only remaining is a forced half, they get auto-processed
    - Returns None when all players have remaining == 0
    """
    players = queue.get('players', [])
    for p in players:
        if p['done']:
            continue
        if p['remaining'] > 0:
            return p
    return None

# game_tables.py (Updated Function Append)

def process_end_of_turn_hc_recovery(car_record: dict) -> None:
    """
    Executes official Car Wars End of Turn (EOT) Handling Class recovery math.
    Increases the current HC by max_hc (or by 1 if max_hc < 1), 
    capping the final value at max_hc.
    """
    if not car_record:
        return

    try:
        # 1. Safely extract and parse current metrics (handling string/numeric mix)
        current_hc = float(car_record.get('hc', 0.0))
        max_hc = float(car_record.get('max_hc', 1.0))
        
        # 2. Determine recovery step: Add max_hc, but if max_hc is under 1, add 1 instead
        recovery_amount = max_hc if max_hc >= 1.0 else 1.0
        
        # 3. Calculate new score and apply hard ceiling cap at max_hc
        new_hc = current_hc + recovery_amount
        if new_hc > max_hc:
            new_hc = max_hc
            
        # 4. Save clean formatted string/int back to matching chassis record slots
        # If max_hc is a whole number (like 3.0), we can format it clean or store as float
        car_record['hc'] = str(int(new_hc)) if new_hc.is_integer() else str(round(new_hc, 1))
        
        print(f"[EOT RECOVERY] Restored vehicle HC from {current_hc} -> {car_record['hc']} (Max: {max_hc})")
        
    except Exception as e:
        print(f"[EOT RECOVERY ERROR] Failed to compute handling recovery math: {e}")

