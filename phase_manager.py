import os
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
            
            # Look up how many segments this vehicle is supposed to move in this phase
            try:
                allowed_segments = int(get_phase_movement(current_speed, current_phase))
            except Exception:
                allowed_segments = 0
                
            # Enforce minimal tracking defaults matching game engine layout files
            if allowed_segments < 2 and current_speed == 60 and current_phase == 1:
                allowed_segments = 2
            if allowed_segments < 1:
                allowed_segments = 1
                
            # Check if this player has committed their unconfirmed preview ghost nodes
            has_confirmed_move = True
            proposed_node = next(
                (r for r in records 
                 if r.get('ProposedCarPosition') == 'ProposedCarPosition' 
                 and r.get('owner') == username),
                None
            )
            
            # If a ghost node exists, they haven't locked down their current phase segment movement yet
            if proposed_node:
                all_cars_moved = False
                break

        # 4. Automate the subphase transition if all movements are spent
        if all_cars_moved:
            mq_record['current_system_subphase'] = 'Combat'
            # Set the active player ticker back to whoever has combat weapon initiative
            mq_record['active_player_turn'] = cls.calculate_combat_initiative(active_cars)
            
            # Save mutated updates back down to the text-line file database
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
    
        # 1. Read active game records
        game_dir = os.path.join('./games', game_id)
        if not os.path.isdir(game_dir):
            return False, "Active game file context missing."
    
        game_files = [
            f for f in os.listdir(game_dir)
            if re.match(r'^T\d+P', f) and f.endswith('.txt')
        ]
        game_files.sort()
    
        if not game_files:
            return False, "Active game file context missing."
    
        filepath = os.path.join(game_dir, game_files[-1])
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
    
            # Look up how many segments this vehicle is supposed to move in this phase
            try:
                allowed_segments = int(get_phase_movement(current_speed, current_phase))
            except Exception:
                allowed_segments = 0
    
            # Enforce minimal tracking defaults matching game engine layout files
            if allowed_segments < 2 and current_speed == 60 and current_phase == 1:
                allowed_segments = 2
            if allowed_segments < 1:
                allowed_segments = 1
    
            # Check if this player has committed their unconfirmed preview ghost nodes
            has_confirmed_move = True
            proposed_node = next(
                (r for r in records 
                 if r.get('ProposedCarPosition') == 'ProposedCarPosition' 
                 and r.get('owner') == username),
                None
            )
    
            # If a ghost node exists, they haven't locked down their current phase segment movement yet
            if proposed_node:
                all_cars_moved = False
                break
    
        # 4. Automate the subphase transition if all movements are spent
        if all_cars_moved:
            mq_record['current_system_subphase'] = 'Combat'
            # Set the active player ticker back to whoever has combat weapon initiative
            mq_record['active_player_turn'] = cls.calculate_combat_initiative(active_cars)
    
            # Save mutated updates back down to the text-line file database
            GameEngine.write_game_file(filepath, records)
            return True, "AUTOMATIC SYSTEM LOCK: Phase movement exhausted. Ticker switched to [Combat]."
    
        return False, "Waiting for remaining drivers to commit movement vectors."
        
    @classmethod
    def advance_to_next_phase_or_turn(cls, game_id: str) -> tuple[bool, str]:
        """
        Advances the global tracking state from Combat back to Movement on the next phase tier.
        Increments through Phase 1-5 before starting a brand new Game Turn.
        """
        game_dir = os.path.join('./games', game_id)
        if not os.path.isdir(game_dir):
            return False, "Active game file context missing."
    
        game_files = [
            f for f in os.listdir(game_dir)
            if re.match(r'^T\d+P', f) and f.endswith('.txt')
        ]
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
        current_turn = int(mq_record.get('turn_count', 1))
    
        # 1. Increment Phase Counter
        if current_phase < 5:
            # Shift to next movement block within the same turn
            mq_record['phase'] = current_phase + 1
            mq_record['current_system_subphase'] = 'Movement'
        else:
            # Phase 5 concluded: Reset phases and increment global Turn Number counter
            mq_record['phase'] = 1
            mq_record['turn_count'] = current_turn + 1
            mq_record['current_system_subphase'] = 'Movement'
        
            # End of Turn: trigger automatic Handling Class recovery calculations across all cars
            from game_tables import process_end_of_turn_hc_recovery
            for r in records:
                if r.get('CarPosition') == 'CarPosition':
                    process_end_of_turn_hc_recovery(r)
        
            # End of Turn: reset every player's per-turn firing-action tracking
            GameEngine.reset_all_players_turn_actions(game_id)

        # 2. Reset active driver initialization order back to Phase 1 setup rules
        active_cars = [r for r in records if r.get('CarPosition') == 'CarPosition']
        if active_cars:
            mq_record['active_player_turn'] = active_cars[0].get('owner', 'Player 1')
    
        GameEngine.write_game_file(filepath, records)
        return True, f"Advanced to Turn {mq_record['turn_count']}, Phase {mq_record['phase']} [Movement]."
        
    @staticmethod
    def calculate_combat_initiative(active_cars: list) -> str:
        """Determines who gets to fire weapons first based on highest current velocity."""
        if not active_cars:
            return "Unknown"
        # Sort cars descending by speed; fastest driver acts first in combat subphases
        sorted_cars = sorted(active_cars, key=lambda c: float(c.get('current_speed', 0.0)), reverse=True)
        return sorted_cars[0].get('owner', 'Unknown')
