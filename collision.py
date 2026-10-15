"""
Static-obstacle collision detection for Car Wars Online.

Everything is done in PIXELS (40 px per grid unit), matching map_renderer.py.
Works for concave shapes (annular sectors, crescent polygons) -- it does NOT use SAT.
"""
import math
import re

GRID = 40.0
CAR_W, CAR_L = 21.0, 41.0            # sprite size in px

# Entry types that are solid, stationary obstacles. Everything else (Text, FloorPaint,
# StartingPosition, Ramp, RaisedPlatform, cars, dropped weapons, queues) is ignored.
SOLID_TYPES = ('Rect', 'Circle', 'Polygon', 'Arc')

# The 21x41 sprite is 1px taller than a 40px grid cell, so a car sitting in the last row/column
# overhangs the map by 1px. Only count the map edge as hit beyond this many px.
EDGE_TOLERANCE = 2.0


# ── Car footprint ─────────────────────────────────────────────────────────────
def footprint_from_center(cx, cy, orientation_deg):
    """Car corners in px for a car centered at (cx, cy); compass heading (0 = north, clockwise)."""
    a = math.radians(orientation_deg)
    fx, fy = math.sin(a), -math.cos(a)          # forward
    rx, ry = math.cos(a), math.sin(a)           # right
    hl, hw = CAR_L / 2, CAR_W / 2
    return [(cx + sl * hl * fx + sw * hw * rx, cy + sl * hl * fy + sw * hw * ry)
            for sl, sw in ((1, -1), (1, 1), (-1, 1), (-1, -1))]

def car_footprint(x_qty, y_qty, orientation_deg):
    """Car corners in px. x/y use the committed CarPosition convention
    (top-left of the unrotated 21x41 box)."""
    return footprint_from_center(x_qty * GRID + CAR_W / 2, y_qty * GRID + CAR_L / 2, orientation_deg)


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

def _dist_point_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

def _inside_strict(pt, poly, eps=1e-6):
    """Inside the polygon, and NOT merely sitting on its outline -- touching is not overlapping."""
    if not _point_in_poly(pt, poly):
        return False
    n = len(poly)
    return all(_dist_point_seg(pt, poly[i], poly[(i + 1) % n]) > eps for i in range(n))

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
    return any(_inside_strict(p, b) for p in a) or _inside_strict(b[0], a)

def quad_hits_polyline(quad, pts):
    """An Arc is an outline only (a thin curved wall)."""
    for i in range(len(pts) - 1):
        if _inside_strict(pts[i], quad):
            return True
        for j in range(4):
            if _edges_cross(pts[i], pts[i + 1], quad[j], quad[(j + 1) % 4]):
                return True
    return len(pts) > 0 and _inside_strict(pts[-1], quad)


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

def build_obstacles(records):
    """Pre-computes every solid stationary shape once, so a move can be probed many times cheaply."""
    shapes = []
    for idx, raw in enumerate(records):
        if not isinstance(raw, dict):
            continue
        e = _norm(raw)
        kind = next((t for t in SOLID_TYPES if e.get(t) == t), None)
        if kind is None:
            continue
        try:
            if kind == 'Rect':
                shape = ('poly', rect_vertices(e))
            elif kind == 'Polygon':
                shape = ('poly', polygon_vertices(e))
            elif kind == 'Circle':
                full = (float(e.get('input_inner_radius_qty', 0.0)) == 0.0 and
                        float(e.get('input_end_degree_qty', 360.0)) -
                        float(e.get('input_begin_degree_qty', 0.0)) >= 360.0)
                if full:                      # solid disc: outer ring only, same sampling the renderer draws
                    sx, sy = _sx_sy(e)
                    outer = float(e['input_outer_radius_qty'])
                    shape = ('poly', [((sx + outer * round(math.sin(math.radians(d)), 3)) * GRID,
                                       (sy + outer * round(math.cos(math.radians(d)), 3)) * GRID)
                                      for d in range(0, 360)])
                else:
                    shape = ('poly', circle_polygon(e))
            else:
                shape = ('line', arc_points(e))
            shapes.append({'type': kind, 'index': idx, 'kind': shape[0], 'data': shape[1],
                           'bbox': _bbox(shape[1])})
        except Exception as err:
            print(f'[COLLISION] skipped malformed {kind} at index {idx}: {err}')
    return {'shapes': shapes, 'bounds': map_bounds_px(records)}

def collisions_with(quad, obstacles):
    """Every solid obstacle the car quad overlaps, plus {'type': 'MapEdge'} if it is off the map."""
    hits = []
    b, t = obstacles['bounds'], EDGE_TOLERANCE
    if b and any(x < -t or y < -t or x > b[0] + t or y > b[1] + t for x, y in quad):
        hits.append({'type': 'MapEdge', 'index': None})
    qbox = _bbox(quad)
    for s in obstacles['shapes']:
        if not _bbox_overlap(qbox, s['bbox']):
            continue
        hit = (polygons_overlap(quad, s['data']) if s['kind'] == 'poly'
               else quad_hits_polyline(quad, s['data']))
        if hit:
            hits.append({'type': s['type'], 'index': s['index']})
    return hits

def find_wall_collisions(quad, records):
    """Returns [{'type', 'index'}, ...] for every solid stationary obstacle the car quad overlaps
    (plus MapEdge). `index` is the entry's position in `records`."""
    return collisions_with(quad, build_obstacles(records))


# ── Movement paths ────────────────────────────────────────────────────────────
HALF_W, HALF_H = CAR_W / 2, CAR_L / 2
SLIDE_SHARE = 0.5     # bends: first half of the move slides forward one car length,
                      # second half swings about the inner rear corner (same as the commit math)

def parse_maneuver(maneuver):
    """-> (step_px, turn_deg).  turn_deg is 0 for STR/HALF, + for right bends, - for left bends."""
    m = (maneuver or 'STR').strip().upper()
    if m == 'STR':
        return 40.0, 0.0
    if m == 'HALF':
        return 20.0, 0.0
    mm = re.fullmatch(r'D(\d+)([LR])', m)
    if mm:
        deg = int(mm.group(1)) * 15.0
        return 40.0, (-deg if mm.group(2) == 'L' else deg)
    return 0.0, 0.0

def pose_at(cx0, cy0, h0, step, turn, t, round_heading=True):
    """(cx, cy, heading) at fraction t (0..1) of a maneuver that starts at center (cx0, cy0), heading h0."""
    a0 = math.radians(h0)
    fx, fy = math.sin(a0), -math.cos(a0)
    rx, ry = math.cos(a0), math.sin(a0)
    if turn == 0:
        return cx0 + t * step * fx, cy0 + t * step * fy, h0
    s = min(t / SLIDE_SHARE, 1.0)
    if t <= SLIDE_SHARE:
        return cx0 + s * step * fx, cy0 + s * step * fy, h0
    frac = (t - SLIDE_SHARE) / (1.0 - SLIDE_SHARE)
    cxs, cys = cx0 + step * fx, cy0 + step * fy                 # fully slid car
    side = 1.0 if turn > 0 else -1.0
    px = cxs - HALF_H * fx + side * HALF_W * rx                 # rear corner on the inside of the turn
    py = cys - HALF_H * fy + side * HALF_W * ry
    phi = math.radians(turn * frac)
    dx, dy = cxs - px, cys - py
    cx = px + dx * math.cos(phi) - dy * math.sin(phi)
    cy = py + dx * math.sin(phi) + dy * math.cos(phi)
    h = h0 + turn * frac
    return cx, cy, (round(h) if round_heading else h)


# ── Conforming ────────────────────────────────────────────────────────────────
def _segment_intersection(p1, p2, q1, q2):
    d1 = (p2[0] - p1[0], p2[1] - p1[1]); d2 = (q2[0] - q1[0], q2[1] - q1[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if den == 0:
        return None
    t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])

def _obstacle_segments(obstacles, hits):
    segs = []
    for h in hits:
        if h['type'] == 'MapEdge':
            w, ht = obstacles['bounds']
            c = [(0, 0), (w, 0), (w, ht), (0, ht)]
            segs += [(c[i], c[(i + 1) % 4]) for i in range(4)]
            continue
        s = next(s for s in obstacles['shapes'] if s['index'] == h['index'])
        pts, closed = s['data'], s['kind'] == 'poly'
        n = len(pts)
        segs += [(pts[i], pts[(i + 1) % n]) for i in range(n if closed else n - 1)]
    return segs

def _contact(quad, segs):
    """Obstacle edges that cross the car outline, and the points where they cross."""
    edges, points = [], []
    for a, b in segs:
        crossed = False
        for j in range(4):
            q1, q2 = quad[j], quad[(j + 1) % 4]
            if _edges_cross(a, b, q1, q2):
                pt = _segment_intersection(a, b, q1, q2)
                if pt:
                    points.append(pt)
                crossed = True
        if crossed:
            edges.append((a, b))
    return edges, points

def _travel_direction(pose, t_hit, point, dt=0.01):
    """Unit direction the contact point (a fixed point on the car body) is moving at t_hit."""
    cx, cy, h = pose(t_hit, False)
    a = math.radians(h)
    u = (point[0] - cx) * math.sin(a) + (point[1] - cy) * -math.cos(a)      # along the car
    v = (point[0] - cx) * math.cos(a) + (point[1] - cy) * math.sin(a)       # across the car
    def where(t):
        c2x, c2y, h2 = pose(t, False)
        a2 = math.radians(h2)
        return (c2x + u * math.sin(a2) + v * math.cos(a2), c2y - u * math.cos(a2) + v * math.sin(a2))
    p0, p1 = where(max(0.0, t_hit - dt)), where(min(1.0, t_hit + dt))
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else None

def _angle_to_wall(d, a, b):
    """Angle (0-90 deg) between the direction of travel and a wall edge. 90 = square on."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    n = math.hypot(ex, ey)
    if n == 0:
        return None
    return math.degrees(math.acos(min(1.0, abs(d[0] * ex + d[1] * ey) / n)))


SIDESWIPE_PIVOT = 'wall'    # which rear corner the car swings about: 'wall' = the rear corner on the side that
                            # hit; 'far' = the other one. The difference is a fraction of a pixel.

def _rotate_about(cx, cy, px, py, deg):
    """Rotate (cx, cy) about (px, py); positive degrees = clockwise on screen, like a heading increase."""
    phi = math.radians(deg)
    dx, dy = cx - px, cy - py
    return (px + dx * math.cos(phi) - dy * math.sin(phi),
            py + dx * math.sin(phi) + dy * math.cos(phi))

def resolve_move(records, x_qty, y_qty, orientation, maneuver,
                 samples=24, iterations=16, head_on_min_deg=45.0):
    """Plays a maneuver against the map's solid objects.

    x_qty / y_qty / orientation: the car's CarPosition before the move.
    Returns a dict:
      collided, conformed, head_on, angle   what happened (angle: 90 = square on, None if no hit)
      stop_fraction                         how much of the move was completed (1.0 = all of it)
      end / full_end                        where the car ends up / would have ended with no obstacle
                                            ({'x','y'} in CarPosition grid units, 'orientation' in degrees)
      hits, note
    Head-on hits (angle >= head_on_min_deg) conform: the car stops flush against the object.
    Sideswipes (angle < head_on_min_deg) complete the whole move, then the car swings about its rear
    corner, away from the object, by the smallest rotation that leaves it clear (just touching).
    Extra keys: sideswipe (bool), rotation (whole degrees the heading changed, + = clockwise).
    """
    step, turn = parse_maneuver(maneuver)
    cx0, cy0 = x_qty * GRID + HALF_W, y_qty * GRID + HALF_H
    pose = lambda t, rnd=True: pose_at(cx0, cy0, float(orientation), step, turn, t, rnd)
    quad = lambda t: footprint_from_center(*pose(t))
    as_xy = lambda p: {'x': (p[0] - HALF_W) / GRID, 'y': (p[1] - HALF_H) / GRID, 'orientation': p[2] % 360}

    obstacles = build_obstacles(records)
    full_end = as_xy(pose(1.0))
    out = {'collided': False, 'conformed': False, 'head_on': None, 'angle': None, 'stop_fraction': 1.0,
           'end': full_end, 'full_end': full_end, 'hits': [], 'note': '', 'sideswipe': False, 'rotation': 0}

    start_hits = collisions_with(quad(0.0), obstacles)
    if start_hits:                                        # already overlapping: nothing sensible to conform to
        out.update(collided=True, hits=start_hits, note='overlap_at_start')
        return out

    lo = hi = None
    prev = 0.0
    for i in range(1, samples + 1):                       # first overlapping sample along the path
        t = i / samples
        hits = collisions_with(quad(t), obstacles)
        if hits:
            lo, hi, hi_hits = prev, t, hits
            break
        prev = t
    if hi is None:
        return out                                        # whole path is clear

    for _ in range(iterations):                           # refine: lo = last clear, hi = first overlap
        mid = (lo + hi) / 2
        h = collisions_with(quad(mid), obstacles)
        if h:
            hi, hi_hits = mid, h
        else:
            lo = mid

    edges, points = _contact(quad(hi), _obstacle_segments(obstacles, hi_hits))
    angle = None
    pt = None
    if edges and points:
        pt = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        d = _travel_direction(pose, hi, pt)
        if d:
            angles = [a for a in (_angle_to_wall(d, *e) for e in edges) if a is not None]
            angle = max(angles) if angles else None       # the most square-on surface decides

    head_on = True if angle is None else angle >= head_on_min_deg
    out.update(collided=True, head_on=head_on, angle=None if angle is None else round(angle, 1),
               hits=hi_hits, stop_fraction=round(lo, 6))
    if angle is None:
        out['note'] = 'no_contact_edge'
    if head_on:
        out.update(conformed=True, end=as_xy(pose(lo)))
        return out

    # ── Sideswipe: finish the whole move, then swing off the rear corner, away from the wall ──
    out['stop_fraction'] = 1.0
    if not collisions_with(quad(1.0), obstacles):          # brushed something en route; the end pose is clear
        out['note'] = 'glancing: brushed an obstacle en route, end pose is clear'
        return out

    cxh, cyh, hh = pose(hi, False)
    side = 1.0 if ((pt[0] - cxh) * math.cos(math.radians(hh)) + (pt[1] - cyh) * math.sin(math.radians(hh))) > 0 else -1.0
    c1x, c1y, h1 = pose(1.0)                               # where the full move would leave the car
    a1 = math.radians(h1)
    fx, fy, rx, ry = math.sin(a1), -math.cos(a1), math.cos(a1), math.sin(a1)
    pside = side if SIDESWIPE_PIVOT == 'wall' else -side
    pvx, pvy = c1x - HALF_H * fx + pside * HALF_W * rx, c1y - HALF_H * fy + pside * HALF_W * ry
    away = -side                                           # turn away from the side that hit (+1 = clockwise)

    def swipe(deg):
        x, y = _rotate_about(c1x, c1y, pvx, pvy, away * deg)
        return x, y, round(h1 + away * deg)
    clear = lambda deg: not collisions_with(footprint_from_center(*swipe(deg)), obstacles)

    prev, hi_deg = 0.0, None
    for k in range(1, int(head_on_min_deg) + 1):          # first whole degree that clears, then refine
        if clear(float(k)):
            hi_deg = float(k)
            break
        prev = float(k)
    if hi_deg is None:                                     # cannot swing clear (e.g. a narrow corridor): stop at contact
        out.update(conformed=True, stop_fraction=round(lo, 6), end=as_xy(pose(lo)),
                   note='sideswipe could not swing clear: stopped at contact')
        return out
    lo_deg = prev
    for _ in range(iterations):
        mid = (lo_deg + hi_deg) / 2
        if clear(mid):
            hi_deg = mid
        else:
            lo_deg = mid
    final = swipe(hi_deg)
    out.update(conformed=True, sideswipe=True, end=as_xy(final),
               rotation=int(round(final[2] - h1)), note='sideswipe')
    return out
