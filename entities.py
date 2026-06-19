"""游戏实体：终端、机兵、敌人、炮塔、墙、光束特效。"""
import pygame
from pygame.math import Vector2

import config as C
from geometry import (circle_rect_collide, resolve_circle_rects, steer_around)
import render


class Beam:
    """一次攻击/治疗的瞬时连线特效。"""
    def __init__(self, a, b, color, ttl=0.12, width=2):
        self.a = Vector2(a)
        self.b = Vector2(b)
        self.color = color
        self.ttl = ttl
        self.max_ttl = ttl
        self.width = width

    def update(self, dt):
        self.ttl -= dt
        return self.ttl > 0

    def draw(self, surf, s=1):
        f = max(0.0, self.ttl / self.max_ttl)
        col = tuple(int(c * (0.4 + 0.6 * f)) for c in self.color)
        render.beam(surf, (self.a.x * s, self.a.y * s), (self.b.x * s, self.b.y * s),
                    col, width=max(1, int(self.width * (0.4 + f) * s)))


class Terminal:
    """中央终端，要守护的核心，可被升级附加设施。"""
    def __init__(self, pos):
        self.pos = Vector2(pos)
        self.radius = C.TERMINAL_RADIUS
        self.max_hp = C.TERMINAL_HP
        self.hp = self.max_hp
        # 升级等级
        self.repair_lv = 0
        self.shield_lv = 0
        self.radar_lv = 0
        self.hit_flash = 0.0
        self._dmg_taken = 0.0

    @property
    def alive(self):
        return self.hp > 0

    @property
    def repair_range(self):
        return 150 + 60 * self.repair_lv

    @property
    def repair_rate(self):
        return 14 * self.repair_lv          # 每秒治疗

    @property
    def tower_range_bonus(self):
        return 40 * self.radar_lv

    def regen(self, dt):
        if self.shield_lv > 0 and self.hp > 0:
            self.hp = min(self.max_hp, self.hp + self.shield_lv * 12 * dt)

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self._dmg_taken += dmg
        self.hit_flash = 0.12


class Wall:
    """阻挡墙：障碍物 + 可被攻击。"""
    def __init__(self, rect, hp):
        self.rect = pygame.Rect(rect)
        self.max_hp = hp
        self.hp = hp
        self.hit_flash = 0.0
        self._dmg_taken = 0.0

    @property
    def alive(self):
        return self.hp > 0

    @property
    def pos(self):
        return Vector2(self.rect.center)

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self._dmg_taken += dmg
        self.hit_flash = 0.12


class Tower:
    """自动炮塔：射程内自动攻击最近敌人。"""
    def __init__(self, pos, data):
        self.pos = Vector2(pos)
        self.radius = data["radius"]
        self.base_range = data["range"]
        self.damage = data["damage"]
        self.attack_cd = data["attack_cd"]
        self.max_hp = data["hp"]
        self.hp = data["hp"]
        self.timer = 0.0
        self.hit_flash = 0.0
        self._dmg_taken = 0.0

    @property
    def alive(self):
        return self.hp > 0

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self._dmg_taken += dmg
        self.hit_flash = 0.12

    def update(self, dt, enemies, range_bonus, beams):
        self.timer -= dt
        if self.timer > 0:
            return
        rng = self.base_range + range_bonus
        target = None
        best = rng * rng
        for e in enemies:
            d = self.pos.distance_squared_to(e.pos)
            if d <= best:
                best = d
                target = e
        if target:
            target.take_damage(self.damage)
            beams.append(Beam(self.pos, target.pos, C.C_BEAM_ALLY, width=2))
            self.timer = self.attack_cd


class Mech:
    """玩家机兵：沿路径移动、自动攻击、可释放技能。"""
    def __init__(self, type_name, pos):
        d = C.MECH_TYPES[type_name]
        self.type = type_name
        self.role = d["role"]
        self.color = d["color"]
        self.radius = d["radius"]
        self.max_hp = d["hp"]
        self.hp = d["hp"]
        self.speed = d["speed"]
        self.range = d["range"]
        self.damage = d["damage"]
        self.attack_cd = d["attack_cd"]
        self.can_hit_flying = d["can_hit_flying"]
        self.splash = d.get("splash", 0)
        self.heal = d.get("heal", 0)
        # 技能（数据驱动）+ 能量
        self.abilities = [dict(a) for a in d.get("abilities", [])]
        self.max_energy = d.get("energy", 100)
        self.energy = self.max_energy
        self.energy_regen = d.get("energy_regen", 12)
        self.ability_timers = [0.0 for _ in self.abilities]   # 每个技能独立冷却

        self.pos = Vector2(pos)
        self.heading = Vector2(1, 0)
        self.path = []              # 待走的路径点
        self.attack_timer = 0.0
        self.forced_target = None   # 玩家右键指定的目标
        self.selected = False
        self.hit_flash = 0.0
        self._dmg_taken = 0.0
        self._death_done = False
        # 状态效果（增益/护盾/生根）：值 + 剩余时间
        self.shield = 0.0
        self.shield_timer = 0.0
        self.dmg_mult = 1.0
        self.range_mult = 1.0
        self.atkspd_mult = 1.0
        self.move_mult = 1.0
        self.buff_timer = 0.0       # 统管 dmg/range/atkspd/move 增益
        self.buff_kind = None       # "calibrate" / "overdrive"，用于显示与生根判断
        self.root_timer = 0.0       # >0 不能移动（校准模式）

    @property
    def alive(self):
        return self.hp > 0

    @property
    def eff_speed(self):
        return self.speed * self.move_mult

    @property
    def eff_range(self):
        return self.range * self.range_mult

    def take_damage(self, dmg):
        if self.shield > 0:                 # 护盾优先吸收
            absorbed = min(self.shield, dmg)
            self.shield -= absorbed
            dmg -= absorbed
        if dmg <= 0:
            return
        self.hp = max(0, self.hp - dmg)
        self._dmg_taken += dmg
        self.hit_flash = 0.12

    def gain_energy(self, amount):
        self.energy = min(self.max_energy, self.energy + amount)

    def _tick_status(self, dt):
        """每帧（仅战斗、未暂停）推进能量与状态计时。"""
        self.energy = min(self.max_energy, self.energy + self.energy_regen * dt)
        if self.shield_timer > 0:
            self.shield_timer -= dt
            if self.shield_timer <= 0:
                self.shield = 0.0
        if self.root_timer > 0:
            self.root_timer -= dt
        if self.buff_timer > 0:
            self.buff_timer -= dt
            if self.buff_timer <= 0:        # 增益到期，复位
                self.dmg_mult = self.range_mult = self.atkspd_mult = self.move_mult = 1.0
                self.buff_kind = None
        for i in range(len(self.ability_timers)):
            if self.ability_timers[i] > 0:
                self.ability_timers[i] -= dt

    def set_path(self, points):
        self.path = [Vector2(p) for p in points]

    def stop(self):
        self.path = []
        self.forced_target = None

    # ---- 移动（建造期与战斗期都会跑）----
    def update_move(self, dt, obstacles):
        if self.root_timer > 0:     # 校准模式：生根，无法移动
            return
        if not self.path:
            return
        old = Vector2(self.pos)
        target = self.path[0]
        to = target - self.pos
        dist = to.length()
        step = self.eff_speed * dt
        if dist <= step or dist == 0:
            self.pos = Vector2(target)
            self.path.pop(0)
        else:
            move = steer_around(self.pos, to, self.radius, obstacles, step)
            if move.length_squared() == 0:
                # 被新出现的障碍堵死，直接朝目标小步推进 + 解碰撞
                self.pos += to.normalize() * step
            else:
                self.pos += move
        self.pos = resolve_circle_rects(self.pos, self.radius, obstacles)
        delta = self.pos - old
        if delta.length_squared() > 1e-4:
            self.heading = delta.normalize()

    # ---- 战斗（仅战斗期）----
    def update_combat(self, dt, game):
        self._tick_status(dt)
        self.attack_timer -= dt

        if self.role == "support":
            self._do_support(game)
            return

        target = self._pick_target(game)
        if target and self.attack_timer <= 0:
            self._attack(target, game)
            self.attack_timer = self.attack_cd / self.atkspd_mult
            self.gain_energy(5)

    def _pick_target(self, game):
        # 玩家指定目标优先（在射程内）
        rng = self.eff_range
        if self.forced_target is not None:
            if getattr(self.forced_target, "alive", False) and \
               self.pos.distance_to(self.forced_target.pos) <= rng + self.forced_target.radius:
                return self.forced_target
            if not getattr(self.forced_target, "alive", False):
                self.forced_target = None
        # 自动索敌：射程内最近的合法敌人
        best = None
        bestd = rng ** 2
        for e in game.enemies:
            if e.flying and not self.can_hit_flying:
                continue
            d = self.pos.distance_squared_to(e.pos)
            if d <= bestd:
                bestd = d
                best = e
        return best

    def _attack(self, target, game):
        dmg = self.damage * self.dmg_mult
        target.take_damage(dmg)
        game.beams.append(Beam(self.pos, target.pos, C.C_BEAM_ALLY, width=2))
        if self.splash > 0:
            for e in game.enemies:
                if e is target:
                    continue
                if e.flying and not self.can_hit_flying:
                    continue
                if target.pos.distance_to(e.pos) <= self.splash:
                    e.take_damage(dmg * 0.5)

    def _do_support(self, game):
        if self.attack_timer > 0:
            return
        # 治疗射程内血量最低的友方机兵
        target = None
        worst = 1.0
        for m in game.mechs:
            if m is self or not m.alive:
                continue
            if self.pos.distance_to(m.pos) > self.range:
                continue
            frac = m.hp / m.max_hp
            if frac < 1.0 and frac < worst:
                worst = frac
                target = m
        if target:
            target.hp = min(target.max_hp, target.hp + self.heal)
            game.beams.append(Beam(self.pos, target.pos, C.C_BEAM_HEAL, width=3))
            self.attack_timer = self.attack_cd

    # ---- 技能 ----
    def ability(self, slot):
        return self.abilities[slot] if 0 <= slot < len(self.abilities) else None

    def can_use(self, slot):
        """返回 (是否可用, 不可用原因)。"""
        spec = self.ability(slot)
        if spec is None or not self.alive:
            return False, ""
        if self.ability_timers[slot] > 0:
            return False, "技能冷却中"
        if self.energy < spec["cost"]:
            return False, "能量不足"
        return True, ""

    def use_ability(self, game, slot, target=None):
        ok, _ = self.can_use(slot)
        if not ok:
            return False
        spec = self.abilities[slot]
        fx = _ABILITY_FX.get(spec["effect"])
        if fx is None:
            return False
        fx(self, game, spec, target)
        self.energy -= spec["cost"]
        self.ability_timers[slot] = spec["cd"]
        return True


# ---------------- 技能效果（数据驱动分派）----------------
def _fx_shock(m, game, spec, target):
    """震荡冲击：自身周围范围伤害 + 短暂眩晕 + 轻击退。"""
    r = spec["radius"]
    game.particles.rings.append(dict(pos=Vector2(m.pos), r=10, max_r=r,
                                     life=0.4, max=0.4, color=(255, 200, 120)))
    for e in list(game.enemies):
        d = m.pos.distance_to(e.pos)
        if d <= r:
            e.take_damage(spec["value"])
            e.apply_stun(spec["duration"])
            if d > 1:
                e.pos += (e.pos - m.pos).normalize() * 26
            game.beams.append(Beam(m.pos, e.pos, C.C_BEAM_ALLY, width=3))


def _fx_dash(m, game, spec, target):
    """战术突进：瞬移到点位，落点范围伤害。"""
    if target is None:
        return
    dest = Vector2(target)
    m.pos = resolve_circle_rects(dest, m.radius, game.obstacle_rects())
    m.path = []
    m.heading = (dest - m.pos)
    if m.heading.length_squared() < 1:
        m.heading = Vector2(1, 0)
    else:
        m.heading = m.heading.normalize()
    game.particles.explosion(m.pos, (255, 180, 120), n=18)
    for e in list(game.enemies):
        if m.pos.distance_to(e.pos) <= spec["radius"]:
            e.take_damage(spec["value"])
            game.beams.append(Beam(m.pos, e.pos, C.C_BEAM_ALLY, width=2))


def _fx_barrage(m, game, spec, target):
    """饱和轰炸：指定点位大范围 AoE。"""
    if target is None:
        return
    c = Vector2(target)
    r = spec["radius"]
    game.particles.rings.append(dict(pos=Vector2(c), r=12, max_r=r,
                                     life=0.5, max=0.5, color=(255, 150, 110)))
    for e in list(game.enemies):
        if c.distance_to(e.pos) <= r:
            e.take_damage(spec["value"])
            game.beams.append(Beam(c, e.pos, C.C_BEAM_ENEMY, ttl=0.25, width=2))
            game.particles.spark(e.pos, (255, 180, 120), n=6)


def _fx_calibrate(m, game, spec, target):
    """校准模式：限时大幅增伤 + 增程，但生根不可移动。"""
    m.dmg_mult = spec["value"]
    m.range_mult = 1.4
    m.atkspd_mult = 1.0
    m.move_mult = 1.0
    m.buff_timer = spec["duration"]
    m.buff_kind = "calibrate"
    m.root_timer = spec["duration"]
    m.path = []


def _fx_strafe(m, game, spec, target):
    """弹幕扫射：射程内全体多段伤害。"""
    for e in list(game.enemies):
        if e.flying and not m.can_hit_flying:
            continue
        if m.pos.distance_to(e.pos) <= m.eff_range:
            e.take_damage(spec["value"])
            game.beams.append(Beam(m.pos, e.pos, C.C_BEAM_ALLY, width=1))


def _fx_overdrive(m, game, spec, target):
    """过载冲锋：限时攻速 + 移速大增。"""
    m.atkspd_mult = spec["value"]
    m.move_mult = 1.5
    m.dmg_mult = 1.0
    m.range_mult = 1.0
    m.buff_timer = spec["duration"]
    m.buff_kind = "overdrive"


def _fx_heal_all(m, game, spec, target):
    """过载治疗：全体友军回血。"""
    for ally in game.mechs:
        if ally.alive:
            ally.hp = min(ally.max_hp, ally.hp + spec["value"])
            game.beams.append(Beam(m.pos, ally.pos, C.C_BEAM_HEAL, ttl=0.25, width=2))


def _fx_barrier(m, game, spec, target):
    """力场护盾：给点位范围内友军附加限时护盾。"""
    c = Vector2(target) if target is not None else Vector2(m.pos)
    r = spec["radius"]
    game.particles.rings.append(dict(pos=Vector2(c), r=10, max_r=r,
                                     life=0.5, max=0.5, color=(130, 220, 255)))
    for ally in game.mechs:
        if ally.alive and c.distance_to(ally.pos) <= r:
            ally.shield = max(ally.shield, spec["value"])
            ally.shield_timer = spec["duration"]
            game.beams.append(Beam(m.pos, ally.pos, C.C_BEAM_HEAL, ttl=0.25, width=2))


def _fx_emp_pulse(m, game, spec, target):
    """静电脉冲：自身范围眩晕 + 小伤害。"""
    r = spec["radius"]
    game.particles.rings.append(dict(pos=Vector2(m.pos), r=10, max_r=r,
                                     life=0.45, max=0.45, color=(190, 150, 255)))
    for e in list(game.enemies):
        if m.pos.distance_to(e.pos) <= r:
            e.take_damage(spec["value"])
            e.apply_stun(spec["duration"])
            game.beams.append(Beam(m.pos, e.pos, (190, 150, 255), ttl=0.2, width=2))


def _fx_slow_field(m, game, spec, target):
    """磁轨钉：在点位部署持续减速 + 灼烧的力场。"""
    if target is None:
        return
    game.deployables.append(SlowField(target, spec["radius"], spec["duration"],
                                      spec["slow"], spec["value"]))


def _fx_deploy_turret(m, game, spec, target):
    """部署哨戒炮：点位召唤一座限时自动炮台。"""
    if target is None:
        return
    game.deployables.append(SentryTurret(target, spec["value"]))


def _fx_heal_drone(m, game, spec, target):
    """维修无人机：点位召唤限时治疗无人机。"""
    pos = target if target is not None else m.pos
    game.deployables.append(HealDrone(pos, spec["value"]))


_ABILITY_FX = {
    "shock": _fx_shock,
    "dash": _fx_dash,
    "barrage": _fx_barrage,
    "calibrate": _fx_calibrate,
    "strafe": _fx_strafe,
    "overdrive": _fx_overdrive,
    "heal_all": _fx_heal_all,
    "barrier": _fx_barrier,
    "emp_pulse": _fx_emp_pulse,
    "slow_field": _fx_slow_field,
    "deploy_turret": _fx_deploy_turret,
    "heal_drone": _fx_heal_drone,
}


# ---------------- 可部署物（限时召唤）----------------
class SentryTurret:
    """限时自动炮台：周期攻击射程内最近敌人。"""
    def __init__(self, pos, lifetime):
        d = C.SENTRY
        self.pos = Vector2(pos)
        self.life = lifetime
        self.max_life = lifetime
        self.range = d["range"]
        self.damage = d["damage"]
        self.attack_cd = d["attack_cd"]
        self.radius = d["radius"]
        self.color = d["color"]
        self.timer = 0.0
        self.anim = 0.0

    def update(self, dt, game):
        self.life -= dt
        self.anim += dt
        self.timer -= dt
        if self.timer <= 0:
            best, bd = None, self.range ** 2
            for e in game.enemies:
                dd = self.pos.distance_squared_to(e.pos)
                if dd <= bd:
                    bd, best = dd, e
            if best is not None:
                best.take_damage(self.damage)
                game.beams.append(Beam(self.pos, best.pos, self.color, width=2))
                self.timer = self.attack_cd
        return self.life > 0


class SlowField:
    """限时减速力场：范围内敌人持续减速 + 灼烧。"""
    def __init__(self, pos, radius, lifetime, slow, dps):
        self.pos = Vector2(pos)
        self.radius = radius
        self.life = lifetime
        self.max_life = lifetime
        self.slow = slow
        self.dps = dps
        self.color = C.SLOW_FIELD["color"]
        self.anim = 0.0

    def update(self, dt, game):
        self.life -= dt
        self.anim += dt
        for e in game.enemies:
            if self.pos.distance_to(e.pos) <= self.radius:
                e.apply_slow(self.slow, 0.3)
                e.take_damage(self.dps * dt)
        return self.life > 0


class HealDrone:
    """限时治疗无人机：在部署点附近悬停，周期治疗最近的受伤友军。"""
    def __init__(self, pos, lifetime):
        d = C.HEAL_DRONE
        self.home = Vector2(pos)
        self.pos = Vector2(pos)
        self.life = lifetime
        self.max_life = lifetime
        self.range = d["range"]
        self.heal = d["heal"]
        self.cd = d["cd"]
        self.radius = d["radius"]
        self.color = d["color"]
        self.timer = 0.0
        self.anim = 0.0
        self.target = None

    def update(self, dt, game):
        self.life -= dt
        self.anim += dt
        self.timer -= dt
        # 找射程内血量最低的受伤友军
        tgt, worst = None, 1.0
        for ally in game.mechs:
            if not ally.alive or ally.hp >= ally.max_hp:
                continue
            if self.home.distance_to(ally.pos) <= self.range:
                frac = ally.hp / ally.max_hp
                if frac < worst:
                    worst, tgt = frac, ally
        self.target = tgt
        # 悬停：朝目标缓慢漂移，否则回到部署点
        anchor = tgt.pos if tgt is not None else self.home
        self.pos += (anchor - self.pos) * min(1.0, 3.0 * dt)
        if tgt is not None and self.timer <= 0:
            tgt.hp = min(tgt.max_hp, tgt.hp + self.heal)
            game.beams.append(Beam(self.pos, tgt.pos, C.C_BEAM_HEAL, ttl=0.25, width=2))
            self.timer = self.cd
        return self.life > 0


class Enemy:
    """来袭机械兽：朝终端推进，沿途攻击墙/机兵，到达后攻击终端。"""
    def __init__(self, type_name, pos):
        d = C.ENEMY_TYPES[type_name]
        self.type = type_name
        self.color = d["color"]
        self.radius = d["radius"]
        self.max_hp = d["hp"]
        self.hp = d["hp"]
        self.speed = d["speed"]
        self.damage = d["damage"]
        self.attack_cd = d["attack_cd"]
        self.flying = d["flying"]
        self.reward = d["reward"]
        self.bomber = d.get("bomber", False)
        # 多样化行为
        self.attack_range = d.get("attack_range", 0)   # >0 为远程攻击距离
        self.shield = d.get("shield", 0)               # 自带护盾（先于血量吸收）
        self.shield_aura = d.get("shield_aura")        # (护盾量, 半径) 给周围敌人加盾
        self.heal_aura = d.get("heal_aura")            # (每跳治疗, 半径)
        self.split = d.get("split")                    # (子类型, 数量) 死亡分裂
        self.boss = d.get("boss", False)
        self.aura_timer = 0.0
        self.pos = Vector2(pos)
        self.heading = Vector2(0, 1)
        self.timer = 0.0
        self.hit_flash = 0.0
        self._dmg_taken = 0.0
        self.slow_factor = 1.0      # <1 表示被减速
        self.slow_timer = 0.0
        self.stun_timer = 0.0       # >0 表示被眩晕/冻结

    @property
    def alive(self):
        return self.hp > 0

    def take_damage(self, dmg):
        self.hit_flash = 0.12
        if self.shield > 0:                 # 护盾优先吸收
            absorbed = min(self.shield, dmg)
            self.shield -= absorbed
            dmg -= absorbed
        if dmg <= 0:
            return
        self.hp = max(0, self.hp - dmg)
        self._dmg_taken += dmg

    def _do_auras(self, dt, game):
        """治疗 / 护盾光环：周期性增益周围敌人。"""
        if not (self.heal_aura or self.shield_aura):
            return
        self.aura_timer -= dt
        if self.aura_timer > 0:
            return
        self.aura_timer = 0.6
        if self.heal_aura:
            amt, rng = self.heal_aura
            for e in game.enemies:
                if e is not self and 0 < e.hp < e.max_hp and self.pos.distance_to(e.pos) <= rng:
                    e.hp = min(e.max_hp, e.hp + amt)
                    game.beams.append(Beam(self.pos, e.pos, C.C_BEAM_HEAL, ttl=0.2, width=2))
        if self.shield_aura:
            amt, rng = self.shield_aura
            for e in game.enemies:
                if e is not self and e.shield < amt and self.pos.distance_to(e.pos) <= rng:
                    e.shield = amt

    def apply_slow(self, factor, dur):
        self.slow_factor = min(self.slow_factor, factor)
        self.slow_timer = max(self.slow_timer, dur)

    def apply_stun(self, dur):
        self.stun_timer = max(self.stun_timer, dur)

    def update(self, dt, game):
        self.timer -= dt
        # 状态计时
        if self.stun_timer > 0:
            self.stun_timer -= dt
            if self.slow_timer > 0:
                self.slow_timer -= dt
            return                  # 眩晕：本帧不移动、不攻击
        if self.slow_timer > 0:
            self.slow_timer -= dt
            if self.slow_timer <= 0:
                self.slow_factor = 1.0
        self._do_auras(dt, game)
        terminal = game.terminal
        to_term = terminal.pos - self.pos
        dist_term = to_term.length()
        atk_range = self.attack_range if self.attack_range else (self.radius + 12)

        # 抵达（远程兵从射程外即可攻击终端）
        if dist_term <= terminal.radius + atk_range:
            if self.bomber:
                terminal.take_damage(self.damage * 4)
                game.beams.append(Beam(self.pos, terminal.pos, C.C_BEAM_ENEMY, ttl=0.25, width=4))
                self.hp = 0
                return
            self._face(to_term)
            if self.timer <= 0:
                terminal.take_damage(self.damage)
                game.beams.append(Beam(self.pos, terminal.pos, C.C_BEAM_ENEMY, width=2))
                self.timer = self.attack_cd
            return

        # 攻击贴近的机兵
        mech = self._nearest_mech(game, atk_range)
        if mech is not None:
            self._face(mech.pos - self.pos)
            if self.timer <= 0:
                mech.take_damage(self.damage)
                game.beams.append(Beam(self.pos, mech.pos, C.C_BEAM_ENEMY, width=2))
                self.timer = self.attack_cd
            return

        # 决定前进方向：流场寻路（绕开障碍）
        reachable = self.flying or game.flow.reachable_at(self.pos)
        if self.flying:
            d = to_term.normalize() if dist_term else Vector2(0, 0)
        elif reachable:
            d = game.flow.direction_at(self.pos)
            if d.length_squared() == 0:
                d = to_term.normalize() if dist_term else Vector2(0, 0)
            else:
                d = (d * 0.85 + (to_term.normalize() if dist_term else d) * 0.15)
                if d.length_squared():
                    d = d.normalize()
        else:
            # 被墙完全围死：攻击挡路的墙，破墙而入
            wall = self._nearest_wall(game, atk_range)
            if wall is not None:
                self._face(wall.pos - self.pos)
                if self.timer <= 0:
                    wall.take_damage(self.damage)
                    game.beams.append(Beam(self.pos, wall.pos, C.C_BEAM_ENEMY, width=2))
                    self.timer = self.attack_cd
                return
            d = to_term.normalize() if dist_term else Vector2(0, 0)

        step = self.speed * self.slow_factor * dt
        newpos = self.pos + d * step
        if not self.flying:
            newpos = resolve_circle_rects(newpos, self.radius, game.obstacle_rects())
        self.pos = newpos
        if d.length_squared() > 1e-4:
            self.heading = d

    def _face(self, vec):
        if vec.length_squared() > 1e-4:
            self.heading = vec.normalize()

    def _nearest_mech(self, game, atk_range):
        best, bestd = None, 1e18
        for m in game.mechs:
            if not m.alive:
                continue
            d = self.pos.distance_to(m.pos) - m.radius
            if d <= atk_range and d < bestd:
                bestd, best = d, m
        return best

    def _nearest_wall(self, game, atk_range):
        best, bestd = None, 1e18
        for w in game.walls:
            cx = max(w.rect.left, min(self.pos.x, w.rect.right))
            cy = max(w.rect.top, min(self.pos.y, w.rect.bottom))
            d = self.pos.distance_to(Vector2(cx, cy))
            if d <= atk_range and d < bestd:
                bestd, best = d, w
        return best
