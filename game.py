"""核心游戏逻辑：状态机、地图、事件处理、更新与绘制。"""
import math
import random
import pygame
from pygame.math import Vector2

import config as C
from geometry import path_blocked, circle_rect_collide, resolve_circle_rects
from entities import Terminal, Mech, Enemy, Tower, Wall, Beam
from ui import HUD, draw_hp_bar
from pathfield import FlowField, find_path
import sprites
import render
import audio
from particles import Particles
from sprites import lighten


class Game:
    def __init__(self, fonts, wfonts=None):
        self.fonts = fonts
        self.wfonts = wfonts or fonts      # 世界空间字体（在 2× 画布上绘制）
        self.hud = HUD(fonts)
        self.field = pygame.Rect(*C.FIELD_RECT)
        self.rs = C.RENDER_SCALE
        # 战场超采样画布（2×）与降采样缓冲
        self.scene = pygame.Surface((C.SCREEN_W * self.rs, self.field.bottom * self.rs))
        self._down = pygame.Surface((C.SCREEN_W, self.field.bottom))
        self._red_vig = self._build_red_vignette()    # 终端受击红闪叠层
        self.reset()

    def _build_red_vignette(self):
        """边缘渐强的红色暗角，叠加在窗口战场区，强度按 term_flash 调制。"""
        surf = pygame.Surface((C.SCREEN_W, self.field.bottom), pygame.SRCALPHA)
        depth = 130
        for i in range(depth):
            a = int(170 * (1 - i / depth) ** 2)
            pygame.draw.rect(surf, (255, 45, 45, a),
                             (i, i, C.SCREEN_W - 2 * i, self.field.bottom - 2 * i), 1)
        return surf

    def add_shake(self, mag):
        self.shake = min(18.0, self.shake + mag)

    # ---------------- 初始化 ----------------
    def reset(self):
        self.terminal = Terminal((self.field.centerx, self.field.centery))
        self.terrain = self._gen_terrain()
        self.walls = []
        self.towers = []
        self.enemies = []
        self.beams = []
        self.mechs = self._spawn_squad()

        self.resources = C.START_RESOURCES
        self.wave_index = 0
        self.spawn_queue = []
        self.spawn_timer = 0.0

        self.state = "BUILD"        # BUILD / WAVE / WON / LOST
        self.paused = False
        self.build_selection = None
        self.wall_vertical = False
        self.selected = []          # 当前选中的机兵组
        self.selected_mech = None   # 主选（用于 HUD/技能），= selected[0]
        self.groups = {i: [] for i in range(1, 7)}   # 数字编组
        self._press = None          # 左键按下信息：("mech"/"empty", 起点)
        self.box = None             # 框选矩形 (start, end) 或 None
        self.aiming = None          # dict(radius, src, cast) 等待点位的技能瞄准
        self.deployables = []       # 限时召唤物（哨戒炮/力场/无人机）
        self.global_cd = {k: 0.0 for k in C.GLOBAL_SKILLS}
        self.drawing_path = False
        self.draw_points = []
        self.path_valid = True
        self.message = ""
        self.message_timer = 0.0
        self.anim_time = 0.0
        # 打击感
        self.shake = 0.0            # 当前震屏幅度（像素）
        self.hitstop = 0.0          # >0 时战斗短暂冻结（命中顿帧）
        self.term_flash = 0.0       # 终端受击红闪强度 0..1
        self.threat_dirs = {"top": 0, "bottom": 0, "left": 0, "right": 0}
        self._prepare_wave()        # 预排第一波（出怪边 + 方向预警）

        self.flow = FlowField(self.field)
        self._flow_dirty = False
        self._rebuild_flow()

        self.particles = Particles()
        self.bg = render.build_background(C.SCREEN_W * self.rs, self.field.bottom * self.rs,
                                          self.terminal.pos * self.rs, s=self.rs)

    def _gen_terrain(self):
        rects = []
        cx, cy = self.terminal.pos
        attempts = 0
        while len(rects) < 7 and attempts < 200:
            attempts += 1
            w = random.randint(60, 160)
            h = random.randint(40, 130)
            x = random.randint(self.field.left + 40, self.field.right - w - 40)
            y = random.randint(self.field.top + 40, self.field.bottom - h - 40)
            r = pygame.Rect(x, y, w, h)
            # 远离终端与机兵初始环（半径约 126），避免堵死核心或压住机兵
            ex = max(r.left, min(cx, r.right))
            ey = max(r.top, min(cy, r.bottom))
            if Vector2(ex, ey).distance_to(Vector2(cx, cy)) < 150:
                continue
            if any(r.inflate(50, 50).colliderect(o) for o in rects):
                continue
            rects.append(r)
        return rects

    def _spawn_squad(self):
        mechs = []
        cx, cy = self.terminal.pos
        n = len(C.STARTING_SQUAD)
        import math
        for i, t in enumerate(C.STARTING_SQUAD):
            ang = (i / n) * math.tau
            p = Vector2(cx + math.cos(ang) * 110, cy + math.sin(ang) * 110)
            mechs.append(Mech(t, p))
        return mechs

    # ---------------- 障碍 ----------------
    def obstacle_rects(self):
        return self.terrain + [w.rect for w in self.walls]

    def _rebuild_flow(self):
        self.flow.compute(self.terminal.pos, self.terminal.radius, self.obstacle_rects())
        self._flow_dirty = False

    # ---------------- 波次 ----------------
    def enemies_remaining(self):
        return len(self.enemies) + len(self.spawn_queue)

    def _prepare_wave(self):
        """进入 BUILD 时预排下一波：给每个敌人预定出怪边，供方向预警与出怪共用。"""
        self.threat_dirs = {"top": 0, "bottom": 0, "left": 0, "right": 0}
        self.spawn_queue = []
        if self.wave_index >= len(C.WAVES):
            return
        sides = ("top", "bottom", "left", "right")
        plan = []
        for tname, count in C.WAVES[self.wave_index]["enemies"]:
            for _ in range(count):
                side = random.choice(sides)
                plan.append((tname, side))
                self.threat_dirs[side] += 1
        random.shuffle(plan)
        self.spawn_queue = plan

    def start_wave(self):
        if self.state != "BUILD":
            return
        if not self.spawn_queue:
            self._prepare_wave()
        self.spawn_timer = 0.5
        self.state = "WAVE"
        audio.play("wave")
        self.paused = False

    def _spawn_one(self):
        tname, side = self.spawn_queue.pop(0)
        if side == "top":
            p = (random.randint(self.field.left, self.field.right), self.field.top + 6)
        elif side == "bottom":
            p = (random.randint(self.field.left, self.field.right), self.field.bottom - 6)
        elif side == "left":
            p = (self.field.left + 6, random.randint(self.field.top, self.field.bottom))
        else:
            p = (self.field.right - 6, random.randint(self.field.top, self.field.bottom))
        self.enemies.append(Enemy(tname, p))

    def _wave_cleared(self):
        reward = C.WAVES[self.wave_index]["reward"]
        self.resources += reward
        self._flash(f"第 {self.wave_index + 1} 波清除！获得资源 {reward}")
        self.wave_index += 1
        if self.wave_index >= len(C.WAVES):
            self.state = "WON"
            audio.play("win")
        else:
            self.state = "BUILD"
            audio.play("build")
        # 复活阵亡机兵（保留游戏推进感），回满血
        for m in self.mechs:
            if not m.alive:
                m.hp = m.max_hp * 0.5
                m._death_done = False
            # 清空战斗态：增益/生根/护盾在 BUILD 期不会自然推进，必须显式复位，
            # 并为下一波补满能量、刷新冷却（每波以备战状态开局）
            m.dmg_mult = m.range_mult = m.atkspd_mult = m.move_mult = 1.0
            m.buff_timer = 0.0
            m.buff_kind = None
            m.root_timer = 0.0
            m.shield = 0.0
            m.shield_timer = 0.0
            m.energy = m.max_energy
            m.ability_timers = [0.0 for _ in m.abilities]
        self.deployables = []       # 限时召唤物不跨波保留
        self.aiming = None
        for m in self.mechs:
            m.selected = False
        self.selected = []
        self.selected_mech = None
        self._prepare_wave()        # 预排下一波（出怪边 + 方向预警）

    def _flash(self, msg):
        self.message = msg
        self.message_timer = 3.0

    # ---------------- 事件 ----------------
    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            self._on_key(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(ev)
        elif ev.type == pygame.MOUSEMOTION:
            if self.drawing_path:
                self._extend_path(Vector2(ev.pos))
            elif self.box is not None:
                self.box = (self.box[0], Vector2(ev.pos))
            elif self._press is not None:
                kind, start = self._press[0], self._press[1]
                p = Vector2(ev.pos)
                if start.distance_to(p) > 6 and ev.pos[1] < C.SCREEN_H - C.HUD_H:
                    if kind == "mech" and self.selected_mech is not None and self.selected_mech.alive:
                        self.drawing_path = True
                        self.draw_points = [Vector2(self.selected_mech.pos), p]
                        self.path_valid = True
                    else:           # 空地拖拽 → 框选
                        self.box = (start, p)
                    self._press = None
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1:
                if self.drawing_path:
                    self._finish_path()
                elif self.box is not None:
                    self._set_selection(self._mechs_in_rect(*self.box))
                    self.box = None
                elif self._press is not None:
                    if self._press[0] == "mech":
                        # 在机兵上普通点击（未拖拽）→ 收敛为单选
                        self._set_selection([self._press[2]])
                    elif self.selected:     # 空地点击：有选中则移动到点
                        self._move_group(self._press[1])
                    else:
                        self._set_selection([])
                self._press = None
        elif ev.type == pygame.MOUSEWHEEL:
            if self.build_selection == "wall":
                self.wall_vertical = not self.wall_vertical

    def _on_key(self, key):
        if key == pygame.K_r:
            self.reset()
            return
        if self.state in ("WON", "LOST"):
            return
        if key == pygame.K_SPACE and self.state == "WAVE":
            self.paused = not self.paused
        elif key == pygame.K_n and self.state == "BUILD":
            self.start_wave()
        elif key == pygame.K_ESCAPE:
            if self.aiming is not None:
                self.aiming = None
                return
            self.build_selection = None
            self._set_selection([])
        elif key == pygame.K_q:
            self._try_ability(0)
        elif key == pygame.K_e:
            self._try_ability(1)
        elif key == pygame.K_z:
            self._try_global("orbital")
        elif key == pygame.K_x:
            self._try_global("overclock")
        elif key == pygame.K_c:
            self._try_global("timewarp")
        elif key == pygame.K_m:
            self._flash("已静音" if audio.toggle_mute() else "已取消静音")
        elif key == pygame.K_TAB:
            if self.build_selection == "wall":
                self.wall_vertical = not self.wall_vertical
        elif pygame.K_1 <= key <= pygame.K_6:
            self._number_key(key - pygame.K_0)

    def _number_key(self, n):
        """数字键：Ctrl 设编组；战斗中选组；否则（1-5）建造快捷键。"""
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_CTRL:
            self.groups[n] = [m for m in self.selected if m.alive]
            self._flash(f"编组 {n}：{len(self.groups[n])} 兵")
            return
        if self.state == "WAVE" and self.groups.get(n):
            alive = [m for m in self.groups[n] if m.alive]
            if alive:
                self._set_selection(alive)
                return
        # 回落到建造快捷键
        builds = {1: ("wall", "toggle"), 2: ("tower", "toggle"),
                  3: ("repair", "buy"), 4: ("shield", "buy"), 5: ("radar", "buy")}
        if n in builds:
            name, kind = builds[n]
            if kind == "toggle":
                self._toggle_build(name)
            else:
                self._buy_upgrade(name)

    def _toggle_build(self, name):
        self.build_selection = None if self.build_selection == name else name
        for m in self.mechs:
            m.selected = False
        self.selected = []
        self.selected_mech = None

    # ---------------- 技能 ----------------
    def _try_ability(self, slot):
        m = self.selected_mech
        if m is None or not m.alive or self.state != "WAVE":
            return
        spec = m.ability(slot)
        if spec is None:
            return
        ok, reason = m.can_use(slot)
        if not ok:
            if reason:
                self._flash(reason)
            return
        if spec["target"] == "self":
            if m.use_ability(self, slot):
                audio.play("cast")
        else:
            def cast(pos, m=m, slot=slot, spec=spec):
                tgt = pos
                if spec["target"] == "enemy":
                    e = self._enemy_at(pos)
                    tgt = e.pos if e is not None else pos
                if m.use_ability(self, slot, tgt):
                    audio.play("cast")
                else:
                    _, why = m.can_use(slot)
                    if why:
                        self._flash(why)
            self.aiming = dict(radius=spec.get("radius", 0), src=Vector2(m.pos),
                               cast=cast, name=spec["name"], mech=m, slot=slot)
            self._flash(f"{spec['name']}：左键选择目标位置（右键/ESC 取消）")

    def _cast_aimed(self, pos):
        cast = self.aiming["cast"]
        self.aiming = None
        cast(pos)

    # ---------------- 终端全局技能 ----------------
    def _try_global(self, name):
        if self.state != "WAVE":
            return
        spec = C.GLOBAL_SKILLS[name]
        if self.global_cd[name] > 0:
            self._flash("全局技能冷却中")
            return
        if self.resources < spec["cost"]:
            self._flash("资源不足")
            return
        if spec["target"] == "self":
            self._do_global(name, None)
        else:
            self.aiming = dict(radius=spec.get("radius", 0), src=None,
                               cast=lambda pos, n=name: self._do_global(n, pos),
                               name=spec["name"])
            self._flash(f"{spec['name']}：左键选择目标位置（右键/ESC 取消）")

    def _do_global(self, name, target):
        spec = C.GLOBAL_SKILLS[name]
        if self.global_cd[name] > 0 or self.resources < spec["cost"]:
            return
        self.resources -= spec["cost"]
        self.global_cd[name] = spec["cd"]
        eff = spec["effect"]
        audio.play("cast")
        if eff == "orbital" and target is not None:
            c = Vector2(target)
            self.particles.explosion(c, (255, 200, 120), n=30)
            audio.play("explosion", throttle=0.05)
            self.particles.rings.append(dict(pos=Vector2(c), r=14, max_r=spec["radius"],
                                             life=0.6, max=0.6, color=(255, 180, 110)))
            for e in list(self.enemies):
                if c.distance_to(e.pos) <= spec["radius"]:
                    e.take_damage(spec["value"])
                    self.particles.spark(e.pos, (255, 200, 140), n=6)
        elif eff == "overclock":
            for m in self.mechs:
                if m.alive:
                    m.atkspd_mult = spec["value"]
                    m.dmg_mult = 1.3
                    m.range_mult = 1.0
                    m.move_mult = 1.2
                    m.buff_timer = spec["duration"]
                    m.buff_kind = "overdrive"
        elif eff == "timewarp":
            for e in self.enemies:
                e.apply_slow(spec["value"], spec["duration"])

    def _on_mouse_down(self, ev):
        pos = Vector2(ev.pos)
        # HUD 区域点击
        if ev.pos[1] >= C.SCREEN_H - C.HUD_H:
            self.aiming = None
            if ev.button == 1:
                self._click_hud(ev.pos)
            return
        if self.state in ("WON", "LOST"):
            return

        # 技能瞄准中：左键释放，右键取消
        if self.aiming is not None:
            if ev.button == 1:
                self._cast_aimed(pos)
            elif ev.button == 3:
                self.aiming = None
            return

        if ev.button == 1:
            # 全局技能栏（左上角）可点击释放
            for gname, rect in self.hud.global_buttons.items():
                if rect.collidepoint(ev.pos):
                    self._try_global(gname)
                    return
            if self.build_selection in ("wall", "tower"):
                self._place_build(pos)
                return
            shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
            m = self._mech_at(pos)
            if m is not None:
                if shift:
                    self._toggle_select(m)
                    self._press = None
                else:
                    if m not in self.selected:
                        self._set_selection([m])
                    self._press = ("mech", Vector2(pos), m)
            else:
                self._press = ("empty", Vector2(pos))
        elif ev.button == 3:
            grp = [x for x in self.selected if x.alive]
            if grp:
                e = self._enemy_at(pos)
                if e is not None:
                    for x in grp:
                        x.forced_target = e
                    self._flash("已指定攻击目标")
                else:
                    for x in grp:
                        x.stop()

    def _click_hud(self, pos):
        # 技能槽（所选机兵）可点击释放
        for slot, rect in self.hud.ability_buttons.items():
            if rect.collidepoint(pos):
                self._try_ability(slot)
                return
        for name, rect in self.hud.buttons.items():
            if rect.collidepoint(pos):
                if name in ("wall", "tower"):
                    self._toggle_build(name)
                else:
                    self._buy_upgrade(name)
                return

    def _set_selection(self, mechs):
        """设定选中组：刷新各机兵 selected 标记，主选取第一个。"""
        self.build_selection = None
        chosen = [m for m in mechs if m.alive]
        for m in self.mechs:
            m.selected = m in chosen
        self.selected = chosen
        self.selected_mech = chosen[0] if chosen else None

    def _toggle_select(self, m):
        sel = list(self.selected)
        if m in sel:
            sel.remove(m)
        else:
            sel.append(m)
        self._set_selection(sel)

    def _mechs_in_rect(self, a, b):
        r = pygame.Rect(min(a.x, b.x), min(a.y, b.y), abs(a.x - b.x), abs(a.y - b.y))
        return [m for m in self.mechs if m.alive and r.collidepoint(m.pos.x, m.pos.y)]

    def _mech_at(self, pos):
        best = None
        bestd = 1e18
        for m in self.mechs:
            if not m.alive:
                continue
            d = m.pos.distance_to(pos)
            if d <= m.radius + 6 and d < bestd:
                bestd = d
                best = m
        return best

    def _enemy_at(self, pos):
        for e in self.enemies:
            if e.pos.distance_to(pos) <= e.radius + 6:
                return e
        return None

    # ---------------- 路径绘制 ----------------
    def _extend_path(self, pos):
        if not self.field.collidepoint(pos.x, pos.y):
            pos.x = max(self.field.left, min(pos.x, self.field.right))
            pos.y = max(self.field.top, min(pos.y, self.field.bottom))
        if self.draw_points[-1].distance_to(pos) >= 14:
            self.draw_points.append(Vector2(pos))
            self.path_valid = not path_blocked(self.draw_points, self.obstacle_rects())

    def _finish_path(self):
        self.drawing_path = False
        pts = self.draw_points
        self.draw_points = []
        grp = [m for m in self.selected if m.alive]
        if len(pts) < 2 or not grp:
            return
        if len(grp) > 1:
            # 多选：把徒手路径终点当作集结点，编队移动
            self._move_group(pts[-1])
            return
        m = grp[0]
        obstacles = self.obstacle_rects()
        if not path_blocked(pts, obstacles):
            m.set_path(pts[1:])     # 徒手路径可行，直接采用（去掉首点）
            m.forced_target = None
        else:
            goal = pts[-1]
            route = find_path(self.field, obstacles, m.pos, goal, clearance=m.radius + 2)
            if route and len(route) >= 2:
                m.set_path(route[1:])
                m.forced_target = None
                self._flash("自动绕行")
            else:
                self._flash("无法到达目标")

    def _formation(self, goal, n):
        """围绕 goal 排出 n 个不重叠的集结点（网格阵）。"""
        goal = Vector2(goal)
        if n <= 1:
            return [goal]
        spacing = 42
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        slots = []
        for i in range(n):
            r, c = divmod(i, cols)
            x = goal.x + (c - (cols - 1) / 2) * spacing
            y = goal.y + (r - (rows - 1) / 2) * spacing
            x = max(self.field.left + 10, min(self.field.right - 10, x))
            y = max(self.field.top + 10, min(self.field.bottom - 10, y))
            slots.append(Vector2(x, y))
        return slots

    def _move_group(self, goal):
        """编队移动：每个机兵分配一个集结点，逐个寻路。"""
        grp = [m for m in self.selected if m.alive]
        if not grp:
            return
        obstacles = self.obstacle_rects()
        slots = self._formation(Vector2(goal), len(grp))
        blocked = 0
        for m, slot in zip(grp, slots):
            if not path_blocked([m.pos, slot], obstacles):
                m.set_path([slot])
                m.forced_target = None
            else:
                route = find_path(self.field, obstacles, m.pos, slot, clearance=m.radius + 2)
                if route and len(route) >= 2:
                    m.set_path(route[1:])
                    m.forced_target = None
                else:
                    blocked += 1    # 无法到达：不设置穿障路径（与单选徒手路径一致）
        if blocked:
            self._flash("部分机兵无法到达目标")

    # ---------------- 建造 ----------------
    def _place_build(self, pos):
        data = C.BUILD_ITEMS[self.build_selection]
        cost = data["cost"]
        if self.resources < cost:
            self._flash("资源不足")
            return
        if self.build_selection == "wall":
            w, h = (data["h"], data["w"]) if self.wall_vertical else (data["w"], data["h"])
            rect = pygame.Rect(0, 0, w, h)
            rect.center = (int(pos.x), int(pos.y))
            if not self.field.contains(rect):
                self._flash("超出战场")
                return
            if rect.inflate(20, 20).collidepoint(*self.terminal.pos):
                self._flash("离终端太近")
                return
            if any(rect.colliderect(o) for o in self.obstacle_rects()):
                self._flash("位置被占用")
                return
            if any(circle_rect_collide(t.pos, t.radius, rect) for t in self.towers):
                self._flash("位置被占用")
                return
            if any(circle_rect_collide(m.pos, m.radius, rect) for m in self.mechs if m.alive):
                self._flash("机兵挡住了")
                return
            self.walls.append(Wall(rect, data["hp"]))
            self._rebuild_flow()
        else:  # tower
            if not self.field.collidepoint(pos.x, pos.y):
                return
            if self.terminal.pos.distance_to(pos) < self.terminal.radius + data["radius"] + 6:
                self._flash("离终端太近")
                return
            if any(circle_rect_collide(pos, data["radius"], o) for o in self.obstacle_rects()):
                self._flash("位置被占用")
                return
            if any(t.pos.distance_to(pos) < t.radius + data["radius"] for t in self.towers):
                self._flash("位置被占用")
                return
            self.towers.append(Tower(pos, data))
        self.resources -= cost
        audio.play("build")

    def _buy_upgrade(self, name):
        lv = getattr(self.terminal, name + "_lv")
        cost = C.BASE_UPGRADES[name]["base_cost"] + lv * 40
        if self.resources < cost:
            self._flash("资源不足")
            return
        self.resources -= cost
        audio.play("build")
        setattr(self.terminal, name + "_lv", lv + 1)
        if name == "shield":
            self.terminal.max_hp += 250
            self.terminal.hp += 250
        self._flash(f"{C.BASE_UPGRADES[name]['label'][:-4]} 升级至 Lv{lv + 1}")

    # ---------------- 更新 ----------------
    def update(self, dt):
        self.anim_time += dt
        audio.tick(dt)
        if self.message_timer > 0:
            self.message_timer -= dt
        # 打击感计时衰减（始终推进）
        self.shake = max(0.0, self.shake - 75 * dt)
        self.term_flash = max(0.0, self.term_flash - 2.6 * dt)
        # 光束 / 粒子始终更新
        self.beams = [b for b in self.beams if b.update(dt)]
        self.particles.update(dt)

        if self._flow_dirty:
            self._rebuild_flow()

        if self.state in ("WON", "LOST"):
            return

        # 命中顿帧：短暂冻结战斗与移动，但特效继续播
        if self.hitstop > 0:
            self.hitstop -= dt
            self._combat_fx(dt)
            return

        obstacles = self.obstacle_rects()
        moving = (self.state in ("BUILD", "WAVE")) and not self.paused
        if moving:
            for m in self.mechs:
                if m.alive:
                    before = Vector2(m.pos)
                    m.update_move(dt, obstacles)
                    if m.path and (m.pos - before).length_squared() > 0.5:
                        self.particles.thruster(m.pos, m.heading, (150, 190, 255))
        # 兜底：始终把机兵推出障碍，避免被压住卡死
        for m in self.mechs:
            if m.alive:
                m.pos = resolve_circle_rects(m.pos, m.radius, obstacles)

        if self.state == "WAVE" and not self.paused:
            self._update_wave(dt)
        self._combat_fx(dt)

    def _combat_fx(self, dt):
        """衰减受击白闪，把累积伤害转成飘字与火花，处理阵亡爆炸。"""
        p = self.particles
        for e in self.enemies:
            e.hit_flash = max(0.0, e.hit_flash - dt)
            if e._dmg_taken > 0:
                p.number(e.pos, e._dmg_taken, (255, 240, 180))
                p.spark(e.pos, lighten(e.color, 0.4), n=5)
                e._dmg_taken = 0.0
        for m in self.mechs:
            m.hit_flash = max(0.0, m.hit_flash - dt)
            if m.alive and m._dmg_taken > 0:
                p.number(m.pos, m._dmg_taken, (255, 140, 140))
                p.spark(m.pos, (255, 160, 90), n=5)
                m._dmg_taken = 0.0
            if not m.alive and not m._death_done:
                p.explosion(m.pos, m.color, n=30)
                p.rings.append(dict(pos=Vector2(m.pos), r=8, max_r=52,
                                    life=0.3, max=0.3, color=(255, 255, 255)))
                self.add_shake(10)
                self.hitstop = max(self.hitstop, 0.05)   # 顿帧
                audio.play("explosion", throttle=0.05)
                m._death_done = True
        for w in self.walls:
            w.hit_flash = max(0.0, w.hit_flash - dt)
            if w._dmg_taken > 0:
                p.number(w.pos, w._dmg_taken, (255, 150, 150))
                w._dmg_taken = 0.0
        t = self.terminal
        t.hit_flash = max(0.0, t.hit_flash - dt)
        if t._dmg_taken > 0:
            p.number(t.pos, t._dmg_taken, (255, 120, 120))
            p.spark(t.pos, (255, 120, 120), n=4)
            self.term_flash = min(1.0, self.term_flash + t._dmg_taken / 90.0)
            self.add_shake(min(13.0, t._dmg_taken * 0.5))
            audio.play("alarm", throttle=0.4)
            t._dmg_taken = 0.0

    def _update_wave(self, dt):
        beams0 = len(self.beams)
        # 出怪
        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                self._spawn_one()
                self.spawn_timer = C.WAVES[self.wave_index]["interval"]

        # 敌人
        for e in self.enemies:
            e.update(dt, self)
        # 机兵战斗
        for m in self.mechs:
            if m.alive:
                m.update_combat(dt, self)
        # 有新光束（开火）→ 节流播放激光音
        if len(self.beams) > beams0:
            audio.play("laser", vol=0.4, throttle=0.07)
        # 炮塔
        rb = self.terminal.tower_range_bonus
        for tw in self.towers:
            tw.update(dt, self.enemies, rb, self.beams)
        # 限时召唤物（哨戒炮/力场/无人机）
        self.deployables = [d for d in self.deployables if d.update(dt, self)]
        # 全局技能冷却
        for k in self.global_cd:
            if self.global_cd[k] > 0:
                self.global_cd[k] -= dt
        # 终端回复 + 维修基站
        self.terminal.regen(dt)
        if self.terminal.repair_lv > 0:
            for m in self.mechs:
                if m.alive and m.hp < m.max_hp and \
                   self.terminal.pos.distance_to(m.pos) <= self.terminal.repair_range:
                    m.hp = min(m.max_hp, m.hp + self.terminal.repair_rate * dt)

        # 清理死亡 & 结算奖励
        survivors = []
        for e in self.enemies:
            if e.alive:
                survivors.append(e)
            else:
                self.resources += e.reward
                self.particles.explosion(e.pos, e.color, n=20)
                audio.play("explosion", vol=0.7, throttle=0.05)
                # 大型单位死亡给点震屏
                if e.radius >= 18 or e.bomber:
                    self.add_shake(6)
        self.enemies = survivors
        before = len(self.walls)
        for w in self.walls:
            if not w.alive:
                self.particles.explosion(w.pos, (200, 180, 140), n=14)
        self.walls = [w for w in self.walls if w.alive]
        if len(self.walls) != before:
            self._flow_dirty = True
        for tw in self.towers:
            if not tw.alive:
                self.particles.explosion(tw.pos, C.C_TOWER, n=16)
        self.towers = [t for t in self.towers if t.alive]

        # 判负
        if not self.terminal.alive:
            self.state = "LOST"
            audio.play("lose")
            return
        # 判定波次结束
        if not self.spawn_queue and not self.enemies:
            self._wave_cleared()

    # ---------------- 绘制 ----------------
    def draw(self, surf):
        s = self.rs
        scene = self.scene
        scene.blit(self.bg, (0, 0))
        rb = self.terminal.tower_range_bonus
        # 地形
        for r in self.terrain:
            sprites.draw_obstacle(scene, r, s)
        # 墙
        for w in self.walls:
            sprites.draw_wall(scene, w, s)
        # 终端
        sprites.draw_terminal(scene, self.terminal, self.anim_time, s)
        # 炮塔
        for tw in self.towers:
            sprites.draw_tower(scene, tw, rb, self.anim_time, s)
        # 限时召唤物
        for d in self.deployables:
            sprites.draw_deployable(scene, d, self.anim_time, s)
        # 光束
        for b in self.beams:
            b.draw(scene, s)
        # 敌人
        for e in self.enemies:
            sprites.draw_enemy(scene, e, self.anim_time, s)
        # 机兵
        for m in self.mechs:
            if m.alive:
                sprites.draw_mech(scene, m, self.wfonts["tiny"], self.anim_time, m.selected, s)
        # 粒子（火花/爆炸/推进器，叠加发光）
        self.particles.draw(scene, s)
        # 正在绘制的路径
        if self.drawing_path and len(self.draw_points) >= 2:
            col = C.C_PATH_OK if self.path_valid else C.C_PATH_BAD
            pygame.draw.aalines(scene, col, False, [(p.x * s, p.y * s) for p in self.draw_points])
            render.aaring(scene, col, (self.draw_points[-1].x * s, self.draw_points[-1].y * s),
                          int(6 * s), max(1, int(2 * s)))
        # 建造预览
        if self.build_selection in ("wall", "tower"):
            self._draw_build_ghost(scene, s)
        # 技能瞄准预览
        if self.aiming is not None:
            self._draw_aim_ghost(scene, s)
        # 伤害飘字（最上层）
        self.particles.draw_text(scene, self.wfonts["small"], s)
        # 临时消息（战场内，超采样绘制）
        if self.message_timer > 0:
            img = self.wfonts["mid"].render(self.message, True, C.C_TEXT_WARN)
            r = img.get_rect(center=(C.SCREEN_W // 2 * s, (C.SCREEN_H - C.HUD_H - 24) * s))
            scene.blit(img, r)
        # 超采样画布 → 降采样到窗口战场区（带震屏偏移）
        pygame.transform.smoothscale(scene, (C.SCREEN_W, self.field.bottom), self._down)
        ox = oy = 0
        if self.shake > 0.5:
            ox = int(random.uniform(-self.shake, self.shake))
            oy = int(random.uniform(-self.shake, self.shake))
            surf.fill(C.C_BG, (0, 0, C.SCREEN_W, self.field.bottom))   # 盖住偏移留下的缝
        surf.blit(self._down, (ox, oy))
        # 终端受击红闪
        if self.term_flash > 0.01:
            ov = self._red_vig.copy()
            ov.fill((255, 255, 255, int(200 * min(1.0, self.term_flash))),
                    special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(ov, (0, 0))
        # 出怪方向预警（建造期）
        if self.state == "BUILD":
            self._draw_threat_edges(surf)
        # 框选矩形
        if self.box is not None:
            a, b = self.box
            r = pygame.Rect(int(min(a.x, b.x)), int(min(a.y, b.y)),
                            int(abs(a.x - b.x)), int(abs(a.y - b.y)))
            box_s = pygame.Surface((max(1, r.w), max(1, r.h)), pygame.SRCALPHA)
            box_s.fill((120, 220, 160, 40))
            surf.blit(box_s, r.topleft)
            pygame.draw.rect(surf, (140, 230, 170), r, 1)
        # HUD（窗口原生 1× 绘制）
        self.hud.draw(surf, self)

    def _draw_threat_edges(self, surf):
        """建造期在战场边缘按 threat_dirs 画脉冲红色箭头，预警出怪方向。"""
        pulse = 0.55 + 0.45 * math.sin(self.anim_time * 4.5)
        col = (255, int(70 + 60 * pulse), int(70 + 60 * pulse))
        fh = self.field.bottom
        for side, n in self.threat_dirs.items():
            if n <= 0:
                continue
            cnt = min(5, 1 + n // 3)        # 箭头数随数量增长
            for k in range(cnt):
                f = (k + 1) / (cnt + 1)
                d = int(14 + 10 * pulse)    # 箭头大小
                if side in ("top", "bottom"):
                    x = int(self.field.left + (self.field.right - self.field.left) * f)
                    y = 8 if side == "top" else fh - 8
                    dy = d if side == "top" else -d
                    pts = [(x - d, y), (x + d, y), (x, y + dy)]
                else:
                    y = int(self.field.top + (fh - self.field.top) * f)
                    x = 8 if side == "left" else C.SCREEN_W - 8
                    dx = d if side == "left" else -d
                    pts = [(x, y - d), (x, y + d), (x + dx, y)]
                pygame.draw.polygon(surf, col, pts)
            # 数量标注
            lbl = self.fonts["tiny"].render(f"×{n}", True, col)
            if side == "top":
                surf.blit(lbl, (C.SCREEN_W // 2 - 12, 30))
            elif side == "bottom":
                surf.blit(lbl, (C.SCREEN_W // 2 - 12, fh - 44))
            elif side == "left":
                surf.blit(lbl, (30, fh // 2))
            else:
                surf.blit(lbl, (C.SCREEN_W - 56, fh // 2))

    def _draw_aim_ghost(self, surf, s=1):
        mx, my = pygame.mouse.get_pos()
        if my >= C.SCREEN_H - C.HUD_H:
            return
        col = (130, 220, 255)
        rad = self.aiming.get("radius", 0)
        src = self.aiming.get("src")
        if rad > 0:
            render.aaring(surf, col, (mx * s, my * s), int(rad * s), max(1, int(2 * s)))
            render.glow(surf, (mx * s, my * s), rad * 0.5 * s, (30, 60, 80))
        if src is not None:
            pygame.draw.aaline(surf, (110, 170, 210), (src.x * s, src.y * s), (mx * s, my * s))
        render.aaring(surf, col, (mx * s, my * s), int(6 * s), max(1, int(2 * s)))

    def _draw_build_ghost(self, surf, s=1):
        mx, my = pygame.mouse.get_pos()
        if my >= C.SCREEN_H - C.HUD_H:
            return
        data = C.BUILD_ITEMS[self.build_selection]
        afford = self.resources >= data["cost"]
        col = (120, 220, 150) if afford else (220, 100, 100)
        if self.build_selection == "wall":
            w, h = (data["h"], data["w"]) if self.wall_vertical else (data["w"], data["h"])
            rect = pygame.Rect(0, 0, int(w * s), int(h * s))
            rect.center = (mx * s, my * s)
            pygame.draw.rect(surf, col, rect, max(1, int(2 * s)), border_radius=int(3 * s))
            hint = self.wfonts["tiny"].render("滚轮/Tab 旋转", True, (180, 200, 220))
            surf.blit(hint, (int((mx + 12) * s), int((my + 12) * s)))
        else:
            pygame.draw.circle(surf, col, (int(mx * s), int(my * s)), int(data["radius"] * s), max(1, int(2 * s)))
            pygame.draw.circle(surf, C.C_RANGE_RING, (int(mx * s), int(my * s)),
                               int((data["range"] + self.terminal.tower_range_bonus) * s), max(1, int(s)))
