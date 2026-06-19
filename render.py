"""底层渲染工具：抗锯齿图元、辉光（叠加混合）、背景烘焙。

霓虹科幻风的两大支柱：
- gfxdraw 抗锯齿圆 / 多边形，消除廉价锯齿
- 缓存的径向渐变贴图用 BLEND_RGB_ADD 叠加出辉光/泛光
"""
import math
import pygame
from pygame import gfxdraw

import config as C

_glow_cache = {}


def _ci(c):
    return (int(c[0]), int(c[1]), int(c[2]))


def aacircle(surf, color, center, radius):
    x, y, r = int(center[0]), int(center[1]), int(radius)
    if r < 1:
        return
    color = _ci(color)
    gfxdraw.filled_circle(surf, x, y, r, color)
    gfxdraw.aacircle(surf, x, y, r, color)


def aaring(surf, color, center, radius, width=1):
    x, y, r = int(center[0]), int(center[1]), int(radius)
    color = _ci(color)
    for i in range(max(1, width)):
        if r - i > 0:
            gfxdraw.aacircle(surf, x, y, r - i, color)


def aapolygon(surf, color, pts):
    ipts = [(int(p[0]), int(p[1])) for p in pts]
    color = _ci(color)
    gfxdraw.filled_polygon(surf, ipts, color)
    gfxdraw.aapolygon(surf, ipts, color)


def _make_glow(radius, color):
    size = radius * 2
    g = pygame.Surface((size, size))
    g.fill((0, 0, 0))
    cx = cy = radius
    for rr in range(radius, 0, -1):
        f = rr / radius                  # 1=边缘 0=中心
        b = (1 - f) ** 1.7
        col = (int(color[0] * b), int(color[1] * b), int(color[2] * b))
        pygame.draw.circle(g, col, (cx, cy), rr)
    return g


def glow(surf, center, radius, color):
    """在 center 叠加一团发光（加法混合）。半径量化以复用缓存。"""
    radius = max(2, (int(radius) // 2) * 2)
    color = _ci(color)
    key = (radius, color)
    g = _glow_cache.get(key)
    if g is None:
        g = _make_glow(radius, color)
        _glow_cache[key] = g
    surf.blit(g, (int(center[0]) - radius, int(center[1]) - radius),
              special_flags=pygame.BLEND_RGB_ADD)


def beam(surf, a, b, color, width=2, glow_color=None):
    """发光光束：沿线叠加辉光 + 抗锯齿亮核。"""
    a = (a[0], a[1])
    b = (b[0], b[1])
    gc = glow_color or color
    dx, dy = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(dx, dy)
    steps = max(2, int(dist // 14))
    for i in range(steps + 1):
        t = i / steps
        p = (a[0] + dx * t, a[1] + dy * t)
        glow(surf, p, 9 + width * 2, (gc[0] // 3, gc[1] // 3, gc[2] // 3))
    pygame.draw.aaline(surf, _ci(color), a, b)
    if width > 1:
        pygame.draw.line(surf, _ci(color), a, b, width)


def soft_shadow(surf, center, rx, ry):
    """半透明柔和阴影。"""
    s = pygame.Surface((int(rx * 2), int(ry * 2)), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 90), (0, 0, int(rx * 2), int(ry * 2)))
    surf.blit(s, (int(center[0] - rx), int(center[1] - ry * 0.4 + ry)))


# ---------------- 背景烘焙（一次性）----------------
def build_background(w, h, terminal_pos, s=1):
    """烘焙战场背景。s 为超采样倍率：w/h/terminal_pos 已是物理像素，
    内部装饰尺寸按 s 放大以保持视觉密度。"""
    bg = pygame.Surface((w, h))
    bg.fill(C.C_BG)

    # 终端处的环境能量光
    glow(bg, terminal_pos, int(360 * s), (16, 34, 60))
    glow(bg, terminal_pos, int(180 * s), (20, 44, 78))

    # 细网格
    step = int(40 * s)
    for x in range(0, w, step):
        pygame.draw.line(bg, C.C_GRID, (x, 0), (x, h), max(1, round(s)))
    for y in range(0, h, step):
        pygame.draw.line(bg, C.C_GRID, (0, y), (w, y), max(1, round(s)))
    # 主网格（更亮）
    major = (38, 48, 68)
    for x in range(0, w, int(160 * s)):
        pygame.draw.line(bg, major, (x, 0), (x, h), max(1, round(s)))
    for y in range(0, h, int(160 * s)):
        pygame.draw.line(bg, major, (0, y), (w, y), max(1, round(s)))

    # 终端周围的装饰光环
    for rad, col in ((150, (30, 55, 80)), (320, (24, 42, 64))):
        aaring(bg, col, terminal_pos, int(rad * s), 1)

    # 暗角
    vig = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2, h / 2
    maxd = math.hypot(cx, cy)
    vig.fill((0, 0, 0, 140))
    for r in range(int(maxd), 0, -max(1, int(4 * s))):
        a = int(140 * (r / maxd) ** 1.5)
        pygame.draw.circle(vig, (0, 0, 0, a), (int(cx), int(cy)), r)
    bg.blit(vig, (0, 0))
    return bg
