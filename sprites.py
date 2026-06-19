"""矢量精灵：霓虹科幻风的机兵、敌人、终端、炮塔、墙、障碍。

统一以「单位坐标 + 渲染缩放 s」绘制：每个 draw 把实体的 pos/radius 乘以 s 转到
物理像素，形状点用半径的比例表达，因此整套画面可在 2× 超采样画布上无失真放大。
多层明暗 + 金属高光 + 面板线 + 轮廓光，让单位脱离「平涂几何体」的廉价感。
障碍/墙纹理按尺寸缓存，避免每帧重绘渐变。
"""
import math
import pygame
from pygame.math import Vector2

import config as C
import render
from ui import draw_hp_bar

_tile_cache = {}


def shade(col, f):
    return (max(0, min(255, int(col[0] * f))),
            max(0, min(255, int(col[1] * f))),
            max(0, min(255, int(col[2] * f))))


def lighten(col, f):
    return (min(255, int(col[0] + (255 - col[0]) * f)),
            min(255, int(col[1] + (255 - col[1]) * f)),
            min(255, int(col[2] + (255 - col[2]) * f)))


def _flash(col, hit):
    if hit <= 0:
        return col
    return lighten(col, 0.85 * min(1.0, hit / 0.12))


def _deg(h):
    return math.degrees(math.atan2(h.y, h.x))


def _poly(cx, cy, pts, deg, scale=1.0):
    out = []
    for x, y in pts:
        v = Vector2(x * scale, y * scale).rotate(deg)
        out.append((cx + v.x, cy + v.y))
    return out


def _line(surf, a, b, col, w):
    w = max(1, int(round(w)))
    if w <= 1:
        pygame.draw.aaline(surf, col, a, b)
    else:
        pygame.draw.line(surf, col, a, b, w)


# ---------------- 血条（仅受伤显示）----------------
def _hp(surf, x, y, w, frac, s, always=False):
    if frac < 0.999 or always:
        draw_hp_bar(surf, x, y, w, max(3, int(4 * s)), frac)


# ---------------- 障碍 / 墙 纹理 ----------------
def _vgrad_tile(w, h, top, bottom, border, radius, s):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        f = y / max(1, h - 1)
        col = (int(top[0] + (bottom[0] - top[0]) * f),
               int(top[1] + (bottom[1] - top[1]) * f),
               int(top[2] + (bottom[2] - top[2]) * f))
        pygame.draw.line(surf, col, (0, y), (w, y))
    # 圆角遮罩
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=int(radius * s))
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # 顶部高光 + 边框
    pygame.draw.line(surf, lighten(top, 0.35), (int(radius * s), int(s)),
                     (w - int(radius * s), int(s)), max(1, int(s)))
    pygame.draw.rect(surf, border, (0, 0, w, h), max(1, int(2 * s)), border_radius=int(radius * s))
    return surf


def _obstacle_tile(w, h, s):
    key = ("obs", w, h)
    t = _tile_cache.get(key)
    if t is None:
        t = _vgrad_tile(w, h, (78, 86, 108), (36, 42, 58), (104, 116, 144), 5, s)
        # 内嵌面板分割线
        pygame.draw.line(t, (96, 106, 132, 110), (int(8 * s), h // 2), (w - int(8 * s), h // 2), max(1, int(s)))
        # 角落铆钉（带高光的立体钉）
        rv = max(2, int(2.6 * s))
        for cx, cy in ((10 * s, 10 * s), (w - 10 * s, 10 * s), (10 * s, h - 10 * s), (w - 10 * s, h - 10 * s)):
            pygame.draw.circle(t, (28, 32, 44), (int(cx), int(cy)), rv)
            pygame.draw.circle(t, (138, 150, 178), (int(cx), int(cy)), rv, max(1, int(s)))
            pygame.draw.circle(t, (180, 192, 215), (int(cx - rv * 0.3), int(cy - rv * 0.3)), max(1, int(rv * 0.4)))
        _tile_cache[key] = t
    return t


def _wall_tile(w, h, s):
    key = ("wall", w, h)
    t = _tile_cache.get(key)
    if t is None:
        t = _vgrad_tile(w, h, (190, 176, 128), (116, 104, 70), (222, 208, 156), 3, s)
        # 斜向危险条纹
        stripe = pygame.Surface((w, h), pygame.SRCALPHA)
        step = int(16 * s)
        for x in range(-h, w, step):
            pygame.draw.line(stripe, (38, 34, 22, 75), (x, h), (x + h, 0), max(2, int(5 * s)))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=int(3 * s))
        stripe.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        t.blit(stripe, (0, 0))
        _tile_cache[key] = t
    return t


def draw_obstacle(surf, rect, s=1):
    w, h = int(rect.width * s), int(rect.height * s)
    x, y = int(rect.left * s), int(rect.top * s)
    # 投影：贴着底部、向右下轻微偏移的低透明圆角暗块（只露出底/右一道细边）
    off = max(2, int(5 * s))
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 80), (0, 0, w, h), border_radius=int(6 * s))
    surf.blit(sh, (x + off, y + off))
    surf.blit(_obstacle_tile(w, h, s), (x, y))


def draw_wall(surf, wl, s=1):
    w, h = int(wl.rect.width * s), int(wl.rect.height * s)
    x, y = int(wl.rect.left * s), int(wl.rect.top * s)
    surf.blit(_wall_tile(w, h, s), (x, y))
    if wl.hit_flash > 0:
        fl = pygame.Surface((w, h), pygame.SRCALPHA)
        fl.fill((255, 255, 255, int(150 * min(1, wl.hit_flash / 0.12))))
        surf.blit(fl, (x, y))
    _hp(surf, x, y - int(7 * s), w, wl.hp / wl.max_hp, s)


# ---------------- 终端 ----------------
def draw_terminal(surf, term, t, s=1):
    pos = (term.pos.x * s, term.pos.y * s)
    r = term.radius * s
    if term.repair_lv > 0:
        render.aaring(surf, (40, 80, 60), pos, int(term.repair_range * s), max(1, int(s)))
    # 外辉光
    flash = term.hit_flash
    gcol = (90, 170, 255) if flash <= 0 else (255, 180, 180)
    render.glow(surf, pos, r * 3.0, (gcol[0] // 4, gcol[1] // 4, gcol[2] // 4))
    # 旋转弧（双层）
    for k in range(4):
        ang = t * (40 + k * 20) + k * 60
        rr = r + (8 + k * 7) * s
        pygame.draw.arc(surf, shade(C.C_TERMINAL, 0.8 - k * 0.12),
                        (pos[0] - rr, pos[1] - rr, rr * 2, rr * 2),
                        math.radians(ang), math.radians(ang + 1.2), max(1, int(2 * s)))
    # 基座盘（分层金属）
    render.aacircle(surf, shade(C.C_TERMINAL, 0.32), pos, int(r * 1.02))
    render.aacircle(surf, _flash(shade(C.C_TERMINAL, 0.5), flash), pos, int(r * 0.92))
    # 面板分割（六向）
    for i in range(6):
        a = i * 60 + t * 12
        p = _poly(pos[0], pos[1], [(0.35, 0), (0.9, 0)], a, r)
        _line(surf, p[0], p[1], shade(C.C_TERMINAL, 0.7), 1.4 * s)
    render.aacircle(surf, _flash(C.C_TERMINAL, flash), pos, int(r * 0.62))
    render.aaring(surf, C.C_TERMINAL_HI, pos, int(r * 0.92), max(1, int(2 * s)))
    # 脉动发光核心
    pulse = 0.5 + 0.5 * math.sin(t * 4)
    cr = int(r * (0.26 + 0.12 * pulse))
    render.glow(surf, pos, r * (1.5 + 0.4 * pulse), (60, 130, 200))
    render.aacircle(surf, lighten(C.C_TERMINAL, 0.55), pos, int(cr * 1.5))
    render.aacircle(surf, (240, 252, 255), pos, cr)
    if term.shield_lv > 0:
        render.aaring(surf, (120, 200, 255), pos, int(r + (6 + term.shield_lv) * s), max(1, int(2 * s)))
    _hp(surf, pos[0] - 40 * s, pos[1] - r - 16 * s, 80 * s, term.hp / term.max_hp, s, always=True)


# ---------------- 炮塔 ----------------
def draw_tower(surf, tw, range_bonus, t, s=1):
    pos = (tw.pos.x * s, tw.pos.y * s)
    R = tw.radius * s
    rng = (tw.base_range + range_bonus) * s
    render.aaring(surf, C.C_RANGE_RING, pos, int(rng), max(1, int(s)))
    render.soft_shadow(surf, Vector2(*pos), R + 2 * s, R)
    base = _flash(C.C_TOWER, tw.hit_flash)
    render.glow(surf, pos, R * 2.4, (60, 40, 80))
    # 六边形底座：外暗环 + 分面高光
    hexpts = [(math.cos(a), math.sin(a)) for a in [i * math.pi / 3 for i in range(6)]]
    render.aapolygon(surf, shade(base, 0.45), _poly(pos[0], pos[1], hexpts, 8, R * 1.06))
    render.aapolygon(surf, shade(base, 0.72), _poly(pos[0], pos[1], hexpts, 0, R))
    # 顶面亮分割
    for i in range(6):
        a = i * 60
        p = _poly(pos[0], pos[1], [(0.0, 0.0), (1.0, 0.0)], a, R)
        _line(surf, p[0], p[1], shade(base, 0.5), 1.2 * s)
    render.aaring(surf, lighten(base, 0.45), pos, int(R), max(1, int(s)))
    # 旋转炮管 + 炮口光
    deg = t * 80 % 360
    barrel = _poly(pos[0], pos[1], [(-0.2, -0.22), (1.55, -0.16), (1.55, 0.16), (-0.2, 0.22)], deg, R)
    render.aapolygon(surf, shade(base, 0.85), barrel)
    pygame.draw.aalines(surf, lighten(base, 0.35), True, barrel)
    muzzle = _poly(pos[0], pos[1], [(1.55, 0)], deg, R)[0]
    render.glow(surf, muzzle, R * 0.6, lighten(base, 0.5))
    # 炮塔头核心
    render.aacircle(surf, shade(base, 0.6), pos, int(R * 0.46))
    render.aacircle(surf, lighten(base, 0.7), pos, int(R * 0.3))
    render.glow(surf, pos, R * 0.9, shade(base, 0.5))
    _hp(surf, pos[0] - R, pos[1] - R - 8 * s, R * 2, tw.hp / tw.max_hp, s)


_MECH_LABEL = {"近接": "近", "炮击": "炮", "突击": "突", "支援": "支",
               "电磁": "磁", "工程": "工"}


# ---------------- 限时召唤物 ----------------
def draw_deployable(surf, d, t, s=1):
    name = type(d).__name__
    if name == "SlowField":
        _draw_slowfield(surf, d, s)
    elif name == "SentryTurret":
        _draw_sentry(surf, d, t, s)
    elif name == "HealDrone":
        _draw_drone(surf, d, s)


def _fade(d):
    """临近消失时淡出（最后 1.2s）。"""
    return max(0.2, min(1.0, d.life / 1.2))


def _draw_slowfield(surf, d, s):
    cx, cy = d.pos.x * s, d.pos.y * s
    R = d.radius * s
    f = _fade(d)
    base = d.color
    # 半透明力场填充
    fill = pygame.Surface((int(R * 2), int(R * 2)), pygame.SRCALPHA)
    pygame.draw.circle(fill, (base[0], base[1], base[2], int(45 * f)),
                       (int(R), int(R)), int(R))
    surf.blit(fill, (int(cx - R), int(cy - R)))
    # 双层旋转环
    render.aaring(surf, lighten(base, 0.3), (cx, cy), int(R), max(1, int(2 * s)))
    for k in range(12):
        a = k * 30 + d.anim * 60
        p = _poly(cx, cy, [(0.82, 0), (1.0, 0)], a, R)
        _line(surf, p[0], p[1], lighten(base, 0.5), 1.4 * s)
    render.aaring(surf, base, (cx, cy), int(R * 0.55), max(1, int(s)))
    # 中心磁轨钉
    render.glow(surf, (cx, cy), R * 0.4, base)
    render.aacircle(surf, lighten(base, 0.6), (cx, cy), max(2, int(R * 0.08)))


def _draw_sentry(surf, d, t, s):
    cx, cy = d.pos.x * s, d.pos.y * s
    R = d.radius * s
    f = _fade(d)
    base = d.color
    render.aaring(surf, C.C_RANGE_RING, (cx, cy), int(d.range * s), max(1, int(s)))
    render.soft_shadow(surf, Vector2(cx, cy), R + 2 * s, R)
    render.glow(surf, (cx, cy), R * 2.2, (40, 70, 100))
    # 三脚支架
    for k in range(3):
        a = k * 120 + 30
        leg = _poly(cx, cy, [(0.6, 0), (1.5, 0)], a, R)
        _line(surf, leg[0], leg[1], shade(base, 0.5), 2.2 * s)
        render.aacircle(surf, shade(base, 0.6), leg[1], max(1, int(R * 0.14)))
    # 六边底座 + 旋转炮管
    hexpts = [(math.cos(a), math.sin(a)) for a in [i * math.pi / 3 for i in range(6)]]
    render.aapolygon(surf, shade(base, 0.7), _poly(cx, cy, hexpts, 0, R))
    render.aaring(surf, lighten(base, 0.4), (cx, cy), int(R), max(1, int(s)))
    deg = t * 120 % 360
    barrel = _poly(cx, cy, [(-0.2, -0.18), (1.45, -0.13), (1.45, 0.13), (-0.2, 0.18)], deg, R)
    render.aapolygon(surf, lighten(base, 0.2), barrel)
    render.aacircle(surf, lighten(base, 0.7), (cx, cy), max(2, int(R * 0.36)))
    # 寿命环
    _life_ring(surf, cx, cy, R * 1.25, d.life / d.max_life, base, s)
    _ = f


def _draw_drone(surf, d, s):
    bob = math.sin(d.anim * 5) * 2 * s
    cx, cy = d.pos.x * s, d.pos.y * s + bob
    R = d.radius * s
    f = _fade(d)
    base = d.color
    render.soft_shadow(surf, Vector2(cx, d.pos.y * s + R * 1.4), R, R * 0.5)
    render.glow(surf, (cx, cy), R * 2.4, shade(base, 0.5))
    # 旋翼（横杆 + 两端旋叶）
    arm = _poly(cx, cy, [(-1.4, 0), (1.4, 0)], 0, R)
    _line(surf, arm[0], arm[1], shade(base, 0.6), 2 * s)
    for sgn in (-1, 1):
        rc = (cx + sgn * 1.4 * R, cy)
        render.aaring(surf, lighten(base, 0.4), rc, int(R * 0.5), max(1, int(s)))
    # 机体
    render.aacircle(surf, shade(base, 0.7), (cx, cy), int(R * 0.7))
    render.aacircle(surf, lighten(base, 0.4), (cx, cy), int(R * 0.45))
    # 医疗十字
    cw = max(1, int(R * 0.5))
    pygame.draw.line(surf, (235, 255, 240), (cx - cw, cy), (cx + cw, cy), max(2, int(2 * s)))
    pygame.draw.line(surf, (235, 255, 240), (cx, cy - cw), (cx, cy + cw), max(2, int(2 * s)))
    # 指向治疗目标的连线
    if getattr(d, "target", None) is not None and d.target.alive:
        pygame.draw.aaline(surf, C.C_BEAM_HEAL, (cx, cy),
                           (d.target.pos.x * s, d.target.pos.y * s))
    _ = f


def _life_ring(surf, cx, cy, r, frac, col, s):
    """顺时针消耗的寿命环。"""
    frac = max(0.0, min(1.0, frac))
    if frac <= 0:
        return
    start = -90
    end = start + 360 * frac
    pygame.draw.arc(surf, lighten(col, 0.3),
                    (cx - r, cy - r, r * 2, r * 2),
                    math.radians(start), math.radians(end), max(1, int(2 * s)))


# ---------------- 机兵 ----------------
def draw_mech(surf, m, wfont, t, selected, s=1):
    cx, cy = m.pos.x * s, m.pos.y * s
    deg = _deg(m.heading)
    R = m.radius * s
    base = _flash(m.color, m.hit_flash)
    dark = shade(base, 0.5)
    darker = shade(base, 0.32)
    light = lighten(base, 0.5)

    render.soft_shadow(surf, Vector2(cx, cy), R * 1.15, R * 0.9)
    render.glow(surf, (cx, cy), R * 2.7, shade(m.color, 0.5))

    if selected:
        pulse = 0.5 + 0.5 * math.sin(t * 6)
        render.aaring(surf, C.C_SELECT, (cx, cy), int(R + (7 + pulse * 2) * s), max(1, int(2 * s)))
        render.aaring(surf, C.C_RANGE_RING, (cx, cy), int(m.range * s), max(1, int(s)))

    # 路径（先画在身体下）
    if m.path:
        pts = [(cx, cy)] + [(p.x * s, p.y * s) for p in m.path]
        if len(pts) >= 2:
            pygame.draw.aalines(surf, (90, 120, 160), False, pts)
        rear = Vector2(cx, cy) - m.heading * (R + 2 * s)
        render.glow(surf, rear, R * 0.7, (120, 170, 255))

    # 后部推进腿 / 支架
    for sy in (-0.78, 0.78):
        leg = _poly(cx, cy, [(-0.9, sy * 0.6), (-1.35, sy * 1.05), (-1.05, sy * 1.15), (-0.65, sy * 0.78)], deg, R)
        render.aapolygon(surf, darker, leg)
    # 后部推进口辉光
    thr = _poly(cx, cy, [(-1.2, 0)], deg, R)[0]
    render.glow(surf, thr, R * 0.7, lighten(base, 0.3))

    # 武器臂（炮管）
    render.aapolygon(surf, darker,
                     _poly(cx, cy, [(0.1, -0.28), (1.5, -0.2), (1.5, 0.2), (0.1, 0.28)], deg, R))
    render.aacircle(surf, shade(base, 0.7), _poly(cx, cy, [(1.5, 0)], deg, R)[0], max(2, int(R * 0.16)))

    # 肩部装甲块（与机体咬合的梯形护肩，带受光高光）
    for sy in (-1, 1):
        sh = _poly(cx, cy, [(-0.55, sy * 0.45), (0.45, sy * 0.5),
                            (0.38, sy * 0.92), (-0.62, sy * 0.85)], deg, R)
        render.aapolygon(surf, dark, sh)
        hi = _poly(cx, cy, [(-0.5, sy * 0.5), (0.4, sy * 0.55), (0.3, sy * 0.7), (-0.55, sy * 0.65)], deg, R)
        render.aapolygon(surf, shade(light, 0.8), hi)

    # 主机体：底层暗描边 + 主体 + 顶部高光板
    hull = [(-1.05, -0.7), (0.45, -0.85), (1.2, 0), (0.45, 0.85), (-1.05, 0.7)]
    render.aapolygon(surf, darker, _poly(cx, cy, hull, deg, R * 1.07))
    render.aapolygon(surf, base, _poly(cx, cy, hull, deg, R))
    # 顶部高光斜板（上半身受光）
    top = [(-0.9, -0.6), (0.4, -0.72), (1.0, -0.1), (-0.3, -0.18)]
    render.aapolygon(surf, lighten(base, 0.28), _poly(cx, cy, top, deg, R))
    # 中线面板缝
    seam = _poly(cx, cy, [(-0.95, 0), (1.1, 0)], deg, R)
    _line(surf, seam[0], seam[1], darker, 1.3 * s)
    pygame.draw.aalines(surf, light, True, _poly(cx, cy, hull, deg, R))

    # 头部 / 传感器 + 驾驶舱发光眼
    head = _poly(cx, cy, [(0.5, -0.28), (1.0, -0.16), (1.0, 0.16), (0.5, 0.28)], deg, R)
    render.aapolygon(surf, shade(base, 0.55), head)
    eye = _poly(cx, cy, [(0.82, 0)], deg, R)[0]
    render.glow(surf, eye, R * 0.4, lighten(base, 0.5))
    render.aacircle(surf, lighten(base, 0.85), eye, max(2, int(R * 0.18)))
    render.aacircle(surf, (250, 252, 245), eye, max(1, int(R * 0.08)))

    label = _MECH_LABEL.get(m.type, m.type[0])
    img = wfont.render(label, True, (12, 15, 22))
    surf.blit(img, img.get_rect(center=(cx, cy)))

    # 状态：增益光环（校准=橙 / 过载=黄），仅描双环不加中心辉光，避免冲白本体
    if m.buff_timer > 0:
        bc = (255, 170, 90) if m.buff_kind == "calibrate" else (255, 230, 110)
        pulse = 0.5 + 0.5 * math.sin(t * 7)
        render.aaring(surf, bc, (cx, cy), int(R * (1.32 + 0.08 * pulse)), max(1, int(2 * s)))
        render.aaring(surf, shade(bc, 0.7), (cx, cy), int(R * 1.5), max(1, int(s)))
    # 状态：护盾（青色六边能量罩，仅描边）
    if m.shield > 0:
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        sh = [(math.cos(a), math.sin(a)) for a in [i * math.pi / 3 + t for i in range(6)]]
        pts = _poly(cx, cy, sh, 0, R * (1.45 + 0.06 * pulse))
        pygame.draw.aalines(surf, (140, 215, 255), True, pts)

    _hp(surf, cx - R, cy - R - 10 * s, R * 2, m.hp / m.max_hp, s)
    if m.forced_target is not None and getattr(m.forced_target, "alive", False):
        pygame.draw.aaline(surf, (255, 120, 120), (cx, cy),
                           (m.forced_target.pos.x * s, m.forced_target.pos.y * s))


# ---------------- 敌人 ----------------
def draw_enemy(surf, e, t, s=1):
    cx, cy, R = e.pos.x * s, e.pos.y * s, e.radius * s
    render.soft_shadow(surf, Vector2(cx, cy), R + s, R)
    _ENEMY_DRAW.get(e.type, _draw_generic)(surf, e, t, s)
    # 状态：冻结（白蓝脉冲）/ 减速（蓝环）
    if e.stun_timer > 0:
        pulse = 0.5 + 0.5 * math.sin(t * 10)
        render.glow(surf, (cx, cy), R * 1.7, (40, 80, 120))
        render.aaring(surf, (190, 235, 255), (cx, cy), int(R * (1.25 + 0.08 * pulse)), max(1, int(2 * s)))
        for i in range(4):
            p = _poly(cx, cy, [(1.15, 0)], i * 90 + t * 40, R)[0]
            render.aacircle(surf, (210, 240, 255), p, max(1, int(R * 0.12)))
    elif e.slow_factor < 0.999:
        render.aaring(surf, (110, 175, 235), (cx, cy), int(R * 1.22), max(1, int(s)))
    _hp(surf, cx - R, cy - R - 8 * s, R * 2, e.hp / e.max_hp, s)


def _draw_generic(surf, e, t, s):
    cx, cy, R = e.pos.x * s, e.pos.y * s, e.radius * s
    base = _flash(e.color, e.hit_flash)
    render.glow(surf, (cx, cy), R * 2.2, shade(e.color, 0.5))
    render.aacircle(surf, shade(base, 0.6), (cx, cy), int(R))
    render.aacircle(surf, base, (cx, cy), int(R * 0.82))
    render.aaring(surf, lighten(base, 0.4), (cx, cy), int(R), max(1, int(s)))


def _draw_spider(surf, e, t, s):
    cx, cy = e.pos.x * s, e.pos.y * s
    deg = _deg(e.heading)
    R = e.radius * s
    base = _flash(e.color, e.hit_flash)
    render.glow(surf, (cx, cy), R * 2.2, shade(e.color, 0.45))
    # 八条带关节的腿
    for i in range(8):
        ang = i * 45 + 22
        swing = math.sin(t * 9 + i) * 6
        knee = _poly(cx, cy, [(1.05, 0)], deg + ang + swing, R)[0]
        tip = _poly(cx, cy, [(1.85, 0)], deg + ang + swing * 1.6, R)[0]
        _line(surf, (cx, cy), knee, shade(base, 0.55), 2.2 * s)
        _line(surf, knee, tip, shade(base, 0.7), 1.6 * s)
        render.aacircle(surf, shade(base, 0.8), knee, max(1, int(R * 0.12)))
    # 甲壳：暗底 + 主体 + 高光
    render.aacircle(surf, shade(base, 0.45), (cx, cy), int(R * 1.0))
    render.aacircle(surf, base, (cx, cy), int(R * 0.82))
    render.aacircle(surf, lighten(base, 0.25),
                    _poly(cx, cy, [(-0.2, -0.2)], deg, R)[0], int(R * 0.4))
    render.aaring(surf, lighten(base, 0.5), (cx, cy), int(R * 0.82), max(1, int(s)))
    # 复眼
    eye = _poly(cx, cy, [(0.45, 0)], deg, R)[0]
    render.glow(surf, eye, R * 0.7, (255, 70, 70))
    render.aacircle(surf, (255, 130, 120), eye, max(2, int(R * 0.28)))
    render.aacircle(surf, (255, 230, 220), eye, max(1, int(R * 0.1)))


def _draw_armored(surf, e, t, s):
    cx, cy = e.pos.x * s, e.pos.y * s
    deg = _deg(e.heading)
    R = e.radius * s
    base = _flash(e.color, e.hit_flash)
    render.glow(surf, (cx, cy), R * 2.0, shade(e.color, 0.4))
    # 履带 / 底盘
    for sy in (-1, 1):
        tr = _poly(cx, cy, [(-1.0, sy * 0.7), (0.9, sy * 0.7), (0.9, sy * 1.02), (-1.0, sy * 1.02)], deg, R)
        render.aapolygon(surf, shade(base, 0.4), tr)
    # 重甲外壳：暗底 + 主体 + 顶部受光斜面
    hull = [(-1.0, -0.95), (0.65, -0.95), (1.15, 0), (0.65, 0.95), (-1.0, 0.95), (-1.3, 0)]
    render.aapolygon(surf, shade(base, 0.55), _poly(cx, cy, hull, deg, R * 1.05))
    render.aapolygon(surf, shade(base, 0.82), _poly(cx, cy, hull, deg, R))
    top = [(-0.95, -0.85), (0.6, -0.85), (1.0, -0.1), (-1.2, -0.1)]
    render.aapolygon(surf, lighten(base, 0.22), _poly(cx, cy, top, deg, R))
    pygame.draw.aalines(surf, lighten(base, 0.4), True, _poly(cx, cy, hull, deg, R))
    # 装甲缝
    for yy in (-0.45, 0.45):
        p = _poly(cx, cy, [(-1.0, yy), (0.9, yy)], deg, R)
        _line(surf, p[0], p[1], shade(base, 0.5), 1.2 * s)
    # 炽热核心
    render.glow(surf, (cx, cy), R * 1.0, (255, 150, 90))
    render.aacircle(surf, (255, 180, 120), (cx, cy), max(3, int(R * 0.34)))
    render.aacircle(surf, (255, 235, 200), (cx, cy), max(1, int(R * 0.14)))


def _draw_flyer(surf, e, t, s):
    cx, cy = e.pos.x * s, e.pos.y * s
    deg = _deg(e.heading)
    R = e.radius * s
    base = _flash(e.color, e.hit_flash)
    flap = abs(math.sin(t * 16)) * 0.5 + 0.5
    render.glow(surf, (cx, cy), R * 2.0, shade(e.color, 0.45))
    # 双翼（带膜与骨）
    for sgn in (-1, 1):
        wing = _poly(cx, cy, [(-0.2, 0), (-1.1, -1.1 * sgn * flap),
                              (0.2, -0.9 * sgn * flap), (0.45, -0.25 * sgn)], deg, R)
        render.aapolygon(surf, lighten(base, 0.32), wing)
        rib = _poly(cx, cy, [(-0.15, -0.1 * sgn), (-0.9, -0.95 * sgn * flap)], deg, R)
        _line(surf, rib[0], rib[1], shade(base, 0.6), 1.3 * s)
    # 流线躯体
    body = _poly(cx, cy, [(1.2, 0), (0.1, 0.55), (-0.95, 0), (0.1, -0.55)], deg, R)
    render.aapolygon(surf, shade(base, 0.6), body)
    render.aapolygon(surf, base, _poly(cx, cy, [(0.95, 0), (0.05, 0.4), (-0.7, 0), (0.05, -0.4)], deg, R))
    pygame.draw.aalines(surf, lighten(base, 0.5), True, body)
    # 头部光点
    eye = _poly(cx, cy, [(0.85, 0)], deg, R)[0]
    render.glow(surf, eye, R * 0.5, (255, 220, 120))
    render.aacircle(surf, (255, 240, 190), eye, max(1, int(R * 0.18)))


def _draw_bomber(surf, e, t, s):
    cx, cy, R = e.pos.x * s, e.pos.y * s, e.radius * s
    base = _flash(e.color, e.hit_flash)
    pulse = 0.5 + 0.5 * math.sin(t * 12)
    r = R * (0.82 + 0.22 * pulse)
    render.glow(surf, (cx, cy), R * (2.3 + pulse), (255, int(90 + 90 * pulse), 50))
    # 外部尖刺
    for i in range(8):
        a = _poly(cx, cy, [(r / R, 0)], i * 45 + t * 30, R)[0]
        b = _poly(cx, cy, [(r / R + 0.45, 0)], i * 45 + t * 30, R)[0]
        _line(surf, a, b, shade(base, 0.85), 2.0 * s)
    # 不稳定外壳
    render.aacircle(surf, shade(base, 0.55), (cx, cy), int(r))
    render.aacircle(surf, base, (cx, cy), int(r * 0.8))
    # 过载核心（白热脉动）
    render.glow(surf, (cx, cy), r * 1.4, (255, 200, 120))
    render.aacircle(surf, (255, 245, 180), (cx, cy), max(3, int(r * (0.32 + 0.1 * pulse))))
    render.aacircle(surf, (255, 255, 240), (cx, cy), max(1, int(r * 0.14)))


_ENEMY_DRAW = {
    "蛛型": _draw_spider,
    "重甲": _draw_armored,
    "飞蝗": _draw_flyer,
    "爆冲": _draw_bomber,
}
