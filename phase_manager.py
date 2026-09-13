import os
import re
from game_engine import GameEngine

class PhaseProgressionManager:
    """
    Automates Car Wars game state transitions by checking vehicle movement lengths
    and switching subphase states between [Movement] and [Combat].
    """

    @classmethod
    def evaluate_phase_completion2(cls, game_id: str) -> tuple[bool, str]:
        """
        Scans active vehicle files to determine if all drivers have exhausted 
        their allowed movement segments for the current phase step.
        """
        from game_tables import get_phase_movement

        # 1. Read active game records
        all_files = os.listdir('./games')
        game_files = sorted([f for f in all_files if f.startswith(game_id) and f.endswith('.txt')])
        if not game_files:
            return False, "Active game file context missing."

        filepath = os.path.join('./games', game_files[-1])
        records = GameEngine.read_game_file(filepath)

        # 2. Extract current global movement queue context metadata
        mq_index, mq_record = next(
            ((idx, r) for idx, r in enumerate(records) if r.get('MovementQueue') == 'MovementQueue'),
            (None, None)
        )
        if not mq_record:
            return False, "Global MovementQueue state record missing from flat file database."

        current_phase = int(mq_record.get('phase', 1))
        current_subphase = mq_record.get('current_system_subphase', 'Movement')

        # If we are already in Combat subphase, wait for combat inputs to call next step
        if current_subphase == 'Combat':
            return True, "Already in Combat mode loop. Waiting for combat step conclusions."

        # 3. Scan all active vehicles to verify phase movement exhaustion
        all_cars_moved = True
        active_cars = [r for r in records if r.get('CarPosition') == 'CarPosition']

        for car in active_cars:
            username = car.get('owner')
            current_speed = int(float(car.get('current_speed', 0)))

            try:
                allowed_segments = int(get_phase_movement(current_speed, current_phase))
            except Exception:
                allowed_segments = 0

            if allowed_segments < 2 and current_speed == 60 and current_phase == 1:
                allowed_segments = 2
            if allowed_segments < 1:
                allowed_segments = 1

            proposed_node = next(
                (r for r in records if r.get('ProposedCarPosition') == 'ProposedCarPosition' and r.get('owner') == username),
                None
            )

            if proposed_node:
                all_cars_moved = False
                break

        # 4. Automate the subphase transition if all movements are spent
        if all_cars_moved:
            mq_record['current_system_subphase'] = 'Combat'
            mq_record['active_player_turn'] = cls.calculate_combat_initiative(active_cars)

            GameEngine.write_game_file(filepath, records)
            return True, "AUTOMATIC SYSTEM LOCK: Phase movement exhausted. Ticker switched to [Combat]."

        return False, "Waiting for remaining drivers to commit movement vectors."

    @classmethod
    def evaluate_phase_completion(cls, game_id: str) -> tuple[bool, str]:
        """
        Scans active vehicle files to determine if all drivers have exhausted 
        their allowed movement segments for the current phase step.
        """
        from game_tables import get_phase_movement

        game_dir = os.path.join('./games', game_id)
        if not os.path.isdir(game_dir):
            return False, "Active game file context missing."

        game_files = [f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')]
        game_files.sort()

        if not game_files:
            return False, "Active game file context missing."

        filepath = os.path.join(game_dir, game_files[-1])
        records = GameEngine.read_game_file(filepath)

        mq_index, mq_record = next(
            ((idx, r) for idx, r in enumerate(records) if r.get('MovementQueue') == 'MovementQueue'),
            (None, None)
        )
        if not mq_record:
            return False, "Global MovementQueue state record missing from flat file database."

        current_phase = int(mq_record.get('phase', 1))
        current_subphase = mq_record.get('current_system_subphase', 'Movement')

        if current_subphase == 'Combat':
            return True, "Already in Combat mode loop. Waiting for combat step conclusions."

        all_cars_moved = True
        active_cars = [r for r in records if r.get('CarPosition') == 'CarPosition']

        for car in active_cars:
            username = car.get('owner')
            current_speed = int(float(car.get('current_speed', 0)))

            try:
                allowed_segments = int(get_phase_movement(current_speed, current_phase))
            except Exception:
                allowed_segments = 0

            if allowed_segments < 2 and current_speed == 60 and current_phase == 1:
                allowed_segments = 2
            if allowed_segments < 1:
                allowed_segments = 1

            proposed_node = next(
                (r for r in records if r.get('ProposedCarPosition') == 'ProposedCarPosition' and r.get('owner') == username),
                None
            )

            if proposed_node:
                all_cars_moved = False
                break

        if all_cars_moved:
            mq_record['current_system_subphase'] = 'Combat'
            mq_record['active_player_turn'] = cls.calculate_combat_initiative(active_cars)

            GameEngine.write_game_file(filepath, records)
            return True, "AUTOMATIC SYSTEM LOCK: Phase movement exhausted. Ticker switched to [Combat]."

        return False, "Waiting for remaining drivers to commit movement vectors."

# Replace your advance_to_next_phase_or_turn method on page 3-4 of phase_manager.py with this:
    @classmethod
    def advance_to_next_phase_or_turn(cls, game_id: str) -> tuple[bool, str]:
        """
        Advances the global tracking state from Combat back to Movement on the next phase tier.
        Generates a brand new distinct flat file layout matching the updated counters, 
        recalculating car length values and remaining distance dynamically per speed chart guidelines.
        """
        from game_tables import get_phase_movement

        game_dir = os.path.join('./games', game_id)
        if not os.path.isdir(game_dir):
            return False, "Active game file context missing."

        game_files = [f for f in os.listdir(game_dir) if re.match(r'^T\d+P', f) and f.endswith('.txt')]
        game_files.sort()

        if not game_files:
            return False, "Active game file context missing."

        # Read state parameters from our previous workspace file
        old_filepath = os.path.join(game_dir, game_files[-1])
        records = GameEngine.read_game_file(old_filepath)

        mq_index, mq_record = next(
            ((idx, r) for idx, r in enumerate(records) if r.get('MovementQueue') == 'MovementQueue'),
            (None, None)
        )

        if not mq_record:
            return False, "Global MovementQueue state record missing from flat file database."

        current_phase = int(mq_record.get('phase', 1))
        current_turn = int(mq_record.get('turn_count', 1))

        # 1. Update the Tracker Metrics Locally
        if current_phase < 5:
            next_phase = current_phase + 1
            next_turn = current_turn
            mq_record['phase'] = next_phase
            mq_record['current_system_subphase'] = 'Movement'
            mq_record['complete'] = False
        else:
            next_phase = 1
            next_turn = current_turn + 1
            mq_record['phase'] = next_phase
            mq_record['turn_count'] = next_turn
            mq_record['current_system_subphase'] = 'Movement'
            mq_record['complete'] = False
            mq_record['requires_turn_speed_selection'] = True

            # End of Turn Cleanups
            from game_tables import process_end_of_turn_hc_recovery
            for r in records:
                if r.get('CarPosition') == 'CarPosition':
                    process_end_of_turn_hc_recovery(r)
            GameEngine.reset_all_players_turn_actions(game_id)

        # ── RECALCULATE MOVEMENT BUDGET DATA PER SPEED & PHASE ── 🛠
        players_list = mq_record.get('players', [])
        for p in players_list:
            player_speed = int(float(p.get('speed', 60)))
            
            # Query chart metrics using next_phase context
            try:
                allowed_segments = float(get_phase_movement(player_speed, next_phase))
            except Exception:
                allowed_segments = 0.0

            # Initialize fresh matching targets for the newly generated file
            p['car_lengths'] = allowed_segments
            p['remaining'] = allowed_segments
            p['full_remaining'] = int(allowed_segments)
            p['half_remaining'] = float(allowed_segments % 1 != 0) # Track fractional segment remnants if odd
            
            # Flush player state interaction switches
            p['done'] = False
            p['moved_this_segment'] = False
            p['maneuvered'] = False
            p['half_forced'] = False

        active_cars = [r for r in records if r.get('CarPosition') == 'CarPosition']
        if active_cars:
            mq_record['active_player_turn'] = active_cars[0].get('owner', 'Player 1')

        # 2. Build the NEW distinct filename destination target string
        new_filename = f"T{next_turn}P{next_phase}M.txt"
        new_filepath = os.path.join(game_dir, new_filename)

        # Clear out any ghost nodes left from past tracking iterations before cloning
        cleaned_records = [r for r in records if r.get('ProposedCarPosition') != 'ProposedCarPosition']

        # Update the embedded object within our array block
        for idx, entry in enumerate(cleaned_records):
            if entry.get('MovementQueue') == 'MovementQueue':
                cleaned_records[idx] = mq_record
                break

        # Save updates out to our NEW distinct phase text ledger file target
        GameEngine.write_game_file(new_filepath, cleaned_records)
        print(f"[ENGINE SUCCESS] Instantiated tracking step ledger with correct budgets: {new_filename}")

        return True, f"Advanced to Turn {next_turn}, Phase {next_phase} [Movement]."

    @staticmethod
    def calculate_combat_initiative(active_cars: list) -> str:
        """Determines who gets to fire weapons first based on highest current velocity."""
        if not active_cars:
            return "Unknown"
        sorted_cars = sorted(active_cars, key=lambda c: float(c.get('current_speed', 0.0)), reverse=True)
        return sorted_cars[0].get('owner', 'Unknown')
