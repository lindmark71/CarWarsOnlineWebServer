import ast
import os
import math
import base64
import re
from io import BytesIO
from PIL import Image, ImageDraw
from datetime import datetime
import sqlite3


class MapRenderer:

    def __init__(self):
        self.current_image   = None
        self.design_dict_list: list = []
        self.true_color_list: list  = []
        self.var_map_x_qty: float   = 1.0
        self.var_map_y_qty: float   = 1.0
        self.set_image_values()
        self.load_color_map()

    # ── Base Images ───────────────────────────────────────────────────────────

    def set_image_values(self):
        base_grid_pixel:  str = 'iVBORw0KGgoAAAANSUhEUgAAACkAAAApCAYAAACoYAD2AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFiUAABYlAUlSJPAAAACGSURBVFhH7ZAxCsAwDMT8/2/5YSlZOpTCafDggxN4CXIQrqo6BlOH0N3fp1+mvUQqqJdIBfUSqaBeIhXUeyPvwtbxuiSBfjrtJVJBvUQqqJdIBfW8Iu/C1vG6JIF+Ou0lUkG9RCqol0gF9bwi78LW8bokgX467SVSQb1EKqiXSAX1vCK3zwPkjq7CROX+0AAAAABJRU5ErkJggg=='
        dark_gray_grid:   str = 'iVBORw0KGgoAAAANSUhEUgAAACkAAAApCAYAAACoYAD2AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAACNSURBVFhH7ZAxDsAwCMR4ep6Wn7XK0iFFOg8MIN3gJTHIIiLiGUA8ay3J3vv3llHtOVJBPUcqqOdIBfUcqaDeF3kGujLrkvdHBl1a7TlSQT1HKqjnSAX1ZkWega7MuuT9kUGXVnuOVFDPkQrqOVJBvVmRZ6Arsy55f2TQpdWeIxXUc6SCeo5UUG9WZHdei94doLc52k8AAAAASUVORK5CYII='

        decoded_image_bytes = base64.b64decode(base_grid_pixel)
        self.base_image = Image.open(BytesIO(decoded_image_bytes))

        decoded_image_bytes = base64.b64decode(dark_gray_grid)
        self.dark_grey_image = Image.open(BytesIO(decoded_image_bytes))
        
        decoded_image_bytes = base64.b64decode(base_grid_pixel)
        self.base_image = Image.open(BytesIO(decoded_image_bytes)).convert('RGB')
        
    # ── Public Entry Points ───────────────────────────────────────────────────

    def render_from_file(self, path: str) -> Image.Image:
        """Load a map file and return the rendered PIL Image."""
        self.load_map(path)
        return self.current_image

    def render_from_string(self, content: str) -> Image.Image:
        """Load map content from a string and return the rendered PIL Image."""
        self._process_lines(content.splitlines(keepends=True))
        return self.current_image

    def get_car_image_from_db(self, image_name: str):
        """
        Look up a car image by name from the database.
        Returns a PIL Image or None if not found.
        """
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'carwars.db')
        try:
            conn = sqlite3.connect(db_path)
            row  = conn.execute(
                'SELECT base64_data FROM car_images WHERE name = ?',
                (image_name,)
            ).fetchone()
            conn.close()
            if row:
                decoded = base64.b64decode(row[0])
                return Image.open(BytesIO(decoded)).convert('RGBA')
        except Exception as e:
            print(f'Error loading car image "{image_name}" from DB: {e}')
        return None
    
    def get_starting_position_image_from_db(self, name: str):
        """
        Look up a starting position image by name from the database.
        Returns a PIL Image or None if not found.
        name is typically the color string — 'blue', 'red', etc.
        """
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'carwars.db')
        try:
            conn = sqlite3.connect(db_path)
            row  = conn.execute(
            '   SELECT base64_data FROM starting_position_images WHERE name = ?',
                (name,)
            ).fetchone()
            conn.close()
            if row:
                decoded = base64.b64decode(row[0])
                return Image.open(BytesIO(decoded)).convert('RGBA')
        except Exception as e:
            print(f'Error loading starting position image "{name}" from DB: {e}')
        return None

    # ── File Loading ──────────────────────────────────────────────────────────

    def load_map(self, path: str):
        with open(path, 'r', encoding='UTF-8') as f:
            lines = f.readlines()
        self._process_lines(lines)

    def _process_lines(self, lines: list):
        file_input_list: list = []
    
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            try:
                # Safely evaluate the entire python dictionary string in one pass
                entry_dict = ast.literal_eval(line)
            
                if isinstance(entry_dict, dict):
                    # Clean keys and values to stay uniform with your existing property loops
                    cleaned_dict = {}
                    for k, v in entry_dict.items():
                        # Strip whitespace from keys for structural compatibility
                        clean_key = str(k).replace(' ', '')
                        cleaned_dict[clean_key] = v
                
                    file_input_list.append(cleaned_dict)
                
            except Exception as e:
                print(f"[PARSER ERROR] Skipping unparseable row structure: {line}. Detail: {e}")
                continue

        # Pipe the completely verified object map array directly down to output engines
        self.output_map(file_input_list)

    # ── Map Output ────────────────────────────────────────────────────────────

    def output_map(self, input_list: list):
        if not input_list:
            self.var_map_x_qty = 1
            self.var_map_y_qty = 1
            self._resize_image()
            return

        object_list = ['Rect', 'Circle', 'Polygon', 'Text', 'FloorPaint',
                       'StartingPosition', 'Arc', 'Ramp', 'RaisedPlatform', 'CarPosition', 'ProposedCarPosition']

        for entry in input_list:
            object_found        = False
            object_type         = ''
            local_x_qty         = ''
            local_y_qty         = ''
            local_z_floor_qty   = ''
            local_z_ceiling_qty = ''
            local_starting_x    = ''
            local_starting_y    = ''
            local_orientation   = ''
            local_color         = ''
            local_outer_radius  = ''
            local_inner_radius  = ''
            local_begin_degree  = ''
            local_end_degree    = ''
            local_radius_qty    = ''
            local_tuples        = []
            local_text          = ''
            local_position_num  = 0
            local_ccw           = False
            local_car_image_name = None

            for k, v in entry.items():
                if k == 'map_size':
                    idx = v.index('X')
                    self.var_map_x_qty = int(v[:idx])
                    self.var_map_y_qty = int(v[idx + 1:])
                    self._resize_image()
                elif k in object_list:
                    object_found = True
                    object_type  = k
                elif k == 'local_x_qty':           local_x_qty        = v
                elif k == 'local_y_qty':           local_y_qty        = v
                elif k == 'local_z_floor_qty':     local_z_floor_qty  = v
                elif k == 'local_z_ceiling_qty':   local_z_ceiling_qty= v
                elif k == 'local_starting_x_qty':  local_starting_x   = v
                elif k == 'local_starting_y_qty':  local_starting_y   = v
                elif k == 'input_starting_x_qty':  local_starting_x   = v
                elif k == 'input_starting_y_qty':  local_starting_y   = v
                elif k == 'orientation':           local_orientation  = v
                elif k == 'color':                 local_color        = v
                elif k == 'input_outer_radius_qty':local_outer_radius = v
                elif k == 'input_inner_radius_qty':local_inner_radius = v
                elif k == 'input_begin_degree_qty':local_begin_degree = v
                elif k == 'input_end_degree_qty':  local_end_degree   = v
                elif k == 'local_radius_qty':      local_radius_qty   = v
                elif k == 'input_radius_qty':      local_radius_qty   = v
                elif k == 'list_of_tuples':        local_tuples       = v
                elif k == 'text_entry':            local_text         = v
                elif k == 'position_number':       local_position_num = v
                elif k == 'input_counter_clockwise': local_ccw        = v
                elif k == 'car_image_name':        local_car_image_name = v
            if not object_found:
                continue

            if object_type == 'Rect':
                self.create_rect(local_x_qty, local_y_qty,
                                 local_z_floor_qty, local_z_ceiling_qty,
                                 local_starting_x, local_starting_y, local_color)

            elif object_type == 'Circle':
                self.create_circle(local_outer_radius, local_inner_radius,
                                   local_begin_degree, local_end_degree,
                                   local_z_floor_qty, local_z_ceiling_qty,
                                   local_starting_x, local_starting_y, local_color)

            elif object_type == 'Polygon':
                self.create_polygon(local_tuples, local_color, expanded=True)

            elif object_type == 'Text':
                self.create_text(local_text, local_color,
                                 local_starting_x, local_starting_y)

            elif object_type == 'FloorPaint':
                self.create_floor_paint(local_color, local_starting_x, local_starting_y)

            elif object_type == 'StartingPosition':
                self.create_starting_position(local_color,
                                              local_starting_x,
                                              local_starting_y,
                                              local_orientation,
                                              int(local_position_num))
                

            elif object_type == 'Arc':
                self.create_arc(local_radius_qty, local_begin_degree, local_end_degree,
                                local_z_floor_qty, local_z_ceiling_qty,
                                local_starting_x, local_starting_y, local_ccw, local_color)

            elif object_type == 'Ramp':
                self.create_ramp(local_x_qty, local_y_qty,
                                 local_z_floor_qty, local_z_ceiling_qty,
                                 local_starting_x, local_starting_y,
                                 local_orientation, local_color)

            elif object_type == 'RaisedPlatform':
                self.create_raised_platform(local_x_qty, local_y_qty,
                                            local_starting_x, local_starting_y,
                                            local_z_floor_qty, local_z_ceiling_qty,
                                            local_color)
            elif object_type == 'CarPosition':
                self.create_car_position(local_color, local_starting_x,
                                        local_starting_y, local_orientation,
                                        entry.get('car_image_name', None), is_ghost=False)
            elif object_type == 'ProposedCarPosition':
                self.create_car_position(local_color, local_starting_x,
                                        local_starting_y, local_orientation,
                                        entry.get('car_image_name', None), is_ghost=True)

                
    # ── Drawing Methods ───────────────────────────────────────────────────────

    def create_rect(self, input_x_qty, input_y_qty,
                    input_z_floor_qty, input_z_ceiling_qty,
                    input_starting_x_qty, input_starting_y_qty, input_color):
        fill_color = self.color_match(input_color)
        top    = int(float(input_starting_y_qty) * 40)
        bottom = int(float(input_y_qty) * 40 + float(input_starting_y_qty) * 40 + 1)
        left   = int(float(input_starting_x_qty) * 40)
        right  = int(float(input_x_qty) * 40 + float(input_starting_x_qty) * 40 + 1)
        draw   = ImageDraw.Draw(self.current_image)
        draw.polygon([[left, top], [right, top], [right, bottom], [left, bottom]],
                     fill=fill_color, outline=fill_color)

    def create_circle(self, input_outer_radius_qty, input_inner_radius_qty,
                      input_begin_degree_qty, input_end_degree_qty,
                      input_z_floor_qty, input_z_ceiling_qty,
                      input_starting_x_qty, input_starting_y_qty, input_color):
        fill_color = self.color_match(input_color)
        pts = self._get_circle_points(
            float(input_outer_radius_qty), float(input_inner_radius_qty),
            float(input_begin_degree_qty), float(input_end_degree_qty),
            float(input_starting_x_qty),  float(input_starting_y_qty))
        draw = ImageDraw.Draw(self.current_image)
        draw.polygon(pts, fill=fill_color, outline=fill_color)

    def create_polygon(self, list_of_tuples, input_color, expanded=False):
        if isinstance(list_of_tuples, str):
            list_of_tuples = ast.literal_eval(list_of_tuples)
        fill_color = self.color_match(input_color)
        if not expanded:
            list_of_tuples = [(x * 40, y * 40) for x, y in list_of_tuples]
        draw = ImageDraw.Draw(self.current_image)
        draw.polygon(list_of_tuples, fill=fill_color, outline=fill_color)

    def create_text(self, text_entry, input_color, input_starting_x_qty, input_starting_y_qty):
        x = float(input_starting_x_qty)
        y = float(input_starting_y_qty)
        for char in str(text_entry).upper():
            if char == ' ':
                x += 1.0          # ← advance position for space, no drawing
                continue
            method = getattr(self, f'_draw_{char.lower()}', None)
            if method:
                method(x, y, input_color)
            if char != ' ' or method:
                x += 1.0

    def create_floor_paint(self, input_color, input_starting_x_qty, input_starting_y_qty):
        fill_color = input_color.lower()
        if fill_color == 'color':
            fill_color = 'black'
        top    = int(float(input_starting_y_qty) * 40 + 1)
        left   = int(float(input_starting_x_qty) * 40 + 1)
        bottom = int(float(input_starting_y_qty) * 40 + 9)
        right  = int(float(input_starting_x_qty) * 40 + 9)
        draw   = ImageDraw.Draw(self.current_image)
        draw.polygon([[left, top], [right, top], [right, bottom], [left, bottom]],
                     fill=fill_color, outline=fill_color)

    def create_starting_position(self, input_color: str,
                                       input_starting_x_qty: float,
                                       input_starting_y_qty: float,
                                       input_orientation: float,
                                       position_number: int):
        """
        Draw a starting position image on the map at the given
        coordinates and orientation. Looks up the image from the
        database by color name, falls back to a colored rectangle
        if not found.
        """
        starting_image = None

        # Try to load from database by color name
        if input_color:
            starting_image = self.get_starting_position_image_from_db(
                name=input_color
            )

        # Fallback — draw a simple colored rectangle placeholder
        if starting_image is None:
            fill_color     = self.color_match(input_color)
            starting_image = Image.new('RGBA', (21, 41), (255, 255, 255, 255))
            draw           = ImageDraw.Draw(starting_image)
            draw.rectangle([0, 0, 20, 40], outline='black')
            try:
                draw.rectangle([1, 1, 19, 39], fill=fill_color)
            except Exception:
                draw.rectangle([1, 1, 19, 39], fill='gray')

        # ── Convert starting position to pixels ───────────────────────────
        pixel_x_value = int(input_starting_x_qty * 40)
        pixel_y_value = int(input_starting_y_qty * 40)

        # ── Rotate to match orientation ───────────────────────────────────
        sp_rgba         = starting_image.convert('RGBA')
        sp_rgba_rotated = sp_rgba.rotate(-input_orientation,
                                          resample=Image.BICUBIC,
                                          expand=True)
        
        paste_position = (int(pixel_x_value),
                          int(pixel_y_value))                          

        # ── Paste onto map using alpha channel ────────────────────────────
        self.current_image.paste(sp_rgba_rotated,
                                 paste_position,
                                 mask=sp_rgba_rotated.split()[3])
        
    def create_arc(self, input_radius_qty, input_begin_degree_qty, input_end_degree_qty,
                   input_z_floor_qty, input_z_ceiling_qty,
                   input_starting_x_qty, input_starting_y_qty,
                   input_counter_clockwise, input_color):
        fill_color = self.color_match(input_color)
        pts = self._get_arc_points(
            float(input_radius_qty),
            float(input_begin_degree_qty), float(input_end_degree_qty),
            float(input_starting_x_qty),   float(input_starting_y_qty),
            bool(input_counter_clockwise))
        draw = ImageDraw.Draw(self.current_image)
        draw.polygon(pts, fill=None, outline=fill_color)

    def create_ramp(self, input_object_x_qty, input_object_y_qty,
                    input_z_floor_qty, input_z_ceiling_qty,
                    input_starting_x_qty, input_starting_y_qty,
                    input_orientation, input_color):
        fill_color = self.color_match(input_color)
        ox_qty  = float(input_object_x_qty)
        oy_qty  = float(input_object_y_qty)
        ori     = float(input_orientation)
        px      = float(input_starting_x_qty) * 40
        py      = float(input_starting_y_qty) * 40
        corners = [(px, py)]
        cx, cy  = px, py

        ang  = math.radians(ori + 90)
        cx  += ox_qty * 20 * round(math.sin(ang),3);  cy += ox_qty * 20 * round(math.cos(ang),3)
        ang  = math.radians(ori + 90)
        cx  += ox_qty * 20 * round(math.sin(ang),3);  cy += ox_qty * 20 * round(math.cos(ang),3)
        corners.append((cx, cy))

        ang  = math.radians(ori + 180)
        cx  += oy_qty * 20 * round(math.sin(ang),3);  cy += oy_qty * 20 * round(math.cos(ang),3)
        ang  = math.radians(ori + 180)
        cx  += oy_qty * 20 * round(math.sin(ang),3);  cy += oy_qty * 20 * round(math.cos(ang),3)
        corners.append((cx, cy))

        ang  = math.radians(ori + 270)
        cx  += ox_qty * 40 * round(math.sin(ang),3);  cy += ox_qty * 40 * round(math.cos(ang),3)
        corners.append((cx, cy))
        corners.append((px, py))

        draw = ImageDraw.Draw(self.current_image)
        draw.polygon(corners, fill=None, outline=fill_color)

    def create_raised_platform(self, input_object_x_qty, input_object_y_qty,
                               input_starting_x_qty, input_starting_y_qty,
                               input_z_floor_qty, input_z_ceiling_qty,
                               input_color):
        converted = self.dark_grey_image.convert('RGB')
        x_max = int(float(input_starting_x_qty) + float(input_object_x_qty))
        y_max = int(float(input_starting_y_qty) + float(input_object_y_qty))
        for xi in range(int(float(input_starting_x_qty)), x_max):
            for yi in range(int(float(input_starting_y_qty)), y_max):
                self.current_image.paste(converted,
                    box=[xi * 40, yi * 40, xi * 40 + 41, yi * 40 + 41])

    def create_car_position(self, input_color: str,
                            input_starting_x_qty: float,
                            input_starting_y_qty: float,
                            input_orientation: float,
                            car_image_name: str = None,
                            is_ghost: bool = False): # <-- Injected boolean anchor
        car_image = None
        if car_image_name:
            car_image = self.get_car_image_from_db(car_image_name)
        if car_image is None:
            fill_color = self.color_match(input_color)
            car_image = Image.new('RGBA', (21, 41), (255, 255, 255, 255))
            draw = ImageDraw.Draw(car_image)
            draw.rectangle ([0, 0, 20, 40], outline='black')
            try:
                draw.rectangle ([1, 1, 19, 39], fill=fill_color)
            except Exception:
                draw.rectangle ([1, 1, 19, 39], fill='gray')

        # Convert starting position to pixels
        pixel_x_value = int(input_starting_x_qty * 40)
        pixel_y_value = int(input_starting_y_qty * 40)

        # Rotate the car image to match orientation
        car_rgba = car_image.convert('RGBA')

        # ── GHOST OPACITY OPERATION ──
        if is_ghost:
            # Split into RGBA bands, apply 50% multiplier down to alpha stream
            r, g, b, a = car_rgba.split()
            ghost_alpha = a.point(lambda p: int(p * 0.45)) # 45% visible opacity ghost shadow
            car_rgba = Image.merge('RGBA', (r, g, b, ghost_alpha))

        car_rgba_rotated = car_rgba.rotate(-input_orientation, resample=Image.BICUBIC, expand=True)

        # Adjust paste position for expanded canvas
        orig_w, orig_h = car_rgba.size
        rot_w, rot_h = car_rgba_rotated.size
        offset_x = (rot_w - orig_w) // 2
        offset_y = (rot_h - orig_h) // 2
        paste_position = (pixel_x_value - offset_x, pixel_y_value - offset_y)

        # Paste onto map using modified alpha channel mask
        self.current_image.paste(car_rgba_rotated, paste_position, mask=car_rgba_rotated.split()[3])

        # Record in design dict tracking
        entry_dict: dict = {}
        entry_dict['CarPosition' if not is_ghost else 'ProposedCarPosition'] = 'CarPosition' if not is_ghost else 'ProposedCarPosition'
        entry_dict['local_starting_x_qty'] = input_starting_x_qty
        entry_dict['local_starting_y_qty'] = input_starting_y_qty
        entry_dict['current_speed'] = 0
        entry_dict['top_speed'] = 0
        entry_dict['heading'] = 0
        entry_dict['orientation'] = input_orientation
        if car_image_name:
            entry_dict['car_image_name'] = car_image_name
        self.design_dict_list.append(entry_dict)

    # ── Internal Geometry Helpers ─────────────────────────────────────────────

    def _get_circle_points(self, outer_r, inner_r, begin_deg, end_deg, sx, sy) -> list:
        if (begin_deg == 0.0 and end_deg == 0.0) or begin_deg > end_deg:
            end_deg += 360.0
        pts = []
        for d in range(int(begin_deg), int(end_deg) + 1):
            r = math.radians(d)
            pts.append(((sx + outer_r * round(math.sin(r),3)) * 40,
                        (sy + outer_r * round(math.cos(r),3)) * 40))
        for d in range(int(end_deg), int(begin_deg) - 1, -1):
            r = math.radians(d)
            pts.append(((sx + inner_r * round(math.sin(r),3)) * 40,
                        (sy + inner_r * round(math.cos(r),3)) * 40))
        return pts

    def _get_arc_points(self, radius, begin_deg, end_deg, sx, sy, ccw) -> list:
        if (begin_deg == 0.0 and end_deg == 0.0) or begin_deg > end_deg:
            end_deg += 360.0
        step = 1 if ccw else -1
        start = int(end_deg) if step == -1 else int(begin_deg)
        stop  = int(begin_deg) - 1 if step == -1 else int(end_deg) + 1
        pts   = []
        for d in range(start, stop, step):
            r = math.radians(d)
            pts.append(((sx + radius * round(math.sin(r),3)) * 40,
                        (sy + radius * round(math.cos(r),3)) * 40))
        return pts

    # ── Image Resize ──────────────────────────────────────────────────────────

    def _resize_image(self):
        bx, by    = self.base_image.size
        lx        = int(self.var_map_x_qty)
        ly        = int(self.var_map_y_qty)
        final_y   = (by - 1) * ly + 1
        final_x   = (bx - 1) * lx + 1
        col_strip = Image.new('RGB', (bx, final_y))
        for i in range(ly):
            col_strip.paste(self.base_image, (0, (by - 1) * i))
        final = Image.new('RGB', (final_x, final_y))
        for i in range(lx):
            final.paste(col_strip, ((bx - 1) * i, 0))
        self.current_image = final
        self.design_dict_list.clear()

    # ── Letter Drawing ────────────────────────────────────────────────────────
    # Each _draw_X method mirrors the draw_X method in map_designer.py
    # Only representative letters shown here for brevity — all 26 are included

    def _draw_polygon_letter(self, tuples, x, y, color):
        """Helper — offset a letter's tuples by (x, y) and draw."""
        shifted = [(x + dx, y + dy) for dx, dy in tuples]
        self.create_polygon(shifted, color)

    def _draw_a(self, x, y, color):
        pts = [
            (0.05, 0.775),(0.05, 0.925),(0.075, 0.95),(0.225, 0.95),(0.25, 0.925),
            (0.25, 0.775),(0.225, 0.75),(0.5, 0.25),(0.775, 0.75),(0.7, 0.625),
            (0.3, 0.625),(0.375, 0.5),(0.65, 0.5),(0.775, 0.75),(0.75, 0.775),
            (0.75, 0.925),(0.775, 0.95),(0.925, 0.95),(0.95, 0.925),(0.95, 0.775),
            (0.925, 0.75),(0.625, 0.075),(0.6, 0.05),(0.4, 0.05),(0.375, 0.075),(0.075, 0.75),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_b(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.85,0.95),(0.95,0.85),(0.95,0.625),
            (0.825,0.5),(0.95,0.375),(0.95,0.15),(0.85,0.05),(0.075,0.05),(0.075,0.075),
            (0.075,0.1),(0.1,0.1),(0.1,0.125),(0.125,0.125),(0.15,0.125),(0.15,0.15),
            (0.175,0.15),(0.175,0.175),(0.2,0.175),(0.2,0.2),(0.225,0.2),(0.225,0.225),
            (0.25,0.225),(0.25,0.25),(0.675,0.25),(0.75,0.325),(0.675,0.4),(0.25,0.4),
            (0.25,0.275),(0.25,0.75),(0.675,0.75),(0.75,0.675),(0.675,0.6),(0.25,0.6),
            (0.25,0.225),(0.225,0.225),(0.225,0.2),(0.2,0.2),(0.2,0.175),(0.175,0.175),
            (0.175,0.15),(0.15,0.15),(0.15,0.125),(0.125,0.125),(0.125,0.1),(0.1,0.1),
            (0.1,0.075),(0.075,0.075),(0.05,0.075),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_c(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.8),
            (0.925,0.775),(0.25,0.775),(0.225,0.75),(0.225,0.25),(0.25,0.225),(0.925,0.225),
            (0.95,0.2),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_d(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.85,0.95),(0.95,0.85),(0.95,0.15),
            (0.85,0.05),(0.075,0.05),(0.075,0.075),(0.1,0.075),(0.1,0.1),(0.125,0.1),
            (0.125,0.125),(0.15,0.125),(0.15,0.15),(0.175,0.15),(0.175,0.175),(0.2,0.175),
            (0.2,0.2),(0.225,0.2),(0.225,0.225),(0.25,0.225),(0.25,0.25),(0.25,0.725),
            (0.625,0.75),(0.75,0.625),(0.75,0.375),(0.625,0.25),(0.25,0.25),(0.25,0.225),
            (0.225,0.225),(0.225,0.2),(0.2,0.2),(0.2,0.175),(0.175,0.175),(0.175,0.15),
            (0.15,0.15),(0.15,0.125),(0.125,0.125),(0.125,0.1),(0.1,0.1),(0.1,0.075),
            (0.075,0.075),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_e(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.775),
            (0.925,0.75),(0.275,0.75),(0.25,0.725),(0.25,0.625),(0.275,0.6),(0.725,0.6),
            (0.75,0.575),(0.75,0.425),(0.725,0.4),(0.275,0.4),(0.25,0.375),(0.25,0.275),
            (0.275,0.25),(0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_f(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.95),(0.25,0.925),(0.25,0.625),
            (0.275,0.6),(0.725,0.6),(0.75,0.575),(0.75,0.425),(0.725,0.4),(0.275,0.4),
            (0.25,0.375),(0.25,0.275),(0.275,0.25),(0.925,0.25),(0.95,0.225),(0.95,0.075),
            (0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_g(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.525),
            (0.925,0.5),(0.525,0.5),(0.5,0.525),(0.5,0.6),(0.525,0.625),(0.725,0.625),
            (0.75,0.65),(0.75,0.725),(0.725,0.75),(0.275,0.75),(0.25,0.725),(0.25,0.275),
            (0.275,0.25),(0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_h(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.2,0.95),(0.225,0.925),(0.225,0.625),
            (0.25,0.6),(0.75,0.6),(0.775,0.625),(0.775,0.925),(0.8,0.95),(0.925,0.95),
            (0.95,0.925),(0.95,0.075),(0.925,0.05),(0.8,0.05),(0.775,0.075),(0.775,0.375),
            (0.75,0.4),(0.25,0.4),(0.225,0.375),(0.225,0.075),(0.2,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_i(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.2),(0.075,0.225),(0.375,0.225),(0.4,0.25),(0.4,0.75),
            (0.375,0.775),(0.075,0.775),(0.05,0.8),(0.05,0.925),(0.075,0.95),(0.925,0.95),
            (0.95,0.925),(0.95,0.8),(0.925,0.77),(0.625,0.77),(0.6,0.75),(0.6,0.25),
            (0.625,0.225),(0.925,0.225),(0.95,0.2),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_j(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.075,0.25),(0.475,0.25),(0.5,0.275),(0.5,0.725),
            (0.475,0.75),(0.275,0.75),(0.25,0.725),(0.25,0.525),(0.075,0.5),(0.05,0.525),
            (0.05,0.925),(0.075,0.95),(0.725,0.95),(0.75,0.925),(0.75,0.275),(0.775,0.25),
            (0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_k(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.95),(0.25,0.925),(0.25,0.65),
            (0.275,0.625),(0.45,0.625),(0.775,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.775),
            (0.675,0.5),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.775,0.05),(0.45,0.375),
            (0.275,0.375),(0.25,0.35),(0.25,0.075),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_l(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.775),
            (0.925,0.75),(0.275,0.75),(0.25,0.725),(0.25,0.075),(0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_m(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.95),(0.25,0.925),(0.25,0.375),
            (0.275,0.35),(0.5,0.575),(0.725,0.35),(0.75,0.375),(0.75,0.925),(0.775,0.95),
            (0.925,0.95),(0.95,0.925),(0.95,0.075),(0.925,0.05),(0.775,0.05),(0.475,0.325),
            (0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_n(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.95),(0.25,0.925),(0.25,0.475),
            (0.275,0.45),(0.775,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.075),(0.925,0.05),
            (0.775,0.05),(0.75,0.075),(0.75,0.525),(0.725,0.55),(0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_o(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.075),
            (0.925,0.05),(0.25,0.05),(0.25,0.725),(0.275,0.75),(0.725,0.75),(0.75,0.725),
            (0.75,0.275),(0.725,0.25),(0.25,0.25),(0.25,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_p(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.95),(0.25,0.275),(0.275,0.25),
            (0.725,0.25),(0.75,0.375),(0.625,0.5),(0.25,0.5),(0.25,0.625),(0.75,0.625),
            (0.95,0.425),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_q(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.625,0.95),(0.725,0.85),(0.825,0.95),
            (0.95,0.825),(0.85,0.725),(0.95,0.625),(0.95,0.075),(0.925,0.05),(0.25,0.05),
            (0.25,0.725),(0.275,0.75),(0.625,0.75),(0.55,0.675),(0.675,0.55),(0.75,0.625),
            (0.75,0.275),(0.725,0.25),(0.25,0.25),(0.25,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_r(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.225,0.925),(0.25,0.925),(0.25,0.275),
            (0.275,0.25),(0.725,0.25),(0.75,0.275),(0.75,0.375),(0.625,0.5),(0.25,0.475),
            (0.25,0.625),(0.45,0.625),(0.775,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.775),
            (0.775,0.6),(0.95,0.425),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_s(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.425),(0.25,0.625),(0.725,0.625),(0.75,0.65),(0.75,0.725),
            (0.725,0.75),(0.075,0.75),(0.05,0.775),(0.05,0.925),(0.075,0.95),(0.925,0.95),
            (0.95,0.925),(0.95,0.575),(0.75,0.4),(0.275,0.375),(0.25,0.35),(0.25,0.275),
            (0.275,0.25),(0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_t(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.2),(0.075,0.225),(0.375,0.225),(0.4,0.25),(0.4,0.925),
            (0.425,0.95),(0.575,0.95),(0.6,0.925),(0.6,0.25),(0.625,0.225),(0.925,0.225),
            (0.95,0.2),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_u(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.075),
            (0.925,0.05),(0.8,0.05),(0.775,0.075),(0.775,0.75),(0.75,0.75),(0.25,0.775),
            (0.225,0.75),(0.225,0.075),(0.2,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_v(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.075,0.25),(0.375,0.925),(0.4,0.95),(0.6,0.95),
            (0.625,0.925),(0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.775,0.05),
            (0.75,0.075),(0.5,0.675),(0.25,0.075),(0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_w(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.075,0.25),(0.25,0.925),(0.275,0.95),(0.375,0.95),
            (0.4,0.925),(0.5,0.5),(0.6,0.925),(0.625,0.95),(0.725,0.95),(0.75,0.925),
            (0.925,0.25),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.775,0.05),(0.75,0.075),
            (0.65,0.5),(0.575,0.075),(0.55,0.05),(0.45,0.05),(0.425,0.075),(0.35,0.5),
            (0.25,0.075),(0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_x(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.325,0.5),(0.05,0.775),(0.05,0.925),(0.075,0.95),
            (0.225,0.95),(0.5,0.675),(0.775,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.8),
            (0.65,0.5),(0.95,0.2),(0.95,0.075),(0.925,0.05),(0.775,0.05),(0.5,0.325),
            (0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_y(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.375,0.55),(0.375,0.925),(0.4,0.95),(0.6,0.95),
            (0.625,0.925),(0.625,0.55),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.775,0.05),
            (0.5,0.325),(0.225,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    def _draw_z(self, x, y, color):
        pts = [
            (0.05,0.075),(0.05,0.225),(0.075,0.25),(0.525,0.25),(0.55,0.275),(0.05,0.775),
            (0.05,0.925),(0.075,0.95),(0.925,0.95),(0.95,0.925),(0.95,0.775),(0.925,0.75),
            (0.425,0.75),(0.95,0.225),(0.95,0.075),(0.925,0.05),(0.075,0.05),
        ]
        self._draw_polygon_letter(pts, x, y, color)

    # ── Color Matching ────────────────────────────────────────────────────────

    def color_match(self, input_color: str) -> str:
        find = str(input_color).lower().replace(' ', '')
        return find if find in self.true_color_list else 'black'

    def load_color_map(self):
        colors = [
            'aliceblue','antiquewhite','aqua','aquamarine','azure','beige','bisque',
            'black','blanchedalmond','blue','blueviolet','brown','burlywood','cadetblue',
            'chartreuse','chocolate','coral','cornflowerblue','cornsilk','crimson','cyan',
            'darkblue','darkcyan','darkgoldenrod','darkgray','darkgrey','darkgreen',
            'darkkhaki','darkmagenta','darkolivegreen','darkorange','darkorchid','darkred',
            'darksalmon','darkseagreen','darkslateblue','darkslategray','darkslategrey',
            'darkturquoise','darkviolet','deeppink','deepskyblue','dimgray','dimgrey',
            'dodgerblue','firebrick','floralwhite','forestgreen','fuchsia','gainsboro',
            'ghostwhite','gold','goldenrod','gray','grey','green','greenyellow','honeydew',
            'hotpink','indianred','indigo','ivory','khaki','lavender','lavenderblush',
            'lawngreen','lemonchiffon','lightblue','lightcoral','lightcyan',
            'lightgoldenrodyellow','lightgreen','lightgray','lightgrey','lightpink',
            'lightsalmon','lightseagreen','lightskyblue','lightslategray','lightslategrey',
            'lightsteelblue','lightyellow','lime','limegreen','linen','magenta','maroon',
            'mediumaquamarine','mediumblue','mediumorchid','mediumpurple','mediumseagreen',
            'mediumslateblue','mediumspringgreen','mediumturquoise','mediumvioletred',
            'midnightblue','mintcream','mistyrose','moccasin','navajowhite','navy',
            'oldlace','olive','olivedrab','orange','orangered','orchid','palegoldenrod',
            'palegreen','paleturquoise','palevioletred','papayawhip','peachpuff','peru',
            'pink','plum','powderblue','purple','rebeccapurple','red','rosybrown',
            'royalblue','saddlebrown','salmon','sandybrown','seagreen','seashell','sienna',
            'silver','skyblue','slateblue','slategray','slategrey','snow','springgreen',
            'steelblue','tan','teal','thistle','tomato','turquoise','violet','wheat',
            'white','whitesmoke','yellow','yellowgreen',
        ]
        self.true_color_list = colors

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _convert_for_number_type(self, value):
        try:
            return float(value)
        except Exception:
            return value


