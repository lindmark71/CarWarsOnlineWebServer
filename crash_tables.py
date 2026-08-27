import random
import math

class CrashTablesEngine:
    """Manages tactical skids, 90° spinout checking adjustments, and rollover mechanics."""

    @staticmethod
    def calculate_crash_roll(base_difficulty: int, driver_skill: int = 0) -> int:
        """Formula: 2D6 + (Difficulty - 3) - Driver Skill"""
        return (random.randint(1, 6) + random.randint(1, 6)) + (base_difficulty - 3) - driver_skill

    @classmethod
    def resolve_table_2_hazard(cls, difficulty: int, driver_skill: int = 0) -> dict:
        roll = cls.calculate_crash_roll(difficulty, driver_skill)
        direction = "Left" if random.random() < 0.5 else "Right"
        
        if roll <= 4:
            return {"status": "FISHTAIL_MINOR", "squares": 1, "dir": direction, "cascade": False}
        if roll <= 8:
            return {"status": "FISHTAIL_MAJOR", "squares": 2, "dir": direction, "cascade": False}
        if roll <= 10:
            return {"status": "FISHTAIL_MINOR", "squares": 1, "dir": direction, "cascade": True}
        if roll <= 14:
            return {"status": "FISHTAIL_MAJOR", "squares": 2, "dir": direction, "cascade": True}
        return {"status": "FISHTAIL_COMPOUND", "squares": 3, "dir": direction, "cascade": True}

    @classmethod
    def execute_rollover_phase(cls, car: dict, previous_heading_deg: float) -> list:
        """Slides 1 inch, flips 90°, and strips tire pools first if hitting underbody."""
        cx = float(car.get('local_starting_x_qty', 0.0))
        cy = float(car.get('local_starting_y_qty', 0.0))
        rad = math.radians(previous_heading_deg)
        
        car['local_starting_x_qty'] = round(cx + (math.sin(rad) * 1.0), 2)
        car['local_starting_y_qty'] = round(cy + (-math.cos(rad) * 1.0), 2)
        
        sequence = ["Left", "Top", "Right", "Underbody"]
        step = int(car.get('rollover_step_count', 0))
        facing = sequence[step % 4]
        damage = random.randint(1, 6)
        log = []

        if facing == "Underbody":
            f_tire = int(car.get('front_tire_dp', 9))
            r_tire = int(car.get('rear_tire_dp', 0))
            if f_tire > 0 or r_tire > 0:
                log.append("Rollover: Underbody impact shielded by active tire groups!")
                car['front_tire_dp'] = max(0, f_tire - (random.randint(1, 6) + random.randint(1, 6)))
                car['rear_tire_dp'] = max(0, r_tire - (random.randint(1, 6) + random.randint(1, 6)))
            else:
                log.append("Rollover: Tires gone! Underbody armor takes direct hit damage.")
                car["self.var_outer_underbody_armor_allocation_qty"] = max(0, int(car.get("self.var_outer_underbody_armor_allocation_qty", 0)) - damage)
        else:
            mapping = {"Left": "self.var_outer_left_armor_allocation_qty", "Top": "self.var_outer_top_armor_allocation_qty", "Right": "self.var_outer_right_armor_allocation_qty"}
            k = mapping[facing]
            car[k] = max(0, int(car.get(k, 0)) - damage)
            log.append(f"Rollover: Car flips onto {facing}. Panel takes {damage} damage.")

        speed = max(0, int(car.get('current_speed', 0)) - 4) # Bleeds 20mph per turn (4 per phase)
        car['current_speed'] = speed
        car['rollover_step_count'] = step + 1
        if speed == 0:
            car['active_driving_mode'] = 'STOPPED_UPSIDE_DOWN' if (step % 4) != 3 else 'STABLE'
        return log
