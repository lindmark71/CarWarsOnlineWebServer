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

def _is_convex(poly):
    n = len(poly)
    if n < 3:
        return False
    sign = 0
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < 1e-9:
            continue
        s_ = 1 if cross > 0 else -1
        if sign == 0:
            sign = s_
        elif s_ != sign:
            return False
    return True

def _sat_overlap(a, b, eps=1e-6):
    """Overlap test for two CONVEX polygons (separating-axis theorem). Exact even when edges and corners
    line up exactly, which the crossing test below cannot see. Touching (within eps) is not overlapping."""
    for poly in (a, b):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            nx, ny = y2 - y1, x1 - x2
            length = math.hypot(nx, ny)
            if length == 0:
                continue
            nx, ny = nx / length, ny / length
            pa = [p[0] * nx + p[1] * ny for p in a]
            pb = [p[0] * nx + p[1] * ny for p in b]
            if max(pa) <= min(pb) + eps or max(pb) <= min(pa) + eps:
                return False
    return True

def _centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))

def polygons_overlap(a, b):
    """True if two simple polygons (convex OR concave) share area."""
    if not _bbox_overlap(_bbox(a), _bbox(b)):
        return False
    if len(a) <= 8 and len(b) <= 8 and _is_convex(a) and _is_convex(b):     # cars and rectangles
        return _sat_overlap(a, b)
    for i in range(len(a)):                                                 # curved walls, concave shapes
        a1, a2 = a[i], a[(i + 1) % len(a)]
        for j in range(len(b)):
            if _edges_cross(a1, a2, b[j], b[(j + 1) % len(b)]):
                return True
    return (any(_inside_strict(p, b) for p in a) or _inside_strict(b[0], a)
            or _inside_strict(_centroid(a), b) or _inside_strict(_centroid(b), a))

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

def build_obstacles(records, mover=None):
    """Pre-computes every solid stationary shape once, so a move can be probed many times cheaply.
    Pass `mover` (the username of the car that is moving) to also treat every OTHER car as a solid
    obstacle at its current position; with mover=None cars are ignored."""
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

    if mover is not None:
        newest = {}                                        # the newest CarPosition line per owner wins
        for idx, raw in enumerate(records):
            if isinstance(raw, dict):
                e = _norm(raw)
                if e.get('CarPosition') == 'CarPosition' and e.get('owner') != mover:
                    newest[e.get('owner')] = (idx, e)
        for owner, (idx, e) in newest.items():
            try:
                quad = footprint_from_center(float(e['local_starting_x_qty']) * GRID + HALF_W,
                                             float(e['local_starting_y_qty']) * GRID + HALF_H,
                                             float(e.get('orientation', 0)))
                shapes.append({'type': 'Car', 'index': idx, 'kind': 'poly', 'data': quad, 'bbox': _bbox(quad),
                               'owner': owner,
                               'pose': (float(e['local_starting_x_qty']), float(e['local_starting_y_qty']),
                                        float(e.get('orientation', 0)))})
            except Exception as err:
                print(f'[COLLISION] skipped car of {owner} at index {idx}: {err}')
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
            hit_info = {'type': s['type'], 'index': s['index']}
            if 'owner' in s:
                hit_info['owner'] = s['owner']
            hits.append(hit_info)
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

def _resolve_against(obstacles, x_qty, y_qty, orientation, maneuver,
                     samples=24, iterations=16, head_on_min_deg=45.0):
    """Plays one maneuver against a prebuilt set of obstacles; the moving car conforms to all of them.
    (See resolve_move for the result dictionary.)"""
    step, turn = parse_maneuver(maneuver)
    cx0, cy0 = x_qty * GRID + HALF_W, y_qty * GRID + HALF_H
    pose = lambda t, rnd=True: pose_at(cx0, cy0, float(orientation), step, turn, t, rnd)
    quad = lambda t: footprint_from_center(*pose(t))
    as_xy = lambda p: {'x': (p[0] - HALF_W) / GRID, 'y': (p[1] - HALF_H) / GRID, 'orientation': p[2] % 360}

    full_end = as_xy(pose(1.0))
    out = {'collided': False, 'conformed': False, 'head_on': None, 'angle': None, 'stop_fraction': 1.0,
           'end': full_end, 'full_end': full_end, 'hits': [], 'note': '', 'sideswipe': False, 'rotation': 0,
           'pushed': [], 'conforming': None, 'impact_heading': None, 'impacts': []}

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
               hits=hi_hits, stop_fraction=round(lo, 6), impact_heading=pose(hi, False)[2] % 360)
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


# ═══════════════════════════════ Car-versus-car conforming ═══════════════════════════════
#
# Each car has a DM (damage modifier). The moving car (V1) and the car it hits (V2) are compared:
#   V1.DM >= V2.DM  ->  V1 forces V2 to conform: V1 completes its move and V2 is pushed out of the way.
#   V1.DM <  V2.DM  ->  a lower-DM car never forces another to conform, so V1 conforms to V2
#                       (V2 acts like a wall: head-on stops flush, a sideswipe swings clear).

# (from_lbs, to_lbs, DM). The rulebook text so far: under 4,000 lbs = 2/3, 4,000 to 8,000 lbs = 1.
# Heavier vehicles are not specified yet; they are treated as DM 1 until that row is filled in.
DM_TABLE = ((0, 4000, 2.0 / 3.0), (4000, 8000, 1.0), (8000, float('inf'), 1.0))

def dm_from_weight(weight_lbs):
    w = float(weight_lbs)
    for lo, hi, dm in DM_TABLE:
        if lo <= w < hi:
            return dm
    return 1.0

MAX_PUSH_PX = 2 * CAR_L          # a struck car is never pushed further than two car lengths


def _first_contact_info(pose, obstacles, samples=24, iterations=16):
    """Where the mover's path first overlaps `obstacles`, and how (angle, direction of travel, contact edge)."""
    quad = lambda t: footprint_from_center(*pose(t))
    prev, lo, hi, hi_hits = 0.0, None, None, None
    for i in range(1, samples + 1):
        t = i / samples
        hits = collisions_with(quad(t), obstacles)
        if hits:
            lo, hi, hi_hits = prev, t, hits
            break
        prev = t
    if hi is None:
        return None
    for _ in range(iterations):
        mid = (lo + hi) / 2
        h = collisions_with(quad(mid), obstacles)
        if h:
            hi, hi_hits = mid, h
        else:
            lo = mid
    edges, points = _contact(quad(hi), _obstacle_segments(obstacles, hi_hits))
    info = {'lo': lo, 'hi': hi, 'hits': hi_hits, 'angle': None, 'travel': None, 'point': None, 'edge': None}
    if edges and points:
        pt = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        d = _travel_direction(pose, hi, pt)
        info.update(point=pt, travel=d)
        if d:
            scored = [(a, e) for e in edges for a in [_angle_to_wall(d, *e)] if a is not None]
            if scored:
                info['angle'], info['edge'] = max(scored, key=lambda s: s[0])
    return info


MAX_PIVOT_DEG = 120              # a struck car never pivots further than this


def _pivot_car(pose, mover_end_quad, shape, obstacles, info, angle, mover_heading, which_end='far'):
    """T-bone conforming (rulebook Figure 10). The struck car (V2) pivots about the end of the struck side
    that is FARTHER from the point of impact (the corner stays put), and the end that was hit swings away the
    way the mover is travelling, by the smallest turn that leaves V2 clear of the mover's final pose.
    which_end='far' (the default) is that end; 'near' is the other end of the same side, used as a second
    choice. The mover has already completed its whole move.
    Returns (push dict, None) or (None, reason it cannot pivot)."""
    a, b = info['edge']                                   # the two ends of the side that was struck
    pt = info['point']
    near_a = math.hypot(a[0] - pt[0], a[1] - pt[1]) <= math.hypot(b[0] - pt[0], b[1] - pt[1])
    if which_end == 'far':                                # pivot on the end away from the impact
        near_a = not near_a
    pivot, swing = (a, b) if near_a else (b, a)            # `swing` is the other end of the struck side
    if _inside_strict(pivot, mover_end_quad):             # a point that is inside the mover can never turn clear of it
        return None, 'the pivot corner is inside the mover'

    d = info.get('travel')                                # the way the mover was travelling at the impact
    if not d:
        mh = math.radians(mover_heading)
        d = (math.sin(mh), -math.cos(mh))

    def swing_end_advance(deg):                           # how far a turn of `deg` carries the swinging end along d
        fx, fy = _rotate_about(swing[0], swing[1], pivot[0], pivot[1], deg)
        return (fx - swing[0]) * d[0] + (fy - swing[1]) * d[1]
    sign = 1.0 if swing_end_advance(5.0) >= swing_end_advance(-5.0) else -1.0

    x0, y0, h0 = shape['pose']
    cx0, cy0 = x0 * GRID + HALF_W, y0 * GRID + HALF_H

    def pose_after(deg):                                  # position from the exact turn, heading in whole degrees
        cx, cy = _rotate_about(cx0, cy0, pivot[0], pivot[1], sign * deg)
        return cx, cy, round(h0 + sign * deg)
    quad_after = lambda deg: footprint_from_center(*pose_after(deg))
    clear = lambda deg: not polygons_overlap(mover_end_quad, quad_after(deg))

    if clear(0.0):
        return None, 'not overlapping the mover final pose'
    prev, hi_deg = 0.0, None
    for k in range(1, int(MAX_PIVOT_DEG) + 1):
        if clear(float(k)):
            hi_deg = float(k)
            break
        prev = float(k)
    if hi_deg is None:
        return None, f'cannot pivot clear within {MAX_PIVOT_DEG} degrees'
    lo_deg = prev
    for _ in range(24):
        mid = (lo_deg + hi_deg) / 2
        if clear(mid):
            hi_deg = mid
        else:
            lo_deg = mid

    new_quad = quad_after(hi_deg)
    others = {'shapes': [o for o in obstacles['shapes'] if o['index'] != shape['index']], 'bounds': obstacles['bounds']}
    blocked_by = collisions_with(new_quad, others)
    if blocked_by:
        bl = blocked_by[0]
        return None, f"blocked by {bl['type']}" + (f" of {bl['owner']}" if 'owner' in bl else '')

    cx, cy, new_h = pose_after(hi_deg)
    end = {'x': (cx - HALF_W) / GRID, 'y': (cy - HALF_H) / GRID, 'orientation': new_h % 360}
    return {'owner': shape['owner'], 'index': shape['index'], 'direction': 'pivot',
            'distance_px': round(math.hypot(cx - cx0, cy - cy0), 4), 'dx_px': cx - cx0, 'dy_px': cy - cy0,
            'angle': None if angle is None else round(angle, 1), 'head_on': True, 'mover_heading': mover_heading,
            'pivot': pivot, 'pivot_end': which_end, 'rotation': int(round(sign * hi_deg)),
            'start': {'x': x0, 'y': y0, 'orientation': h0 % 360}, 'end': end, 'quad': new_quad}, None


def _push_car(pose, mover_end_quad, shape, obstacles, head_on_min_deg):
    """Moves the struck car (V2) the least distance that leaves it clear of the mover's final pose.
    A T-bone pivots V2 about the end of the struck side that is farther from the impact (see _pivot_car); if that cannot
    be done it tries the nearer end, and failing that pushes V2 straight back. Any other hit keeps V2's
    heading: a head-on or rear-end pushes it the way the mover was travelling, and a sideswipe nudges it
    straight away from the surface that was grazed.
    Returns (push dict, None) or (None, reason it cannot be pushed)."""
    info = _first_contact_info(pose, {'shapes': [shape], 'bounds': None})
    angle = info['angle'] if info else None
    head_on = angle is None or angle >= head_on_min_deg
    mover_heading = (pose(info['hi'], False)[2] if info else pose(1.0, False)[2]) % 360
    pivot_failed = []
    if (info and info['edge'] and info['point']
            and classify_car_impact(angle, mover_heading, shape['pose'][2], head_on_min_deg) == 't-bone'):
        for which in ('far', 'near'):                     # pivot on the end away from the impact; failing that, the other end
            result, reason = _pivot_car(pose, mover_end_quad, shape, obstacles, info, angle, mover_heading, which)
            if result is not None:
                if pivot_failed:
                    result['pivot_failed'] = pivot_failed
                return result, None
            pivot_failed.append(f'{which} end: {reason}')
        # neither end can pivot: the car is still moved out of the way, straight back, below

    car_quad = shape['data']
    ccx, ccy = _centroid(car_quad)
    if head_on or not info or not info['edge']:
        d = (info or {}).get('travel')
        if not d:                                           # fall back to the mover's final heading
            qx = mover_end_quad
            d = ((qx[0][0] - qx[3][0]), (qx[0][1] - qx[3][1]))
            n = math.hypot(*d) or 1.0
            d = (d[0] / n, d[1] / n)
        direction, kind = d, 'travel'
    else:                                                   # sideswipe: away from the grazed surface
        (ax, ay), (bx, by) = info['edge']
        nx, ny = ay - by, bx - ax
        ln = math.hypot(nx, ny) or 1.0
        nx, ny = nx / ln, ny / ln
        px, py = info['point']
        if nx * (ccx - px) + ny * (ccy - py) < 0:
            nx, ny = -nx, -ny
        direction, kind = (nx, ny), 'normal'

    moved = lambda s: [(x + direction[0] * s, y + direction[1] * s) for x, y in car_quad]
    clear = lambda s: not polygons_overlap(mover_end_quad, moved(s))
    if clear(0.0):
        return None, 'not overlapping the mover final pose'
    prev, hi_s = 0.0, None
    for k in range(1, int(MAX_PUSH_PX) + 1):
        if clear(float(k)):
            hi_s = float(k)
            break
        prev = float(k)
    if hi_s is None:
        return None, f'would have to be pushed more than {MAX_PUSH_PX:.0f} px'
    lo_s = prev
    for _ in range(24):
        mid = (lo_s + hi_s) / 2
        if clear(mid):
            hi_s = mid
        else:
            lo_s = mid
    s = hi_s

    others = {'shapes': [o for o in obstacles['shapes'] if o['index'] != shape['index']], 'bounds': obstacles['bounds']}
    blocked_by = collisions_with(moved(s), others)
    if blocked_by:
        b = blocked_by[0]
        return None, f"blocked by {b['type']}" + (f" of {b['owner']}" if 'owner' in b else '')

    x0, y0, h0 = shape['pose']
    end = {'x': x0 + direction[0] * s / GRID, 'y': y0 + direction[1] * s / GRID, 'orientation': h0 % 360}
    return {'owner': shape['owner'], 'index': shape['index'], 'direction': kind,
            'distance_px': round(s, 4), 'dx_px': direction[0] * s, 'dy_px': direction[1] * s,
            'angle': None if angle is None else round(angle, 1), 'head_on': head_on, 'mover_heading': mover_heading,
            'start': {'x': x0, 'y': y0, 'orientation': h0 % 360}, 'end': end,
            'quad': moved(s), 'pivot_failed': pivot_failed}, None


def resolve_move(records, x_qty, y_qty, orientation, maneuver,
                 samples=24, iterations=16, head_on_min_deg=45.0, mover=None, dm=None):
    """Plays a maneuver against the map's solid objects and, when `mover` is given, the other cars.

    x_qty / y_qty / orientation: the moving car's CarPosition before the move.
    mover: its username.  dm: {username: DM}; a car that is missing counts as DM 1.
    Returns a dict:
      collided, conformed, head_on, angle   what happened (angle: 90 = square on, None if no hit)
      stop_fraction                         how much of the move was completed (1.0 = all of it)
      end / full_end                        where the mover ends up / would have ended with no obstacle
                                            ({'x','y'} in CarPosition grid units, 'orientation' in degrees)
      sideswipe, rotation                   a sideswipe finishes the move and swings off the rear corner
      conforming                            None, 'mover' (it conformed to a car) or 'other' (it pushed one)
      pushed                                the cars it forced to conform: owner, index, start, end, ...
      hits, note
    Walls: head-on hits (angle >= head_on_min_deg) stop the mover flush; sideswipes finish the move and swing
    the mover off its rear corner just clear of the surface.
    Cars: see the DM rules above. A car that cannot be pushed (a wall or another car is behind it)
    cannot be forced to conform, so the mover conforms to it instead.
    """
    obstacles = build_obstacles(records, mover)
    cars = [s for s in obstacles['shapes'] if s['type'] == 'Car']
    kw = dict(samples=samples, iterations=iterations, head_on_min_deg=head_on_min_deg)

    def mover_conforms(note=''):
        out = _resolve_against(obstacles, x_qty, y_qty, orientation, maneuver, **kw)
        if any(h['type'] == 'Car' for h in out['hits']):
            out['conforming'] = 'mover'
            by_index = {c['index']: c for c in cars}
            for h in out['hits']:
                if h['type'] == 'Car' and h['index'] in by_index and out['impact_heading'] is not None:
                    struck_heading = by_index[h['index']]['pose'][2] % 360
                    out['impacts'].append({
                        'owner': h['owner'], 'index': h['index'], 'conformed': 'mover', 'angle': out['angle'],
                        'mover_heading': out['impact_heading'], 'struck_heading': struck_heading,
                        'type': classify_car_impact(out['angle'], out['impact_heading'], struck_heading)})
        if note:
            out['note'] = f"{out['note']} | {note}" if out['note'] else note
        return out

    if mover is None or not cars:
        return mover_conforms()

    dm = dm or {}
    mover_dm = float(dm.get(mover, 1.0))
    forceable = {c['owner'] for c in cars if mover_dm >= float(dm.get(c['owner'], 1.0))}
    if not forceable:
        return mover_conforms()

    if collisions_with(car_footprint(x_qty, y_qty, orientation), obstacles):      # already overlapping at the start
        return mover_conforms()

    # the mover completes its move, stopped only by walls and by cars it may not force to conform
    blockers = {'shapes': [s for s in obstacles['shapes'] if not (s['type'] == 'Car' and s['owner'] in forceable)],
                'bounds': obstacles['bounds']}
    out = _resolve_against(blockers, x_qty, y_qty, orientation, maneuver, **kw)
    if out['note'] == 'overlap_at_start':
        return out

    end = out['end']
    end_quad = footprint_from_center(end['x'] * GRID + HALF_W, end['y'] * GRID + HALF_H, end['orientation'])
    step, turn = parse_maneuver(maneuver)
    cx0, cy0 = x_qty * GRID + HALF_W, y_qty * GRID + HALF_H
    pose = lambda t, rnd=True: pose_at(cx0, cy0, float(orientation), step, turn, t, rnd)

    working = {'shapes': list(obstacles['shapes']), 'bounds': obstacles['bounds']}
    pushed = []
    for shape in cars:
        if shape['owner'] not in forceable or not polygons_overlap(end_quad, shape['data']):
            continue
        push, reason = _push_car(pose, end_quad, shape, working, head_on_min_deg)
        if push is None:
            return mover_conforms(f"{shape['owner']} could not be pushed ({reason}): the mover conformed instead")
        pushed.append(push)
        moved_shape = dict(shape, data=push['quad'], bbox=_bbox(push['quad']),
                           pose=(push['end']['x'], push['end']['y'], push['end']['orientation']))
        working['shapes'] = [moved_shape if o['index'] == shape['index'] else o for o in working['shapes']]

    if not pushed:
        return out
    first = pushed[0]
    for p in pushed:
        p.pop('quad', None)
        out['impacts'].append({
            'owner': p['owner'], 'index': p['index'], 'conformed': 'other', 'angle': p['angle'],
            'mover_heading': p['mover_heading'], 'struck_heading': p['start']['orientation'],
            'type': classify_car_impact(p['angle'], p['mover_heading'], p['start']['orientation'])})
    out.update(collided=True, conforming='other', pushed=pushed, head_on=first['head_on'], angle=first['angle'],
               hits=[{'type': 'Car', 'index': p['index'], 'owner': p['owner']} for p in pushed] + out['hits'])
    out['note'] = (out['note'] + ' | ' if out['note'] else '') + 'pushed ' + ', '.join(p['owner'] for p in pushed)
    for p in pushed:
        if p.get('pivot_failed'):
            out['note'] += f" | {p['owner']} could not pivot ({'; '.join(p['pivot_failed'])})"
    return out


# ═══════════════════════════════ Collision types and speed changes ═══════════════════════════════
#
# Four types of car-versus-car collision, from the approach angle and the two cars' headings:
#   sideswipe  the mover meets the other car at under 45 degrees to its surface   -> no speed change
#   head-on    the cars face each other (headings 135-180 degrees apart)          -> each loses the AVERAGE speed
#   rear-end   the cars point the same way (headings 0-45 degrees apart)          -> both end at the AVERAGE speed
#   t-bone     anything in between                                                -> the MOVER's speed is halved
# "Mover" is the car whose movement caused the collision; the car it hits is not the mover.

SPEED_STEP = 5               # speeds change in whole steps of 5 mph
SPEED_ROUNDING = 'nearest'   # 'nearest' (an exact tie goes DOWN, toward zero), 'down' or 'up'; applied to the size of the speed

def classify_car_impact(angle, mover_heading, struck_heading, sideswipe_below_deg=45.0):
    """'sideswipe', 'head-on', 'rear-end' or 't-bone'.  angle: the mover's angle to the struck surface
    (90 = square on); None (cars lined up exactly, no measurable edge) counts as square on."""
    if angle is not None and angle < sideswipe_below_deg:
        return 'sideswipe'
    rel = abs(((float(struck_heading) - float(mover_heading) + 180.0) % 360.0) - 180.0)   # 0 = same way, 180 = opposite
    if rel >= 135.0:
        return 'head-on'
    if rel <= 45.0:
        return 'rear-end'
    return 't-bone'

def round_speed(v):
    """Rounds a speed to a multiple of SPEED_STEP using SPEED_ROUNDING (applied to the size, keeping the sign)."""
    sign = -1 if v < 0 else 1
    units = abs(float(v)) / SPEED_STEP
    if SPEED_ROUNDING == 'down':
        r = math.floor(units + 1e-9)
    elif SPEED_ROUNDING == 'up':
        r = math.ceil(units - 1e-9)
    else:
        r = math.ceil(units - 0.5 - 1e-9)          # nearest; an exact .5 goes down
    return sign * r * SPEED_STEP

def speeds_after_collision(kind, mover_speed, other_speed):
    """(new mover speed, new other speed), before rounding. A speed below zero means the car is being pushed backwards."""
    m, o = float(mover_speed), float(other_speed)
    if kind == 't-bone':
        return m / 2.0, o                           # only the car that moved halves
    avg = (m + o) / 2.0
    if kind == 'rear-end':
        return avg, avg                             # both end at the average
    if kind == 'head-on':
        return m - avg, o - avg                     # each is reduced by the average; the slower car can go negative
    return m, o                                     # sideswipe: unchanged

def apply_speed_changes(impacts, mover, speeds):
    """Applies resolve_move()'s `impacts` in order, each using the speeds as the previous one left them.
    speeds: {username: current speed}. Returns (new speeds {username: int}, changes), where each change is
    {'owner', 'with', 'type', 'before', 'after'} and only cars whose speed really changed are listed."""
    speeds = {k: float(v) for k, v in speeds.items()}
    changes = []
    for imp in impacts:
        other = imp['owner']
        m0, o0 = speeds.get(mover, 0.0), speeds.get(other, 0.0)
        m1, o1 = (round_speed(v) for v in speeds_after_collision(imp['type'], m0, o0))
        speeds[mover], speeds[other] = m1, o1
        for who, with_, before, after in ((mover, other, m0, m1), (other, mover, o0, o1)):
            if before != after:
                changes.append({'owner': who, 'with': with_, 'type': imp['type'],
                                'before': int(before) if before == int(before) else before, 'after': int(after)})
    return {k: int(v) for k, v in speeds.items()}, changes
