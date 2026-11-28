"""
petpath.py - pets find their way around walls, huts, cliffs and rivers. Used by main._pet_brain.

Pets used to walk in a straight line at whatever they wanted (a bush, a rock, the Storage Bin) and, when
something was in the way, sidestep at random for a moment - fine for a tree, hopeless for a wall or a
cliff. Now:

  * A pet still walks straight while it can (cheap, and looks natural).
  * If it bumps into something and gets no closer for a moment, it plans a route on a grid of CELL x CELL squares (A*, only around itself
    and its target) using the same collision tests as walking (main.step_body), then follows the corners.
  * If there is no way to get there (a rock on the far side of a cliff), the brain is told so and picks
    something else; that target is skipped for a while (SKIP_SECONDS).

Only the host / solo game runs this (pets are moved on the host), so co-op needs nothing extra.
"""
import heapq
import math

import arcade

CELL = 28                 # grid square (px): a bit smaller than a pet, so gaps a pet fits through are found
MARGIN = 520              # how far outside the start-target box the search may wander (px)
MAX_NODES = 1800          # give up after this many squares (a failed search costs ~20 ms at most)
RETRY_SECONDS = (3.0, 20.0)   # after a failed search wait this long (doubling each time, up to the second)
PROGRESS_SECONDS = 0.8    # bumped into something and no closer after this long -> plan a route
PROGRESS_PX = 24          # ... "closer" means at least this much
REPLAN_SECONDS = 6.0      # follow a route at most this long before checking for a better one
WAYPOINT_REACHED = 18     # px: close enough to a corner to head for the next one
SKIP_SECONDS = 45.0       # an unreachable bush / tree / rock is ignored this long
PLANS_PER_FRAME = 2       # at most this many searches a frame, so many stuck pets never cause a hitch


def _blocked_test(game, a, blockers):
    """(cell x, cell y) -> True if pet `a` can't stand in the middle of that square. Uses the pet's own hit
    box against the same lists step_body uses (with their spatial hashes), plus cliffs / water."""
    cache = {}
    land = bool(blockers)
    ox, oy = a.center_x, a.center_y

    def blocked(cx, cy):
        k = (cx, cy)
        v = cache.get(k)
        if v is None:
            x, y = cx * CELL + CELL / 2, cy * CELL + CELL / 2
            if x < 40 or y < 40 or x > game.world_size - 40 or y > game.world_size - 40:
                v = True
            else:
                a.center_x, a.center_y = x, y
                v = bool(arcade.check_for_collision_with_lists(a, blockers)) if land else False
                if not v and land:
                    v = bool(game.body_blocked(a, x, y))
            cache[k] = v
        return v

    def done():
        a.center_x, a.center_y = ox, oy
    return blocked, done


def plan(game, a, tx, ty, blockers, slack=40):
    """A list of (x, y) corners from pet `a` to within `slack` of (tx, ty), or None if there's no way."""
    blocked, done = _blocked_test(game, a, blockers)
    try:
        sx, sy = int(a.center_x // CELL), int(a.center_y // CELL)
        gx, gy = int(tx // CELL), int(ty // CELL)
        # the target itself is usually solid (a rock, the bin): getting this close is enough - from there
        # the pet walks the last bit straight in, as before
        reach = max(2, int((slack + 30) // CELL))
        lo_x, hi_x = min(sx, gx) - MARGIN // CELL, max(sx, gx) + MARGIN // CELL
        lo_y, hi_y = min(sy, gy) - MARGIN // CELL, max(sy, gy) + MARGIN // CELL

        def h(x, y):
            dx, dy = abs(x - gx), abs(y - gy)
            return max(dx, dy) + 0.41 * min(dx, dy)

        def at_goal(x, y):
            return max(abs(x - gx), abs(y - gy)) <= reach

        start = (sx, sy)
        came = {start: None}
        cost = {start: 0.0}
        heap = [(h(sx, sy), 0.0, sx, sy)]
        end = None
        n = 0
        steps = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.41), (1, -1, 1.41), (-1, 1, 1.41), (-1, -1, 1.41))
        while heap:
            _, c, x, y = heapq.heappop(heap)
            if c > cost.get((x, y), 1e18):
                continue
            if at_goal(x, y):
                end = (x, y)
                break
            n += 1
            if n > MAX_NODES:
                break
            for dx, dy, w in steps:
                nx, ny = x + dx, y + dy
                if nx < lo_x or nx > hi_x or ny < lo_y or ny > hi_y:
                    continue
                if blocked(nx, ny):
                    continue
                if dx and dy and (blocked(x + dx, y) or blocked(x, y + dy)):
                    continue                # no cutting corners past a wall's end
                nc = c + w
                if nc < cost.get((nx, ny), 1e18):
                    cost[(nx, ny)] = nc
                    came[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (nc + h(nx, ny), nc, nx, ny))
        if end is None:
            return None
        cells = []
        k = end
        while k is not None:
            cells.append(k)
            k = came[k]
        cells.reverse()
        return _smooth(cells, blocked)
    finally:
        done()


def _line_clear(a, b, blocked):
    """Can a pet walk straight from cell a to cell b? (checks every square the line passes)"""
    (x0, y0), (x1, y1) = a, b
    n = max(abs(x1 - x0), abs(y1 - y0)) * 2
    for i in range(1, n + 1):
        t = i / n
        if blocked(round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)):
            return False
    return True


def _smooth(cells, blocked):
    """Drop the in-between squares: keep only the corners the pet has to turn at."""
    if not cells:
        return []
    out = []
    i = 0
    while i < len(cells) - 1:
        j = len(cells) - 1
        while j > i + 1 and not _line_clear(cells[i], cells[j], blocked):
            j -= 1
        out.append(cells[j])
        i = j
    return [(x * CELL + CELL / 2, y * CELL + CELL / 2) for x, y in out]


# --------------------------------------------------------------------------- used by main._pet_brain
def steer(game, a, tx, ty, slack, dt):
    """Which way pet `a` should walk to reach (tx, ty): (dx, dy) unit vector, or None when it got there.
    Follows a planned route if it has one for this target; main._update_animals marks it stuck."""
    d = math.hypot(tx - a.center_x, ty - a.center_y)
    if d < slack:
        a.path = None
        return None
    route = getattr(a, "path", None)
    if route and getattr(a, "path_for", None) is not None and math.hypot(
            a.path_for[0] - tx, a.path_for[1] - ty) < CELL * 2:
        a.path_t = getattr(a, "path_t", 0.0) - dt
        while route and math.hypot(route[0][0] - a.center_x, route[0][1] - a.center_y) < WAYPOINT_REACHED:
            route.pop(0)
        if route and a.path_t > 0:
            wx, wy = route[0]
            wd = math.hypot(wx - a.center_x, wy - a.center_y) or 1
            return (wx - a.center_x) / wd, (wy - a.center_y) / wd
        a.path = None
    a.want = (tx, ty, slack)          # where it's heading (for the stuck handler below)
    return (tx - a.center_x) / d, (ty - a.center_y) / d


def no_progress(game, a, bumped, dt):
    """Called every step for a moving pet: True when it has bumped into something and got no closer to
    where it wants to go for PROGRESS_SECONDS (sliding up and down a wall counts as no progress)."""
    want = getattr(a, "want", None)
    if want is None or getattr(a, "path", None) or getattr(a, "plan_wait", 0.0) > game.flame_t:
        a.prog = None
        return False
    d = math.hypot(want[0] - a.center_x, want[1] - a.center_y)
    pr = getattr(a, "prog", None)
    if pr is None or pr[2] != want[:2]:
        a.prog = [0.0, d, want[:2], bumped]
        return False
    pr[0] += dt
    pr[3] = pr[3] or bumped
    if pr[0] < PROGRESS_SECONDS:
        return False
    stuck = pr[3] and d > pr[1] - PROGRESS_PX
    a.prog = [0.0, d, want[:2], False]
    return stuck


def unstick(game, a, blockers):
    """Called when a pet has been stuck a moment: plan a route to where it wants to go.
    Returns False if there's no way there (the brain then picks another target)."""
    want = getattr(a, "want", None)
    if want is None:
        return True
    fr = getattr(game, "_path_frame", None)
    if fr != game.flame_t:
        game._path_frame, game._path_n = game.flame_t, 0
    if game._path_n >= PLANS_PER_FRAME:
        a.prog = None                  # too many searches this frame: try again shortly
        return True
    game._path_n += 1
    tx, ty, slack = want
    route = plan(game, a, tx, ty, blockers, slack)
    if route is None:
        a.path = None
        n = getattr(a, "plan_fails", 0)
        a.plan_fails = n + 1
        a.plan_wait = game.flame_t + min(RETRY_SECONDS[1], RETRY_SECONDS[0] * 2 ** n)
        return False
    a.path, a.path_for, a.path_t = route, (tx, ty), REPLAN_SECONDS
    a.plan_fails = 0
    return True


def skip(game, a, node):
    """Remember that `node` can't be reached by this pet, for a while."""
    sk = getattr(a, "skip", None)
    if sk is None:
        sk = a.skip = {}
    sk[id(node)] = game.flame_t + SKIP_SECONDS


def skipped(game, a, node):
    sk = getattr(a, "skip", None)
    return bool(sk) and sk.get(id(node), 0) > game.flame_t
