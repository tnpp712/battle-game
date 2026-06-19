"""几何辅助：线段/矩形相交、路径阻挡检测、圆-矩形碰撞、避障转向。"""
import math
import pygame
from pygame.math import Vector2


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _ccw(a, b, c):
    return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x)


def seg_seg_intersect(a, b, c, d):
    """两线段 ab 与 cd 是否相交。"""
    return (_ccw(a, c, d) != _ccw(b, c, d)) and (_ccw(a, b, c) != _ccw(a, b, d))


def segment_rect_intersect(p1, p2, rect):
    """线段 p1-p2 是否与矩形 rect 相交（含端点在内部）。"""
    if rect.collidepoint(p1.x, p1.y) or rect.collidepoint(p2.x, p2.y):
        return True
    tl = Vector2(rect.left, rect.top)
    tr = Vector2(rect.right, rect.top)
    br = Vector2(rect.right, rect.bottom)
    bl = Vector2(rect.left, rect.bottom)
    edges = ((tl, tr), (tr, br), (br, bl), (bl, tl))
    return any(seg_seg_intersect(p1, p2, e[0], e[1]) for e in edges)


def path_blocked(points, rects):
    """折线 points 是否穿过任一矩形。"""
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        for r in rects:
            if segment_rect_intersect(a, b, r):
                return True
    return False


def circle_rect_collide(center, radius, rect):
    cx = clamp(center.x, rect.left, rect.right)
    cy = clamp(center.y, rect.top, rect.bottom)
    return center.distance_squared_to(Vector2(cx, cy)) <= radius * radius


def resolve_circle_rects(center, radius, rects):
    """把圆心从所有矩形里推出来，返回修正后的位置。"""
    pos = Vector2(center)
    for r in rects:
        cx = clamp(pos.x, r.left, r.right)
        cy = clamp(pos.y, r.top, r.bottom)
        closest = Vector2(cx, cy)
        diff = pos - closest
        d = diff.length()
        if d < radius:
            out = radius + 0.5   # 多推出一点，确保彻底脱离而非相切
            if d == 0:
                # 圆心落在矩形内：沿最近边推出
                left = pos.x - r.left
                right = r.right - pos.x
                top = pos.y - r.top
                bottom = r.bottom - pos.y
                m = min(left, right, top, bottom)
                if m == left:
                    pos.x = r.left - out
                elif m == right:
                    pos.x = r.right + out
                elif m == top:
                    pos.y = r.top - out
                else:
                    pos.y = r.bottom + out
            else:
                pos = closest + diff.normalize() * out
    return pos


def steer_around(pos, desired_dir, radius, rects, step):
    """从 pos 朝 desired_dir 走 step，遇障碍尝试偏转方向，返回可行的位移向量。"""
    if desired_dir.length_squared() == 0:
        return Vector2(0, 0)
    base = desired_dir.normalize()
    for angle in (0, 25, -25, 50, -50, 80, -80, 115, -115, 150, -150):
        d = base.rotate(angle)
        nxt = pos + d * step
        if not any(circle_rect_collide(nxt, radius, r) for r in rects):
            return d * step
    return Vector2(0, 0)
