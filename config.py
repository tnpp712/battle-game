"""全局配置：尺寸、颜色、平衡数值、机兵/敌人/建造/波次数据。"""

# ---------- 窗口 ----------
SCREEN_W = 1280
SCREEN_H = 820
FPS = 60
HUD_H = 140                      # 底部 HUD 高度
RENDER_SCALE = 2                 # 战场超采样倍率：以 2× 分辨率绘制再降采样，边缘更顺滑
FIELD_RECT = (0, 0, SCREEN_W, SCREEN_H - HUD_H)   # 战场区域

# ---------- 颜色 ----------
C_BG          = (16, 20, 30)
C_GRID        = (28, 34, 48)
C_FIELD_EDGE  = (60, 80, 120)
C_HUD_BG      = (12, 14, 20)
C_HUD_LINE    = (40, 48, 66)
C_TEXT        = (210, 220, 235)
C_TEXT_DIM    = (120, 130, 150)
C_TEXT_WARN   = (255, 180, 80)
C_TEXT_GOOD   = (120, 230, 150)
C_TEXT_BAD    = (255, 90, 90)

C_TERMINAL    = (90, 200, 255)
C_TERMINAL_HI = (160, 230, 255)
C_TERRAIN     = (52, 58, 74)
C_TERRAIN_HI  = (74, 82, 100)
C_WALL        = (150, 140, 110)
C_WALL_HI     = (200, 190, 150)
C_TOWER       = (180, 130, 220)
C_SELECT      = (255, 240, 120)
C_PATH_OK     = (120, 230, 150)
C_PATH_BAD    = (255, 90, 90)
C_HP_BACK     = (40, 44, 56)
C_HP_GOOD     = (90, 220, 120)
C_HP_MID      = (240, 200, 70)
C_HP_LOW      = (240, 90, 90)
C_BEAM_ALLY   = (140, 220, 255)
C_BEAM_ENEMY  = (255, 130, 110)
C_BEAM_HEAL   = (130, 255, 170)
C_RANGE_RING  = (70, 90, 120)

# ---------- 机兵类型 ----------
# role: melee / ranged / support
# 每个机兵两个技能（Q=slot0, E=slot1），数据驱动，由 entities._ABILITY_FX 分派：
#   key   : 显示用按键
#   target: self（瞬发自身为中心） / point（鼠标点位） / enemy（鼠标指定敌人）
#   cost  : 能量消耗      cd: 冷却秒
#   effect: 效果 id（见 entities._ABILITY_FX）
#   其余 radius/value/duration 为效果参数
MECH_TYPES = {
    "近接": dict(role="melee",   color=(255, 120, 90),  radius=16,
                 hp=420, speed=130, range=46, damage=34, attack_cd=0.55,
                 can_hit_flying=False, splash=0, energy=100, energy_regen=16,
                 abilities=[
                     dict(key="Q", name="震荡冲击", target="self",  cost=35, cd=8.0,
                          effect="shock", radius=120, value=90, duration=1.3),
                     dict(key="E", name="战术突进", target="point", cost=45, cd=10.0,
                          effect="dash", radius=92, value=70),
                 ]),
    "炮击": dict(role="ranged",  color=(120, 180, 255), radius=15,
                 hp=240, speed=95,  range=240, damage=26, attack_cd=1.1,
                 can_hit_flying=True, splash=55, energy=100, energy_regen=12,
                 abilities=[
                     dict(key="Q", name="饱和轰炸", target="point", cost=45, cd=10.0,
                          effect="barrage", radius=140, value=70),
                     dict(key="E", name="校准模式", target="self",  cost=40, cd=14.0,
                          effect="calibrate", duration=6.0, value=1.6),
                 ]),
    "突击": dict(role="ranged",  color=(255, 210, 120), radius=14,
                 hp=200, speed=170, range=150, damage=16, attack_cd=0.32,
                 can_hit_flying=True, splash=0, energy=100, energy_regen=14,
                 abilities=[
                     dict(key="Q", name="弹幕扫射", target="self", cost=30, cd=7.0,
                          effect="strafe", value=10),
                     dict(key="E", name="过载冲锋", target="self", cost=40, cd=11.0,
                          effect="overdrive", duration=5.0, value=2.0),
                 ]),
    "支援": dict(role="support", color=(140, 235, 170), radius=15,
                 hp=260, speed=120, range=170, damage=0, attack_cd=0.6,
                 can_hit_flying=True, splash=0, heal=22, energy=100, energy_regen=14,
                 abilities=[
                     dict(key="Q", name="过载治疗", target="self",  cost=40, cd=12.0,
                          effect="heal_all", value=120),
                     dict(key="E", name="力场护盾", target="point", cost=45, cd=12.0,
                          effect="barrier", radius=150, value=120, duration=8.0),
                 ]),
    "电磁": dict(role="ranged",  color=(180, 130, 235), radius=15,
                 hp=220, speed=110, range=160, damage=12, attack_cd=0.7,
                 can_hit_flying=True, splash=0, energy=100, energy_regen=15,
                 abilities=[
                     dict(key="Q", name="静电脉冲", target="self",  cost=35, cd=8.0,
                          effect="emp_pulse", radius=135, value=30, duration=1.7),
                     dict(key="E", name="磁轨钉", target="point", cost=45, cd=11.0,
                          effect="slow_field", radius=110, duration=6.0, value=18, slow=0.45),
                 ]),
    "工程": dict(role="ranged",  color=(120, 210, 200), radius=15,
                 hp=240, speed=115, range=150, damage=14, attack_cd=0.6,
                 can_hit_flying=True, splash=0, energy=100, energy_regen=13,
                 abilities=[
                     dict(key="Q", name="部署哨戒炮", target="point", cost=45, cd=12.0,
                          effect="deploy_turret", value=12),
                     dict(key="E", name="维修无人机", target="point", cost=40, cd=13.0,
                          effect="heal_drone", value=14),
                 ]),
}

# 兵种池 / 解锁 / 出战
MECH_POOL = ["近接", "炮击", "突击", "支援", "电磁", "工程"]
STARTING_UNLOCKED = ["近接", "炮击", "突击", "支援"]   # 初始解锁 4 种
SQUAD_MAX = 5                                          # 单局最多出战
# 解锁规则：达到任一条件即解锁（best_wave=历史最高到达波，wins=通关次数）
UNLOCK_RULES = {
    "电磁": dict(best_wave=4, wins=1),
    "工程": dict(best_wave=6, wins=2),
}
# 初始小队（出场即拥有的机兵，用作默认出战阵容）
STARTING_SQUAD = ["近接", "炮击", "突击", "支援", "电磁", "工程"]

# ---------- 可部署物（技能召唤，限时存在）----------
SENTRY     = dict(range=200, damage=18, attack_cd=0.5, radius=14, color=(150, 210, 255))
SLOW_FIELD = dict(color=(170, 130, 235))          # 半径/减速/dps/时长由技能 spec 提供
HEAL_DRONE = dict(range=150, heal=20, cd=0.7, radius=9, color=(140, 235, 180))

# ---------- 终端全局技能（不绑机兵，消耗资源）----------
GLOBAL_SKILLS = {
    "orbital":   dict(key="Z", name="轨道炮",   target="point", cost=60, cd=18.0,
                      effect="orbital", radius=130, value=260),
    "overclock": dict(key="X", name="全场过载", target="self",  cost=50, cd=22.0,
                      effect="overclock", duration=6.0, value=1.6),
    "timewarp":  dict(key="C", name="时滞力场", target="self",  cost=45, cd=20.0,
                      effect="timewarp", duration=5.0, value=0.4),
}

# ---------- 敌人类型 ----------
# 行为标志（Enemy 读取）：bomber 自爆；flying 无视障碍直冲；attack_range 远程攻击距离；
# shield 自带护盾；shield_aura=(护盾量,半径) 给周围敌人加盾；heal_aura=(每跳治疗,半径)；
# split=(子类型,数量) 死亡分裂；boss 首领（造型/震屏）。
ENEMY_TYPES = {
    "蛛型": dict(color=(180, 90, 110),  radius=12, hp=70,  speed=70,  damage=9,  attack_cd=0.8, flying=False, reward=8),
    "重甲": dict(color=(120, 100, 90),  radius=20, hp=320, speed=42,  damage=22, attack_cd=1.2, flying=False, reward=20),
    "飞蝗": dict(color=(200, 160, 90),  radius=11, hp=55,  speed=95,  damage=7,  attack_cd=0.7, flying=True,  reward=12),
    "爆冲": dict(color=(255, 110, 70),  radius=14, hp=90,  speed=120, damage=60, attack_cd=0.1, flying=False, reward=15, bomber=True),
    "分裂体": dict(color=(205, 120, 205), radius=16, hp=130, speed=58, damage=14, attack_cd=1.0, flying=False, reward=18, split=("蛛型", 3)),
    "护盾兵": dict(color=(110, 160, 215), radius=18, hp=190, speed=44, damage=18, attack_cd=1.2, flying=False, reward=26, shield=120, shield_aura=(60, 130)),
    "治疗兵": dict(color=(110, 210, 150), radius=14, hp=150, speed=56, damage=8,  attack_cd=1.0, flying=False, reward=24, heal_aura=(14, 135)),
    "远程兵": dict(color=(230, 165, 90),  radius=13, hp=95,  speed=58, damage=16, attack_cd=1.4, flying=False, reward=20, attack_range=175),
    "首领": dict(color=(225, 80, 120),    radius=34, hp=3000, speed=32, damage=46, attack_cd=1.0, flying=False, reward=240, attack_range=160, boss=True),
}

# ---------- 建造物 / 基地升级 ----------
BUILD_ITEMS = {
    "wall":  dict(label="阻挡墙 [1]",  key="1", cost=20,  hp=260, w=64, h=24),
    "tower": dict(label="自动炮塔 [2]", key="2", cost=55,  hp=160, range=180, damage=15, attack_cd=0.55, radius=18),
}
# 基地升级：可重复购买，费用随等级递增
BASE_UPGRADES = {
    "repair": dict(label="维修基站 [3]", key="3", base_cost=70,  desc="治疗范围内的机兵"),
    "shield": dict(label="护盾发生器 [4]", key="4", base_cost=70, desc="提升终端血量与回复"),
    "radar":  dict(label="雷达阵列 [5]", key="5", base_cost=60,  desc="提升所有炮塔射程"),
}

# ---------- 终端（要守护的核心） ----------
TERMINAL_HP = 1500
TERMINAL_RADIUS = 40

# ---------- 波次 ----------
# 每波: enemies = [(类型, 数量), ...], interval = 出怪间隔(秒), reward = 通关奖励
WAVES = [
    dict(enemies=[("蛛型", 8)],                                      interval=1.1, reward=80),
    dict(enemies=[("蛛型", 10), ("飞蝗", 4)],                        interval=0.95, reward=110),
    dict(enemies=[("蛛型", 8), ("重甲", 2), ("远程兵", 4)],          interval=0.9, reward=140),
    dict(enemies=[("飞蝗", 10), ("爆冲", 3), ("治疗兵", 2)],         interval=0.85, reward=170),
    dict(enemies=[("重甲", 4), ("分裂体", 4), ("护盾兵", 2), ("远程兵", 4)], interval=0.75, reward=210),
    dict(enemies=[("重甲", 6), ("飞蝗", 12), ("爆冲", 5), ("治疗兵", 3), ("护盾兵", 2)], interval=0.65, reward=270),
    dict(enemies=[("首领", 1), ("护盾兵", 3), ("分裂体", 4), ("远程兵", 6)], interval=0.7, reward=420),  # Boss 波
]

START_RESOURCES = 120

# ---------- 局内 Roguelite 升级（每清一波三选一，按 effect 分派）----------
UPGRADES = [
    dict(id="dmg",     name="强化武器", desc="全体机兵伤害 +20%",         effect="mech_dmg",    value=0.20),
    dict(id="hp",      name="强化装甲", desc="全体机兵血量上限 +25% 并修复", effect="mech_hp",     value=0.25),
    dict(id="energy",  name="能量核心", desc="全体机兵能量回复 +5/秒",     effect="mech_energy", value=5),
    dict(id="speed",   name="推进升级", desc="全体机兵移动速度 +15%",      effect="mech_speed",  value=0.15),
    dict(id="cd",      name="战术冷却", desc="全体机兵技能冷却 -15%",      effect="mech_cd",     value=0.15),
    dict(id="atkspd",  name="超频枪管", desc="全体机兵攻速 +18%",          effect="mech_atkspd", value=0.18),
    dict(id="reward",  name="资源采集", desc="资源获取 +25%",             effect="reward",      value=0.25),
    dict(id="term",    name="终端强化", desc="终端血量上限 +400 并修复",   effect="term_hp",     value=400),
]

# ---------- 难度 ----------
# hp/speed/count/reward 为对敌人对应数值的乘子
DIFFICULTIES = {
    "简单": dict(hp=0.75, speed=0.9,  count=0.8,  reward=1.25),
    "普通": dict(hp=1.0,  speed=1.0,  count=1.0,  reward=1.0),
    "困难": dict(hp=1.4,  speed=1.1,  count=1.25, reward=0.85),
}
DIFFICULTY_ORDER = ["简单", "普通", "困难"]
DEFAULT_DIFFICULTY = "普通"
