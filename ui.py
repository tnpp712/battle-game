"""HUD：霓虹风信息栏、建造栏（带图标）、状态横幅、血条。"""
import math
import pygame
import config as C
import render


def draw_hp_bar(surf, x, y, w, h, frac):
    frac = max(0.0, min(1.0, frac))
    x, y, w, h = int(x), int(y), int(w), int(h)
    pygame.draw.rect(surf, C.C_HP_BACK, (x, y, w, h), border_radius=h // 2)
    if frac > 0.6:
        col = C.C_HP_GOOD
    elif frac > 0.3:
        col = C.C_HP_MID
    else:
        col = C.C_HP_LOW
    if frac > 0:
        pygame.draw.rect(surf, col, (x, y, max(h, int(w * frac)), h), border_radius=h // 2)


def _panel(surf, rect, fill, border, sel=False):
    pygame.draw.rect(surf, fill, rect, border_radius=8)
    if sel:
        glow_rect = rect.inflate(6, 6)
        render.glow(surf, glow_rect.center, max(glow_rect.w, glow_rect.h),
                    (40, 50, 30))
    pygame.draw.rect(surf, border, rect, 2, border_radius=8)
    pygame.draw.line(surf, tuple(min(255, c + 25) for c in fill),
                     (rect.left + 8, rect.top + 1), (rect.right - 8, rect.top + 1))


def _res_icon(surf, cx, cy):
    pts = [(cx, cy - 8), (cx + 7, cy), (cx, cy + 8), (cx - 7, cy)]
    render.glow(surf, (cx, cy), 16, (40, 90, 50))
    render.aapolygon(surf, (130, 230, 150), pts)
    render.aapolygon(surf, (200, 255, 210), [(cx, cy - 8), (cx + 7, cy), (cx, cy)])


def _build_icon(surf, name, cx, cy):
    if name == "wall":
        r = pygame.Rect(0, 0, 26, 12); r.center = (cx, cy)
        pygame.draw.rect(surf, (190, 175, 130), r, border_radius=2)
        pygame.draw.rect(surf, (220, 205, 160), r, 1, border_radius=2)
    elif name == "tower":
        render.aacircle(surf, (180, 130, 220), (cx, cy), 9)
        render.aaring(surf, (220, 190, 255), (cx, cy), 9, 1)
        pygame.draw.line(surf, (230, 210, 255), (cx, cy), (cx + 12, cy), 3)
    elif name == "repair":
        pygame.draw.rect(surf, (140, 235, 170), (cx - 3, cy - 9, 6, 18), border_radius=2)
        pygame.draw.rect(surf, (140, 235, 170), (cx - 9, cy - 3, 18, 6), border_radius=2)
    elif name == "shield":
        pts = [(cx, cy - 10), (cx + 9, cy - 4), (cx + 7, cy + 8),
               (cx, cy + 11), (cx - 7, cy + 8), (cx - 9, cy - 4)]
        render.aapolygon(surf, (110, 180, 255), pts)
        render.aapolygon(surf, (180, 220, 255), [(cx, cy - 10), (cx + 9, cy - 4), (cx, cy + 2)])
    elif name == "radar":
        render.aaring(surf, (120, 220, 255), (cx, cy), 10, 1)
        render.aaring(surf, (120, 220, 255), (cx, cy), 6, 1)
        pygame.draw.line(surf, (160, 240, 255), (cx, cy), (cx + 9, cy - 7), 2)


class HUD:
    def __init__(self, fonts):
        self.f_small = fonts["small"]
        self.f_mid = fonts["mid"]
        self.f_big = fonts["big"]
        self.f_tiny = fonts["tiny"]
        self.buttons = {}

    def _text(self, surf, txt, x, y, font, color=C.C_TEXT, center=False):
        img = font.render(txt, True, color)
        r = img.get_rect()
        if center:
            r.center = (x, y)
        else:
            r.topleft = (x, y)
        surf.blit(img, r)
        return r

    def _energy_bar(self, surf, x, y, w, h, frac):
        frac = max(0.0, min(1.0, frac))
        pygame.draw.rect(surf, (24, 30, 44), (x, y, w, h), border_radius=h // 2)
        if frac > 0:
            pygame.draw.rect(surf, (90, 170, 255), (x, y, max(h, int(w * frac)), h),
                             border_radius=h // 2)

    def _ability_slot(self, surf, m, slot, game, x, y, w, h):
        spec = m.ability(slot)
        if spec is None:
            return
        cd = m.ability_timers[slot]
        ready = cd <= 0 and m.energy >= spec["cost"]
        aiming = (game.aiming is not None and game.aiming.get("mech") is m
                  and game.aiming.get("slot") == slot)
        rect = pygame.Rect(x, y, w, h)
        fill = (40, 54, 40) if aiming else (28, 34, 48) if ready else (22, 24, 34)
        border = C.C_SELECT if aiming else (70, 140, 110) if ready else C.C_HUD_LINE
        pygame.draw.rect(surf, fill, rect, border_radius=6)
        pygame.draw.rect(surf, border, rect, 2, border_radius=6)
        # 冷却灰罩（从上往下覆盖未就绪部分）
        if cd > 0:
            frac = min(1.0, cd / spec["cd"])
            ov = pygame.Surface((w - 4, int((h - 4) * frac)), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 150))
            surf.blit(ov, (x + 2, y + 2))
        # 按键徽标 + 名称
        kcol = C.C_TEXT_GOOD if ready else C.C_TEXT_DIM
        self._text(surf, spec["key"], x + 8, y + 5, self.f_small, kcol)
        self._text(surf, spec["name"], x + 30, y + 6, self.f_tiny,
                   C.C_TEXT if ready else C.C_TEXT_DIM)
        # 底部信息：冷却剩余 或 能量消耗
        if cd > 0:
            info, icol = f"冷却 {cd:.1f}s", C.C_TEXT_DIM
        elif m.energy < spec["cost"]:
            info, icol = f"能量 {spec['cost']}", C.C_TEXT_BAD
        else:
            info, icol = f"耗能 {spec['cost']}", (120, 180, 240)
        self._text(surf, info, x + 30, y + 24, self.f_tiny, icol)

    def draw(self, surf, game):
        hud_y = C.SCREEN_H - C.HUD_H
        pygame.draw.rect(surf, C.C_HUD_BG, (0, hud_y, C.SCREEN_W, C.HUD_H))
        # 顶部霓虹分隔线
        pygame.draw.line(surf, (60, 110, 170), (0, hud_y), (C.SCREEN_W, hud_y), 2)
        render.glow(surf, (C.SCREEN_W // 2, hud_y), 200, (10, 24, 40))

        mouse = pygame.mouse.get_pos()

        # --- 左：状态 ---
        _res_icon(surf, 30, hud_y + 26)
        self._text(surf, f"{int(game.resources)}", 46, hud_y + 14, self.f_mid, C.C_TEXT_GOOD)
        self._text(surf, f"波次 {game.wave_index + 1}/{len(C.WAVES)}", 20, hud_y + 48, self.f_small)
        t = game.terminal
        self._text(surf, "终端", 20, hud_y + 78, self.f_tiny, C.C_TEXT_DIM)
        draw_hp_bar(surf, 62, hud_y + 80, 180, 12, t.hp / t.max_hp)
        self._text(surf, f"{int(t.hp)}/{t.max_hp}", 250, hud_y + 77, self.f_tiny, C.C_TEXT_DIM)
        self._text(surf, f"维修 Lv{t.repair_lv}  护盾 Lv{t.shield_lv}  雷达 Lv{t.radar_lv}",
                   20, hud_y + 104, self.f_tiny, C.C_TEXT_DIM)

        # --- 中：建造栏 ---
        self.buttons.clear()
        bx, by, bw, bh, gap = 380, hud_y + 16, 152, 50, 12

        def cost_for(name):
            if name in C.BUILD_ITEMS:
                return C.BUILD_ITEMS[name]["cost"]
            lv = getattr(t, name + "_lv")
            return C.BASE_UPGRADES[name]["base_cost"] + lv * 40

        items = [
            ("wall", C.BUILD_ITEMS["wall"]["label"]),
            ("tower", C.BUILD_ITEMS["tower"]["label"]),
            ("repair", C.BASE_UPGRADES["repair"]["label"]),
            ("shield", C.BASE_UPGRADES["shield"]["label"]),
            ("radar", C.BASE_UPGRADES["radar"]["label"]),
        ]
        for i, (name, label) in enumerate(items):
            col, row = i % 3, i // 3
            rect = pygame.Rect(bx + col * (bw + gap), by + row * (bh + gap), bw, bh)
            self.buttons[name] = rect
            cost = cost_for(name)
            selected = (game.build_selection == name)
            hover = rect.collidepoint(mouse)
            afford = game.resources >= cost
            fill = (44, 56, 40) if selected else (34, 42, 58) if hover else (22, 26, 38)
            border = C.C_SELECT if selected else (70, 110, 160) if hover else C.C_HUD_LINE
            _panel(surf, rect, fill, border, sel=selected)
            _build_icon(surf, name, rect.left + 22, rect.centery)
            self._text(surf, label, rect.left + 42, rect.top + 8, self.f_tiny,
                       C.C_TEXT if afford else C.C_TEXT_BAD)
            self._text(surf, f"花费 {cost}", rect.left + 42, rect.top + 27, self.f_tiny,
                       C.C_TEXT_GOOD if afford else C.C_TEXT_BAD)

        # --- 右：所选机兵 ---
        rx = 900
        m = game.selected_mech
        if m is not None and m.alive:
            self._text(surf, f"机兵 · {m.type}", rx, hud_y + 8, self.f_mid, m.color)
            draw_hp_bar(surf, rx, hud_y + 38, 200, 10, m.hp / m.max_hp)
            self._text(surf, f"{int(m.hp)}/{m.max_hp}", rx + 208, hud_y + 33, self.f_tiny, C.C_TEXT_DIM)
            # 能量条 + 数值
            self._energy_bar(surf, rx, hud_y + 53, 200, 7, m.energy / m.max_energy)
            self._text(surf, f"{int(m.energy)}/{m.max_energy}", rx + 208, hud_y + 49, self.f_tiny, (120, 185, 245))
            if m.shield > 0:
                self._text(surf, f"盾 {int(m.shield)}", rx + 150, hud_y + 14, self.f_small, (130, 210, 255))
            # 双技能槽
            for slot in range(2):
                self._ability_slot(surf, m, slot, game,
                                   rx + slot * 188, hud_y + 70, 178, 44)
        else:
            self._text(surf, "点击选择机兵", rx, hud_y + 14, self.f_mid, C.C_TEXT_DIM)
            self._text(surf, "空格=暂停下令   Q/E=技能   ESC=取消", rx, hud_y + 50, self.f_tiny, C.C_TEXT_DIM)
            if game.state == "BUILD":
                self._text(surf, "N=开始下一波", rx, hud_y + 74, self.f_small, C.C_TEXT_WARN)

        self._draw_globals(surf, game)
        self._draw_banner(surf, game)

    def _draw_globals(self, surf, game):
        """左上角：终端全局技能（Z/X/C），消耗资源。"""
        x, y, w, h, gap = 14, 12, 116, 36, 8
        active = (game.state == "WAVE")
        for name, spec in C.GLOBAL_SKILLS.items():
            cd = game.global_cd.get(name, 0)
            afford = game.resources >= spec["cost"]
            ready = active and cd <= 0 and afford
            rect = pygame.Rect(x, y, w, h)
            fill = (28, 36, 50) if ready else (20, 24, 34)
            border = (90, 160, 210) if ready else C.C_HUD_LINE
            pygame.draw.rect(surf, fill, rect, border_radius=6)
            pygame.draw.rect(surf, border, rect, 2, border_radius=6)
            if cd > 0:
                frac = min(1.0, cd / spec["cd"])
                ov = pygame.Surface((w - 4, int((h - 4) * frac)), pygame.SRCALPHA)
                ov.fill((0, 0, 0, 150))
                surf.blit(ov, (x + 2, y + 2))
            kcol = C.C_TEXT_GOOD if ready else C.C_TEXT_DIM
            self._text(surf, spec["key"], x + 8, y + 3, self.f_small, kcol)
            self._text(surf, spec["name"], x + 30, y + 4, self.f_tiny,
                       C.C_TEXT if ready else C.C_TEXT_DIM)
            info = f"冷却 {cd:.1f}s" if cd > 0 else f"资源 {spec['cost']}"
            icol = C.C_TEXT_DIM if cd > 0 else (C.C_TEXT_GOOD if afford else C.C_TEXT_BAD)
            self._text(surf, info, x + 30, y + 19, self.f_tiny, icol)
            x += w + gap

    def _draw_banner(self, surf, game):
        if game.state == "BUILD":
            self._text(surf, f"建造阶段 — 布防后按 N 开始第 {game.wave_index + 1} 波",
                       C.SCREEN_W // 2, 26, self.f_mid, C.C_TEXT_WARN, center=True)
        elif game.state == "WAVE":
            if game.paused:
                self._text(surf, "⏸ 暂停 — 下达指令中（空格继续）", C.SCREEN_W // 2, 26,
                           self.f_mid, C.C_SELECT, center=True)
            self._text(surf, f"第 {game.wave_index + 1} 波   剩余敌人 {game.enemies_remaining()}",
                       C.SCREEN_W // 2, 52, self.f_small, C.C_TEXT_DIM, center=True)
        elif game.state == "WON":
            self._center_big(surf, "防卫成功！", C.C_TEXT_GOOD, "按 R 重新开始")
        elif game.state == "LOST":
            self._center_big(surf, "终端被摧毁…", C.C_TEXT_BAD, "按 R 重新开始")

    def _center_big(self, surf, title, color, sub):
        cx, cy = C.SCREEN_W // 2, (C.SCREEN_H - C.HUD_H) // 2
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H - C.HUD_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surf.blit(overlay, (0, 0))
        render.glow(surf, (cx, cy - 10), 240, tuple(c // 4 for c in color))
        self._text(surf, title, cx, cy - 20, self.f_big, color, center=True)
        self._text(surf, sub, cx, cy + 30, self.f_mid, C.C_TEXT, center=True)
