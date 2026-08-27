import math

class CombatGeometryEngine:
    """
    Manages pinpoint weapon placement coordinates, directional fire arcs,
    and Line-of-Sight ray-casting obstruction checks.
    """

    @staticmethod
    def get_weapon_origin(car_x: float, car_y: float, orientation_deg: float, 
                          facing: str, length: float = 1.0, width: float = 0.5) -> tuple[float, float]:
        """
        Calculates pinpoint coordinate origins (in game inches)
        based on midpoints of faces or dead center for turrets.
        """
        rad = math.radians(orientation_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # Turrets rest precisely in the dead center
        if facing == "Top":
            return car_x, car_y
            
        # Offset vectors from pivot center
        half_l = length / 2.0
        half_w = width / 2.0
        
        if facing == "Front":
            # Exactly in the middle of the front edge
            dx, dy = half_l, 0.0
        elif facing == "Back":
            # Exactly in the middle of the rear edge
            dx, dy = -half_l, 0.0
        elif facing == "Left":
            # Exactly in the middle of the left edge
            dx, dy = 0.0, -half_w
        elif facing == "Right":
            # Exactly in the middle of the right edge
            dx, dy = 0.0, half_w
        else:
            return car_x, car_y

        # Apply matrix translation
        rx = car_x + (dx * sin_a + dy * cos_a)
        ry = car_y + (-dx * cos_a + dy * sin_a)
        return round(rx, 2), round(ry, 2)

    @staticmethod
    def determine_relative_arc(origin_x: float, origin_y: float, firer_orientation_deg: float, 
                               target_x: float, target_y: float) -> str:
        """
        Maps a target's position relative to the diagonal intersecting fields of fire:
        Front/Back = 60 degrees wide apex, Left/Right = 120 degrees wide apex.
        """
        dx = target_x - origin_x
        dy = target_y - origin_y
        
        # PATCH (bug fix): was math.atan2(dy, dx), the standard math-angle
        # convention (0=east, counter-clockwise). get_weapon_origin's own
        # rotation matrix -- and `orientation`'s real meaning, confirmed
        # against the map's StartingPosition data -- uses a COMPASS
        # convention instead (0=north, clockwise). Mixing the two caused a
        # target directly ahead of a north-facing car to be reported as
        # "Left" instead of "Front". atan2(dx, -dy) matches the compass
        # convention get_weapon_origin already uses correctly.
        target_angle = math.degrees(math.atan2(dx, -dy)) % 360
        relative_angle = (target_angle - firer_orientation_deg) % 360
        
        if relative_angle <= 30 or relative_angle >= 330:
            return "Front"
        elif 30 < relative_angle < 150:
            return "Right"
        elif 150 <= relative_angle <= 210:
            return "Back"
        else:
            return "Left"

    @classmethod
    def is_line_of_sight_blocked(cls, weapon_origin: tuple, target_center: tuple, map_obstacles: list) -> bool:
        """
        Ray-casts a straight line between the weapon mounting point and target center.
        Re-uses your SAT logic by building a micro-bounding box line block to check blocks.
        """
        wx, wy = weapon_origin
        tx, ty = target_center
        
        ray_vertices = [(wx, wy), (tx, ty), (tx + 0.01, ty + 0.01), (wx + 0.01, wy + 0.01)]
        
        from collision_engine import CollisionEngine
        # PATCH (bug fix): extract_pixel_vertices is a @staticmethod on the
        # GameEngine class, not a module-level function -- the old
        # `from game_engine import extract_pixel_vertices` raised an
        # ImportError on every call, before any collision logic could run.
        from game_engine import GameEngine

        for obstacle in map_obstacles:
            # PATCH (bug fix): 'CarPosition' and 'ProposedCarPosition' were
            # NOT excluded here, and extract_pixel_vertices DOES build a
            # real solid bounding box for car entries. Since a shot's ray
            # always starts at (or near) the shooter's own car and always
            # ends at the target's own center -- which sits exactly inside
            # that car's own extracted box -- every shot was self-colliding
            # with the shooter's and/or target's own vehicle and being
            # reported as blocked, regardless of what was actually on the
            # map. If you want OTHER vehicles to block LOS as cover, that's
            # a separate, deliberate design choice -- but the shooter's own
            # car and the specific target's own car must always be excluded,
            # or every shot blocks itself.
            if any(k in obstacle for k in
                   ['Text', 'StartingPosition', 'map_size', 'CarPosition', 'ProposedCarPosition']):
                continue
                
            obs_poly = GameEngine.extract_pixel_vertices(obstacle)
            if not obs_poly: continue
            
            # Sub-scale ray bounds to match the 40x pixel multiplier engine layout
            ray_pixel_poly = [(x * 40.0, y * 40.0) for x, y in ray_vertices]
            
            if CollisionEngine.check_sat_collision(ray_pixel_poly, obs_poly):
                return True 
        return False