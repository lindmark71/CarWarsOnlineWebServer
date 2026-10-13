"""
Static-obstacle collision detection for Car Wars Online.

Everything is done in PIXELS (40 px per grid unit), matching map_renderer.py.
Works for concave shapes (annular sectors, crescent polygons) -- it does NOT use SAT.
"""
import math

GRID = 40.0
CAR_W, CAR_L = 21.0, 41.0            # sprite size in px

# Entry types that are solid, stationary obstacles. Everything else (Text, FloorPaint,
# StartingPosition, Ramp, RaisedPlatform, cars, dropped weapons, queues) is ignored.
SOLID_TYPES = ('Rect', 'Circle', 'Polygon', 'Arc')

# The 21x41 sprite is 1px taller than a 40px grid cell, so a car sitting in the last row/column
# overhangs the map by 1px. Only count the map edge as hit beyond this many px.
EDGE_TOLERANCE = 2.0


# ── Car footprint ─────────────────────────────────────────────────────────────
def car_footprint(x_qty, y_qty, orientation_deg):
    """Car corners in px. x/y use the committed CarPosition convention
    (top-left of the unrotated 21x41 box); orientation is compass-style (0 = north, clockwise)."""
    cx, cy = x_qty * GRID + CAR_W / 2, y_qty * GRID + CAR_L / 2
    a = math.radians(orientation_deg)
    fx, fy = math.sin(a), -math.cos(a)          # forward
    rx, ry = math.cos(a), math.sin(a)           # right
    hl, hw = CAR_L / 2, CAR_W / 2
    return [(cx + sl * hl * fx + sw * hw * rx, cy + sl * hl * fy + sw * hw * ry)
            for sl, sw in ((1, -1), (1, 1), (-1, 1), (-1, -1))]


# ── Primitive tests ───────────────────────────────────────────────────────────
def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])

def _edges_cross(p1, p2, q1, q2):
    return (_ccw(q1, q2, p1) * _ccw(q1, q2, p2) < 0 and
            _ccw(p1, p2, q1) * _ccw(p1, p2, q2) < 0)

def _point_in_poly(pt, poly):
    x, y, inside = pt[0], pt[1], False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside

def _bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def _bbox_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

def polygons_overlap(a, b):
    """True if two simple polygons (convex OR concave) share area."""
    if not _bbox_overlap(_bbox(a), _bbox(b)):
        return False
    for i in range(len(a)):
        a1, a2 = a[i], a[(i + 1) % len(a)]
        for j in range(len(b)):
            if _edges_cross(a1, a2, b[j], b[(j + 1) % len(b)]):
                return True
    return _point_in_poly(a[0], b) or _point_in_poly(b[0], a)

def _dist_point_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

def quad_hits_disc(quad, center, r):
    if _point_in_poly(center, quad):
        return True
    return any(_dist_point_seg(center, quad[i], quad[(i + 1) % 4]) < r for i in range(4))

def quad_hits_polyline(quad, pts):
    """An Arc is an outline only (a thin curved wall)."""
    for i in range(len(pts) - 1):
        if _point_in_poly(pts[i], quad):
            return True
        for j in range(4):
            if _edges_cross(pts[i], pts[i + 1], quad[j], quad[(j + 1) % 4]):
                return True
    return len(pts) > 0 and _point_in_poly(pts[-1], quad)


# ── Shape builders (formulas copied from MapRenderer so collisions match the picture) ──
def _norm(entry):
    return {str(k).replace(' ', ''): v for k, v in entry.items()}

def _sx_sy(e):
    sx = e.get('input_starting_x_qty', e.get('local_starting_x_qty', 0.0))
    sy = e.get('input_starting_y_qty', e.get('local_starting_y_qty', 0.0))
    return float(sx), float(sy)

def rect_vertices(e):
    sx, sy = _sx_sy(e)
    w, h = float(e['local_x_qty']), float(e['local_y_qty'])
    return [(sx * GRID, sy * GRID), ((sx + w) * GRID, sy * GRID),
            ((sx + w) * GRID, (sy + h) * GRID), (sx * GRID, (sy + h) * GRID)]

def circle_polygon(e):
    """Annular sector / pie slice as a polygon; same sampling as MapRenderer._get_circle_points."""
    sx, sy = _sx_sy(e)
    outer = float(e['input_outer_radius_qty']); inner = float(e.get('input_inner_radius_qty', 0.0))
    b, en = float(e.get('input_begin_degree_qty', 0.0)), float(e.get('input_end_degree_qty', 360.0))
    if (b == 0.0 and en == 0.0) or b > en:
        en += 360.0
    pts = []
    for d in range(int(b), int(en) + 1):
        r = math.radians(d)
        pts.append(((sx + outer * round(math.sin(r), 3)) * GRID, (sy + outer * round(math.cos(r), 3)) * GRID))
    for d in range(int(en), int(b) - 1, -1):
        r = math.radians(d)
        pts.append(((sx + inner * round(math.sin(r), 3)) * GRID, (sy + inner * round(math.cos(r), 3)) * GRID))
    return pts

def arc_points(e):
    """Same sampling as MapRenderer._get_arc_points (an open polyline)."""
    sx, sy = _sx_sy(e)
    radius = float(e.get('input_radius_qty', e.get('local_radius_qty', 0.0)))
    b, en = float(e.get('input_begin_degree_qty', 0.0)), float(e.get('input_end_degree_qty', 0.0))
    ccw = bool(e.get('input_counter_clockwise', False))
    if (b == 0.0 and en == 0.0) or b > en:
        en += 360.0
    step = 1 if ccw else -1
    start = int(en) if step == -1 else int(b)
    stop = int(b) - 1 if step == -1 else int(en) + 1
    return [((sx + radius * round(math.sin(math.radians(d)), 3)) * GRID,
             (sy + radius * round(math.cos(math.radians(d)), 3)) * GRID)
            for d in range(start, stop, step)]

def polygon_vertices(e):
    pts = e['list_of_tuples']
    if isinstance(pts, str):
        import ast
        pts = ast.literal_eval(pts)
    return [(float(x), float(y)) for x, y in pts]       # already in px


# ── Public API ────────────────────────────────────────────────────────────────
def map_bounds_px(records):
    """(width_px, height_px) from the map_size entry, or None if there isn't one."""
    for r in records:
        if isinstance(r, dict) and 'map_size' in r:
            w, h = str(r['map_size']).upper().split('X')
            return int(w) * GRID, int(h) * GRID
    return None

def find_wall_collisions(quad, records):
    """Returns a list of {'type', 'index'} for every solid stationary obstacle the
    car quad overlaps, plus {'type': 'MapEdge'} if any corner is off the map.
    `index` is the entry's position in `records`, so it can be traced back to the file."""
    hits = []
    bounds = map_bounds_px(records)
    t = EDGE_TOLERANCE
    if bounds and any(x < -t or y < -t or x > bounds[0] + t or y > bounds[1] + t for x, y in quad):
        hits.append({'type': 'MapEdge', 'index': None})

    for idx, raw in enumerate(records):
        if not isinstance(raw, dict):
            continue
        e = _norm(raw)
        kind = next((t for t in SOLID_TYPES if e.get(t) == t), None)
        if kind is None:
            continue
        try:
            if kind == 'Rect':
                hit = polygons_overlap(quad, rect_vertices(e))
            elif kind == 'Polygon':
                hit = polygons_overlap(quad, polygon_vertices(e))
            elif kind == 'Circle':
                full = (float(e.get('input_inner_radius_qty', 0.0)) == 0.0 and
                        float(e.get('input_end_degree_qty', 360.0)) -
                        float(e.get('input_begin_degree_qty', 0.0)) >= 360.0)
                if full:                                    # a solid disc (pillar / drum)
                    sx, sy = _sx_sy(e)
                    hit = quad_hits_disc(quad, (sx * GRID, sy * GRID),
                                         float(e['input_outer_radius_qty']) * GRID)
                else:                                       # curved wall segment
                    hit = polygons_overlap(quad, circle_polygon(e))
            else:  # Arc
                hit = quad_hits_polyline(quad, arc_points(e))
        except Exception as err:
            print(f'[COLLISION] skipped malformed {kind} at index {idx}: {err}')
            continue
        if hit:
            hits.append({'type': kind, 'index': idx})
    return hits
