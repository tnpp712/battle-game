"""生成应用图标：复用游戏的霓虹矢量渲染，画「中央终端发光核心 + 防卫环 + 环绕机兵」。

输出 assets/icon_1024.png（再由 tools 里的 shell 转成 .icns/.ico）。
风格与游戏内 sprites.draw_terminal / render.glow 一致：暗底径向辉光、青色脉冲核心、
四个角色色机兵三角环绕，呼应「机兵防卫圈」主题。
"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from pygame.math import Vector2

import render

SIZE = 1024
CY = (90, 200, 255)          # 终端青
CY_HI = (170, 235, 255)
ROLE_COLORS = [(255, 120, 90), (120, 180, 255), (255, 210, 120), (140, 235, 170)]


def _round_mask(size, radius):
    """纯白圆角 alpha 蒙版：仅用于裁掉四角（BLEND_RGBA_MULT 保留 RGB、切 alpha）。"""
    m = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(m, (255, 255, 255, 255), (0, 0, size, size), border_radius=radius)
    return m


def _mech(surf, cx, cy, ang, R, color):
    """朝外的小机兵三角（带辉光）。"""
    rad = math.radians(ang)
    def pt(fx, fy):
        v = Vector2(fx, fy).rotate(ang)
        return (cx + v.x * R, cy + v.y * R)
    body = [pt(1.0, 0), pt(-0.7, 0.7), pt(-0.4, 0), pt(-0.7, -0.7)]
    render.glow(surf, (cx, cy), R * 2.2, tuple(c // 2 for c in color))
    render.aapolygon(surf, color, body)
    pygame.draw.aalines(surf, tuple(min(255, c + 60) for c in color), True, body)
    render.aacircle(surf, (250, 252, 245), pt(0.15, 0), max(2, int(R * 0.18)))


def build():
    pygame.init()
    pygame.display.set_mode((1, 1))
    c = SIZE / 2
    base = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)

    # 暗色径向渐变背景（中心偏亮的深蓝 → 边缘近黑）
    maxd = math.hypot(c, c)
    for r in range(int(maxd), 0, -2):
        f = r / maxd                       # 0=中心 1=边缘
        col = (int(10 + 24 * (1 - f)), int(16 + 34 * (1 - f)), int(28 + 48 * (1 - f)), 255)
        pygame.draw.circle(base, col, (int(c), int(c)), r)

    # 环境径向辉光（加法）
    render.glow(base, (c, c), SIZE * 0.50, (26, 64, 110))
    render.glow(base, (c, c), SIZE * 0.30, (40, 90, 150))

    # 细网格
    step = 64
    grid = (30, 44, 66)
    for x in range(0, SIZE, step):
        pygame.draw.line(base, grid, (x, 0), (x, SIZE))
    for y in range(0, SIZE, step):
        pygame.draw.line(base, grid, (0, y), (SIZE, y))

    # 防卫环（两道）
    render.aaring(base, (70, 130, 185), (c, c), int(SIZE * 0.40), 3)
    render.aaring(base, (90, 165, 220), (c, c), int(SIZE * 0.34), 4)

    # 环绕机兵（四角色，朝外）
    orbit = SIZE * 0.34
    for i, col in enumerate(ROLE_COLORS):
        ang = -90 + i * 90 + 45
        mx = c + math.cos(math.radians(ang)) * orbit
        my = c + math.sin(math.radians(ang)) * orbit
        _mech(base, mx, my, ang, SIZE * 0.058, col)

    # 中央终端核心
    R = SIZE * 0.18
    render.glow(base, (c, c), R * 3.2, (60, 130, 200))
    # 旋转弧
    for k in range(4):
        ang = k * 40
        rr = R + (16 + k * 14)
        pygame.draw.arc(base, tuple(min(255, int(x * (1.0 - k * 0.12))) for x in CY_HI),
                        (c - rr, c - rr, rr * 2, rr * 2),
                        math.radians(ang), math.radians(ang + 70), 7)
    render.aacircle(base, (40, 90, 140), (c, c), int(R * 1.02))
    render.aacircle(base, (90, 175, 235), (c, c), int(R * 0.80))
    render.aaring(base, CY_HI, (c, c), int(R * 0.80), 5)
    render.glow(base, (c, c), R * 1.7, (90, 170, 240))
    render.aacircle(base, (180, 230, 255), (c, c), int(R * 0.46))
    render.aacircle(base, (245, 252, 255), (c, c), int(R * 0.24))

    # 轻暗角（仅压边缘）
    vig = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    for r in range(int(maxd), 0, -6):
        a = int(70 * (r / maxd) ** 3.0)
        pygame.draw.circle(vig, (0, 0, 0, a), (int(c), int(c)), r)
    base.blit(vig, (0, 0))

    # 仅用白色圆角蒙版裁角（保留 RGB），再描青色细边
    radius = int(SIZE * 0.225)
    base.blit(_round_mask(SIZE, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.rect(base, (90, 160, 210), (3, 3, SIZE - 6, SIZE - 6),
                     width=5, border_radius=radius)

    os.makedirs("assets", exist_ok=True)
    pygame.image.save(base, "assets/icon_1024.png")
    print("saved assets/icon_1024.png")
    pygame.quit()


if __name__ == "__main__":
    build()
