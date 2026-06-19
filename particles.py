"""粒子系统：命中火花、死亡爆炸、推进器拖尾、伤害飘字。"""
import math
import random
import pygame
from pygame.math import Vector2

import render


class Particles:
    def __init__(self):
        self.items = []   # 发光小颗粒
        self.texts = []   # 伤害飘字
        self.rings = []   # 爆炸冲击环

    # ---- 生成 ----
    def spark(self, pos, color, n=6, speed=150, life=0.35, size=(1.6, 3.2)):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(speed * 0.3, speed)
            self.items.append(dict(
                pos=Vector2(pos), vel=Vector2(math.cos(ang), math.sin(ang)) * sp,
                life=life, max=life, color=color, size=random.uniform(*size)))

    def explosion(self, pos, color, n=18):
        self.spark(pos, color, n=n, speed=240, life=0.55, size=(2.0, 4.0))
        self.spark(pos, (255, 240, 200), n=max(4, n // 3), speed=120, life=0.4)
        self.rings.append(dict(pos=Vector2(pos), r=6, max_r=34, life=0.35, max=0.35, color=color))

    def thruster(self, pos, heading, color):
        ang = math.atan2(heading.y, heading.x) + math.pi + random.uniform(-0.4, 0.4)
        sp = random.uniform(25, 60)
        self.items.append(dict(
            pos=Vector2(pos), vel=Vector2(math.cos(ang), math.sin(ang)) * sp,
            life=0.32, max=0.32, color=color, size=random.uniform(1.8, 3.0)))

    def number(self, pos, amount, color):
        self.texts.append(dict(
            pos=Vector2(pos) + Vector2(random.uniform(-7, 7), -8),
            vel=Vector2(random.uniform(-10, 10), -46),
            life=0.85, max=0.85, text=str(int(amount)), color=color))

    # ---- 更新 ----
    def update(self, dt):
        for p in self.items:
            p["pos"] += p["vel"] * dt
            p["vel"] *= max(0.0, 1 - 3.0 * dt)
            p["life"] -= dt
        self.items = [p for p in self.items if p["life"] > 0]

        for t in self.texts:
            t["pos"] += t["vel"] * dt
            t["vel"].y += 60 * dt        # 轻微回落
            t["life"] -= dt
        self.texts = [t for t in self.texts if t["life"] > 0]

        for r in self.rings:
            f = 1 - r["life"] / r["max"]
            r["r"] = r["r"] + (r["max_r"] - 6) * dt / r["max"]
            r["life"] -= dt
        self.rings = [r for r in self.rings if r["life"] > 0]

    # ---- 绘制 ----
    def draw(self, surf, s=1):
        for r in self.rings:
            f = max(0.0, r["life"] / r["max"])
            col = tuple(int(c * f) for c in r["color"])
            render.aaring(surf, col, (r["pos"].x * s, r["pos"].y * s), r["r"] * s, max(1, round(2 * s)))
        for p in self.items:
            f = max(0.0, p["life"] / p["max"])
            rad = p["size"] * (0.4 + 0.6 * f) * s
            render.glow(surf, (p["pos"].x * s, p["pos"].y * s), rad * 3.2, p["color"])
            render.aacircle(surf, p["color"], (p["pos"].x * s, p["pos"].y * s), max(1, rad))

    def draw_text(self, surf, font, s=1):
        for t in self.texts:
            f = t["life"] / t["max"]
            img = font.render(t["text"], True, t["color"])
            img.set_alpha(int(255 * min(1.0, f * 1.5)))
            surf.blit(img, img.get_rect(center=(int(t["pos"].x * s), int(t["pos"].y * s))))
