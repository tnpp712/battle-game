"""流场寻路：从终端对整个战场做 Dijkstra 距离场，敌人沿梯度绕开障碍前进。

相比局部转向避障，流场不会陷入凹形死角，也不会在卡死时穿墙。
墙体/地形变化时重新计算即可。
"""
import math
import heapq
import pygame
from pygame.math import Vector2

from geometry import segment_rect_intersect

INF = float("inf")
_DIAG = math.sqrt(2)
_NEIGH = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, _DIAG), (-1, 1, _DIAG), (1, -1, _DIAG), (1, 1, _DIAG),
)


class FlowField:
    def __init__(self, field_rect, cell=20):
        self.field = field_rect
        self.cell = cell
        self.cols = max(1, field_rect.width // cell)
        self.rows = max(1, field_rect.height // cell)
        self.dist = [[INF] * self.cols for _ in range(self.rows)]
        self.dirs = [[Vector2(0, 0)] * self.cols for _ in range(self.rows)]
        self.blocked = [[False] * self.cols for _ in range(self.rows)]

    def _cell_rect(self, c, r):
        return pygame.Rect(self.field.left + c * self.cell,
                           self.field.top + r * self.cell, self.cell, self.cell)

    def to_cell(self, pos):
        c = int((pos.x - self.field.left) // self.cell)
        r = int((pos.y - self.field.top) // self.cell)
        c = 0 if c < 0 else self.cols - 1 if c >= self.cols else c
        r = 0 if r < 0 else self.rows - 1 if r >= self.rows else r
        return c, r

    def compute(self, terminal_pos, terminal_radius, obstacles, clearance=16):
        self.dist = [[INF] * self.cols for _ in range(self.rows)]
        self.blocked = [[False] * self.cols for _ in range(self.rows)]
        infl = [o.inflate(clearance * 2, clearance * 2) for o in obstacles]
        for r in range(self.rows):
            for c in range(self.cols):
                cr = self._cell_rect(c, r)
                if any(cr.colliderect(o) for o in infl):
                    self.blocked[r][c] = True

        pq = []
        tc, tr = self.to_cell(terminal_pos)
        gr = int(terminal_radius // self.cell) + 1
        seeded = False
        for r in range(max(0, tr - gr), min(self.rows, tr + gr + 1)):
            for c in range(max(0, tc - gr), min(self.cols, tc + gr + 1)):
                center = Vector2(self._cell_rect(c, r).center)
                if center.distance_to(terminal_pos) <= terminal_radius + self.cell:
                    self.dist[r][c] = 0.0
                    heapq.heappush(pq, (0.0, r, c))
                    seeded = True
        if not seeded:
            self.dist[tr][tc] = 0.0
            heapq.heappush(pq, (0.0, tr, tc))

        while pq:
            d, r, c = heapq.heappop(pq)
            if d > self.dist[r][c]:
                continue
            for dr, dc, cost in _NEIGH:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.rows and 0 <= nc < self.cols):
                    continue
                if self.blocked[nr][nc]:
                    continue
                if dr != 0 and dc != 0:  # 禁止贴角穿过
                    if self.blocked[r][c + dc] or self.blocked[r + dr][c]:
                        continue
                nd = d + cost
                if nd < self.dist[nr][nc]:
                    self.dist[nr][nc] = nd
                    heapq.heappush(pq, (nd, nr, nc))

        # 由距离场生成流向（指向距离最小的邻格）
        for r in range(self.rows):
            for c in range(self.cols):
                if self.blocked[r][c] or self.dist[r][c] == INF:
                    self.dirs[r][c] = Vector2(0, 0)
                    continue
                best = self.dist[r][c]
                bv = Vector2(0, 0)
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if not (0 <= nr < self.rows and 0 <= nc < self.cols):
                            continue
                        if self.dist[nr][nc] < best:
                            best = self.dist[nr][nc]
                            bv = Vector2(dc, dr)
                self.dirs[r][c] = bv.normalize() if bv.length_squared() else Vector2(0, 0)

    def direction_at(self, pos):
        c, r = self.to_cell(pos)
        return Vector2(self.dirs[r][c])

    def reachable_at(self, pos):
        c, r = self.to_cell(pos)
        return self.dist[r][c] != INF


# ---------------- A* 单点寻路（机兵点击自动绕行）----------------
def _seg_blocked(a, b, rects):
    return any(segment_rect_intersect(a, b, r) for r in rects)


def _smooth(pts, rects):
    """串绳法：在保持不穿障碍的前提下，跳过中间多余拐点，让路径更顺。"""
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and _seg_blocked(pts[i], pts[j], rects):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def find_path(field, obstacles, start, goal, clearance=16, cell=20):
    """A* 在网格上寻一条从 start 到 goal、绕开障碍的路径。

    返回平滑后的航点列表（含起点；首航点即 start），无路可达时返回 None。
    obstacles 会按 clearance 膨胀，使路径与墙体保持安全距离。
    """
    cols = max(1, field.width // cell)
    rows = max(1, field.height // cell)
    infl = [o.inflate(clearance * 2, clearance * 2) for o in obstacles]

    def cell_rect(c, r):
        return pygame.Rect(field.left + c * cell, field.top + r * cell, cell, cell)

    blocked = [[any(cell_rect(c, r).colliderect(o) for o in infl)
                for c in range(cols)] for r in range(rows)]

    def to_cell(p):
        c = int((p.x - field.left) // cell)
        r = int((p.y - field.top) // cell)
        return (0 if c < 0 else cols - 1 if c >= cols else c,
                0 if r < 0 else rows - 1 if r >= rows else r)

    sc, sr = to_cell(start)
    gc, gr = to_cell(goal)

    goal_in_obstacle = any(o.collidepoint(goal.x, goal.y) for o in infl)
    # 目标落在障碍内：吸附到最近的空格
    if blocked[gr][gc]:
        found, best = None, INF
        for r in range(rows):
            for c in range(cols):
                if not blocked[r][c]:
                    d = (c - gc) ** 2 + (r - gr) ** 2
                    if d < best:
                        best, found = d, (c, r)
        if found is None:
            return None
        gc, gr = found

    diag = math.sqrt(2)
    neigh = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, diag), (-1, 1, diag), (1, -1, diag), (1, 1, diag))

    def heur(c, r):
        return math.hypot(c - gc, r - gr)

    openq = [(heur(sc, sr), 0.0, sc, sr)]
    gscore = {(sc, sr): 0.0}
    came = {}
    reached = False
    while openq:
        f, g, c, r = heapq.heappop(openq)
        if (c, r) == (gc, gr):
            reached = True
            break
        if g > gscore.get((c, r), INF):
            continue
        for dc, dr, cost in neigh:
            nc, nr = c + dc, r + dr
            if not (0 <= nc < cols and 0 <= nr < rows):
                continue
            if blocked[nr][nc]:
                continue
            if dc != 0 and dr != 0 and (blocked[r][c + dc] or blocked[r + dr][c]):
                continue
            ng = g + cost
            if ng < gscore.get((nc, nr), INF):
                gscore[(nc, nr)] = ng
                came[(nc, nr)] = (c, r)
                heapq.heappush(openq, (ng + heur(nc, nr), ng, nc, nr))
    if not reached:
        return None

    cells = [(gc, gr)]
    while cells[-1] in came:
        cells.append(came[cells[-1]])
    cells.reverse()

    pts = [Vector2(start)]
    for (c, r) in cells[1:]:
        pts.append(Vector2(cell_rect(c, r).center))
    # 目标本身在空地则精确走到点击处，否则停在吸附格中心
    if not goal_in_obstacle:
        pts.append(Vector2(goal))
    return _smooth(pts, infl)
