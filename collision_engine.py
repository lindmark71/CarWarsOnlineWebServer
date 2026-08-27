import math

class CollisionEngine:
    """
    Handles mixed-geometry intersection and 3D boundary layer analysis 
    between active vehicles, rectangular walls, and circular barriers.
    """

    @staticmethod
    def verify_3d_z_overlap(obj_a: dict, obj_b: dict) -> bool:
        """Returns True if two models share a vertical height tracking horizon."""
        floor_a = float(obj_a.get('local_z_floor_qty', 0.0))
        ceil_a = float(obj_a.get('local_z_ceiling_qty', floor_a + 1.0))
        
        floor_b = float(obj_b.get('local_z_floor_qty', 0.0))
        ceil_b = float(obj_b.get('local_z_ceiling_qty', floor_b + 1.0))
        
        if ceil_a <= floor_b or ceil_b <= floor_a:
            return False  # Clearance gap found; one passes under/over the other
        return True

    @staticmethod
    def get_normals(points: list) -> list:
        """Extracts perpendicular normal vectors for all polygon boundaries."""
        normals = []
        qty = len(points)
        for i in range(qty):
            p1 = points[i]
            p2 = points[(i + 1) % qty]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.hypot(dx, dy)
            if length != 0:
                normals.append((-dy / length, dx / length))
        return normals

    @staticmethod
    def project_polygon(points: list, axis: tuple) -> tuple:
        """Projects coordinate points onto a target vector axis line."""
        dots = [pt[0] * axis[0] + pt[1] * axis[1] for pt in points]
        return min(dots), max(dots)

    @classmethod
    def check_sat_collision(cls, poly_a: list, poly_b: list) -> bool:
        """Returns True if shapes overlap on every single edge tracking axis."""
        if not poly_a or not poly_b:
            return False
        axes = cls.get_normals(poly_a) + cls.get_normals(poly_b)
        for axis in axes:
            min_a, max_a = cls.project_polygon(poly_a, axis)
            min_b, max_b = cls.project_polygon(poly_b, axis)
            if max_a < min_b or max_b < min_a:
                return False  # Separating axis gap found
        return True

    @classmethod
    def check_polygon_vs_circle(cls, vertices: list, center: tuple, radius: float) -> bool:
        """Implements an expanded SAT sweep projecting polygon vertices and curves."""
        cx, cy = center
        closest_vertex = min(vertices, key=lambda v: math.hypot(v[0] - cx, v[1] - cy))
        
        axis_x = cx - closest_vertex[0]
        axis_y = cy - closest_vertex[1]
        axis_len = math.hypot(axis_x, axis_y)
        
        axes = cls.get_normals(vertices)
        if axis_len != 0:
            axes.append((axis_x / axis_len, axis_y / axis_len))

        for axis in axes:
            poly_dots = [v[0] * axis[0] + v[1] * axis[1] for v in vertices]
            min_poly, max_poly = min(poly_dots), max(poly_dots)
            
            circle_dot = cx * axis[0] + cy * axis[1]
            min_circle = circle_dot - radius
            max_circle = circle_dot + radius
            
            if max_poly < min_circle or max_circle < min_poly:
                return False
        return True

    @staticmethod
    def is_angle_in_arc(angle: float, start_deg: float, end_deg: float) -> bool:
        """Validates if a target angle falls within a circular arc sector."""
        angle = angle % 360
        if start_deg <= end_deg:
            return start_deg <= angle <= end_deg
        return angle >= start_deg or angle <= end_deg

    @classmethod
    def test_vehicle_vs_circle_obstacle(cls, car_pixel_vertices: list, circle_entry: dict) -> bool:
        """Runs geometric checks against solid pillars or partial ring boundaries."""
        cx = float(circle_entry.get('input_starting_x_qty', 0.0)) * 40.0
        cy = float(circle_entry.get('input_starting_y_qty', 0.0)) * 40.0
        outer_r = float(circle_entry.get('input_outer_radius_qty', 0.0)) * 40.0
        inner_r = float(circle_entry.get('input_inner_radius_qty', 0.0)) * 40.0
        start_deg = float(circle_entry.get('input_begin_degree_qty', 0.0))
        end_deg = float(circle_entry.get('input_end_degree_qty', 360.0))
        
        # Solid Full Pillars
        if inner_r == 0.0 and start_deg == 0.0 and end_deg == 360.0:
            return cls.check_polygon_vs_circle(car_pixel_vertices, (cx, cy), outer_r)

        # Ring Walls / Intersecting Curved Arcs
        for vx, vy in car_pixel_vertices:
            dx, dy = vx - cx, vy - cy
            dist = math.hypot(dx, dy)
            if inner_r <= dist <= outer_r:
                angle_deg = math.degrees(math.atan2(dy, dx)) % 360
                if cls.is_angle_in_arc(angle_deg, start_deg, end_deg):
                    return True
        return False
