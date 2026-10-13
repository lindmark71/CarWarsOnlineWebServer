import os
import re
from game_engine import GameEngine

class PhaseProgressionManager:
    """
    Automates Car Wars game state transitions by checking vehicle movement lengths
    and switching subphase states between [Movement] and [Combat].
    """

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

        filepath = PhaseProgressionManager.latest_phase_file(game_dir=game_dir)
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

    @classmethod
    def advance_to_next_phase_or_turn(cls, game_id: str) -> tuple[bool, str]:
        from game_tables import (build_movement_queue, build_combat_queue,
                                 process_end_of_turn_hc_recovery)

        game_dir = os.path.join('./games', str(game_id).strip())
        if not os.path.isdir(game_dir):
            return False, "Active game file context missing."

        latest = GameEngine.latest_phase_file(game_dir)
        m = re.match(r'^T(\d+)P(\d+)', latest) if latest else None
        if not m:
            return False, "Active game file context missing."
        turn, phase = int(m.group(1)), int(m.group(2))

        records = GameEngine.read_game_file(os.path.join(game_dir, latest))
        old_mq = next((r for r in reversed(records)
                       if r.get('MovementQueue') == 'MovementQueue'), {})
        game_name = old_mq.get('game_name', 'Car Wars Arena')

        if phase < 5:
            next_turn, next_phase = turn, phase + 1
        else:
            next_turn, next_phase = turn + 1, 1

        # Drop ghosts and BOTH old queues; they get rebuilt below.
        records = [r for r in records
                   if r.get('ProposedCarPosition') != 'ProposedCarPosition'
                   and r.get('MovementQueue') != 'MovementQueue'
                   and r.get('CombatQueue') != 'CombatQueue']

        if next_phase == 1:   # end-of-turn cleanup
            for r in records:
                if r.get('CarPosition') == 'CarPosition':
                    process_end_of_turn_hc_recovery(r)
            GameEngine.reset_all_players_turn_actions(game_id)

        # One entry per owner (newest wins), ordered by position number
        by_owner = {}
        for r in records:
            if r.get('CarPosition') == 'CarPosition':
                by_owner[r.get('owner')] = r
        players = sorted(
            [{'username': o,
              'current_speed': int(float(c.get('current_speed', 0))),
              'position_number': c.get('player_number')}
             for o, c in by_owner.items()],
            key=lambda p: int(p['position_number'] or 0))
        if not players:
            return False, "No CarPosition records found."

        combat_queue = build_combat_queue(players, game_dir)   # ALL cars, not just movers

        new_name = f"T{next_turn}P{next_phase}M.txt"
        new_path = os.path.join(game_dir, new_name)

        # ── 1. BUILD THE QUEUES (everything below this line may use `queue`) ──
        queue = build_movement_queue(players, next_phase)
        queue['game_name'] = game_name
        queue['turn_count'] = next_turn
        queue['round'] = next_turn
        queue['complete'] = False
        queue['current_system_subphase'] = 'Movement'
        for p in queue['players']:
            p['moved_this_segment'] = False        

        if next_phase == 1:
            # New turn: every player picks a speed before anyone moves
            queue['requires_turn_speed_selection'] = True
            queue['speed_pending'] = [p['username'] for p in players]            

        if not queue['players']:
            # ── NOBODY MOVES THIS PHASE: adjudicate it and go straight to combat ──
            queue['complete'] = True
            queue['active_player_turn'] = cls.calculate_combat_initiative(list(by_owner.values()))

            # 1. Movement file is written first, recording that it was empty and resolved
            GameEngine.write_game_file(new_path, records + [queue, combat_queue])

            # 2. Combat file is the same state with the subphase flipped,
            #    matching what handle_game_confirm_move writes when movement finishes normally
            queue['current_system_subphase'] = 'Combat'
            combat_name = f"T{next_turn}P{next_phase}C.txt"
            GameEngine.write_game_file(os.path.join(game_dir, combat_name),
                                       records + [queue, combat_queue])

            print(f"[ENGINE] No movement in T{next_turn}P{next_phase}; created {new_name} and {combat_name}")
            return True, (f"Advanced to Turn {next_turn}, Phase {next_phase}. "
                          f"No movement this phase; now in [Combat].")

        records.append(queue)
        records.append(combat_queue)
        GameEngine.write_game_file(new_path, records)
        print(f"[ENGINE SUCCESS] Created {new_name}")
        return True, f"Advanced to Turn {next_turn}, Phase {next_phase} [Movement]."
    
    @staticmethod
    def calculate_combat_initiative(active_cars: list) -> str:
        """Determines who gets to fire weapons first based on highest current velocity."""
        if not active_cars:
            return "Unknown"
        sorted_cars = sorted(active_cars, key=lambda c: float(c.get('current_speed', 0.0)), reverse=True)
        return sorted_cars[0].get('owner', 'Unknown')

    @staticmethod
    def latest_phase_file(game_dir: str) -> str:
        """Latest T#P#[M|C].txt by (turn, phase, C-after-M). '' if none."""
        best, best_key = '', None
        for f in os.listdir(game_dir):
            m = re.match(r'^T(\d+)P(\d+)([MC]?)\.txt$', f)
            if m:
                key = (int(m.group(1)), int(m.group(2)), 1 if m.group(3) == 'C' else 0)
                if best_key is None or key > best_key:
                    best, best_key = f, key
        return best
