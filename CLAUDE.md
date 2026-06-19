# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 沟通约定：本仓库的所有思考过程、回复与文档一律使用**中文**。
>
> 提交约定：**git 提交信息中不得出现任何 AI 署名**——不要添加 `Co-Authored-By: Claude ...`、`Generated with Claude` 等字样。提交信息只写实际改动内容。

## 项目概述

模仿《十三机兵防卫圈》崩坏战模式的塔防 / 即时策略游戏（无剧情）。Python + Pygame，纯矢量绘制、无外部素材。玩家指挥机兵小队守护中央终端，抵御波次来袭的机械兽，并可在战场布防、升级基地。

## 常用命令

```bash
pip install -r requirements.txt      # 安装依赖（仅 pygame）
pkill -f "main.py"; python3 main.py  # 启动游戏窗口（先关旧实例）
```

无构建步骤、无 lint 配置、无测试框架。

**重要：每次启动游戏窗口测试前，必须先关闭之前打开的实例**，否则 Dock 里会堆积多个窗口。统一用 `pkill -f "main.py"` 关掉所有旧实例后再启动；用 `pgrep -fl "python3 main.py"` 确认是否还有残留。

**冒烟测试**（无窗口、跑完整循环验证不崩溃）——改动核心逻辑后建议执行：

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 - <<'PY'
import os; os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"
import pygame; from game import Game; from main import load_fonts
import config as C
pygame.init(); screen=pygame.display.set_mode((C.SCREEN_W,C.SCREEN_H))
fonts, wfonts = load_fonts(); g=Game(fonts, wfonts); g.start_wave()
for _ in range(60*60*3):
    g.update(1/60); g.draw(screen)
    if g.state=="BUILD": g.start_wave()
    if g.state in ("WON","LOST"): break
print("OK", g.state); pygame.quit()
PY
```

用 `SDL_VIDEODRIVER=dummy` 即可在无显示环境下驱动整个游戏循环——这是验证逻辑改动的主要手段。

**但上面的冒烟只驱动「自动战斗循环」，从不选中机兵、不进技能瞄准、不在「有选中机兵/瞄准中」状态下画 HUD**——而历史上两次"按 Q/启动即崩"的 bug 恰恰藏在这些路径里。改动**输入 / HUD / 技能 / 瞄准 / 选中态**后，务必再跑一遍交互冒烟（覆盖 `_try_ability` / `_try_global` / `_cast_aimed` / 选中态下的 `hud.draw`）：

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 - <<'PY'
import os; os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"
import pygame; from game import Game; from main import load_fonts
import config as C; from pygame.math import Vector2
pygame.init(); screen=pygame.display.set_mode((C.SCREEN_W,C.SCREEN_H))
fonts, wfonts = load_fonts(); g=Game(fonts, wfonts); g.start_wave()
for _ in range(90): g.update(1/60)
TP=Vector2(g.terminal.pos)+Vector2(50,0)
def click(x,y,b=1):
    e=type("E",(),{})(); e.type=pygame.MOUSEBUTTONDOWN; e.button=b; e.pos=(int(x),int(y)); g._on_mouse_down(e)
for m in g.mechs:                       # 逐兵：选中→画HUD→Q/E→（点位则点击释放）→画HUD
    g.selected_mech=m; m.selected=True; g.draw(screen)
    for slot in range(2):
        m.energy=m.max_energy; m.ability_timers[slot]=0; g._try_ability(slot); g.draw(screen)
        if g.aiming is not None: click(TP.x,TP.y)
        g.draw(screen)
for name in C.GLOBAL_SKILLS:            # 全局技能 Z/X/C
    g.resources=300; g.global_cd[name]=0; g._try_global(name); g.draw(screen)
    if g.aiming is not None: click(TP.x,TP.y)
    g.draw(screen)
print("INTERACTION SMOKE OK"); pygame.quit()
PY
```

## 易错点与经验（改代码前必读）

这些是本项目反复踩中、且 dummy 冒烟未必能直接暴露的坑：

1. **改共享接口/状态的「形状」时，必须同步所有读取方。** 历史 bug：`load_fonts()` 由返回单 dict 改成返回 `(fonts, wfonts)` 元组；`Game.aiming` 由元组 `(mech,slot,spec)` 改成 `dict(...)`——后者漏改 `ui.py` 里 `aiming[0]` 的下标访问，按 Q 进瞄准后下一帧 `draw` 抛 `KeyError` 直接崩。**做法**：改完签名/字段形状后，`grep` 出每一处读取点逐一更新，再跑交互冒烟。
2. **战斗态计时只在 WAVE 且未暂停时推进。** `Mech._tick_status`（能量回复、`buff_timer`/`root_timer`/`shield_timer`、技能冷却 `ability_timers`）只在 `update_combat` 里跑，而它仅在 `_update_wave` 调用。**推论**：这些计时在 BUILD/暂停期**不会自然归零**——若放任，可能把「生根/增益」状态带进 BUILD（机兵卡住不能动）。跨波切换必须显式复位：见 `_wave_cleared` 里对每个机兵复位 mults/buff/root/shield、补满能量、清零冷却，并清空 `deployables`/`aiming`。新增任何「战斗期计时」状态时，记得在 `_wave_cleared` 一并复位。
3. **数据驱动的分派若 id 拼错会「静默失效」。** `Mech.use_ability` 查不到 `_ABILITY_FX[effect]` 时返回 False（不报错）；`Game._do_global` 的 `if/elif` 无 `else`。新增技能时务必让 `config` 里的 `effect` 与注册表/分支一一对应，否则表现为「按键/扣资源却无效果」。可用 `for ... in MECH_TYPES: assert effect in _ABILITY_FX` 自检。
4. **超采样 `s` 约定不可半截。** 战场绘制全部在 2× 画布上，坐标/尺寸都要乘 `s`、形状点用半径比例表达（详见下文渲染节）。漏乘 `s` 不会崩，但会「只缩放了一半」导致错位/变形——视觉 bug 比崩溃更难发现，改 `sprites`/`particles`/`Beam.draw`/`game.draw` 的绘制时尤其注意。
5. **新增「可受击实体」三件套。** 任何会进 `take_damage` 的实体都要有 `_dmg_taken` + `hit_flash` 字段并在 `take_damage` 维护，否则 `Game._combat_fx` / `sprites.draw_*` 读 `hit_flash` 会崩。（可部署物不可受击、不进 `_combat_fx`，故无此要求。）
6. **改完即跑两套冒烟 + 真机窗口。** 逻辑改动跑自动冒烟；输入/HUD/技能改动加跑交互冒烟；视觉改动 `pkill -f main.py` 后重启窗口（或 dummy 下 `pygame.image.save` 存帧）肉眼确认。

## 架构

主循环在 [main.py](main.py)：`while` 循环每帧执行 `game.handle_event` → `game.update(dt)` → `game.draw(screen)`。`dt` 被限制在 `1/30` 秒以内防止穿模。

[game.py](game.py) 的 `Game` 类是唯一的协调中心，持有全部游戏状态（实体列表、终端、资源、波次、流场、选中态、输入态），并把更新与渲染编排起来。其余模块都是被它调用的纯粹组件。

### 状态机

`Game.state` 取值 `BUILD / WAVE / WON / LOST`，是理解全局行为的关键：

- **BUILD**：机兵可被路径指令移动（用于布防前调位），但无敌人、无战斗。按 `N`（`start_wave`）进入 WAVE。
- **WAVE**：实时推进。可按空格 `paused` 暂停下令（核心机制——暂停时一切冻结，但仍可选机兵、画路径、指定目标，松开后执行）。`_update_wave` 处理出怪、战斗、清理与胜负判定。清波后 `_wave_cleared` 发奖励、复活阵亡机兵、回到 BUILD，全部波次清完则 WON；终端血量归零则 LOST。
- 按 `R` 任何时候 `reset()` 重开。

`update()` 中：机兵移动在 BUILD/WAVE 且未暂停时都跑；战斗逻辑仅在 WAVE 且未暂停时跑。

### 寻路：流场（关键设计）

敌人**不**用局部转向避障（会卡死、卡死时退化成直线穿墙）。改用 [pathfield.py](pathfield.py) 的 `FlowField`：对整个战场网格从终端做 Dijkstra 距离场，每格预存指向最近邻格的流向量。敌人 `Enemy.update` 采样所在格的流向前进，天然绕开障碍。

- 流场在**障碍变化时**重算，不是每帧：建墙时 `_place_build` 直接调 `_rebuild_flow`；墙被打掉时 `_update_wave` 置 `_flow_dirty`，下一帧 `update` 开头重算。修改墙/地形相关逻辑时务必维护这条失效链路。
- 飞行敌人（`flying=True`，如「飞蝗」）**无视障碍**直冲终端，不走流场——这是设定，不是 bug。
- 被墙完全围死（`reachable_at` 为假）时，敌人会攻击挡路的墙破墙而入，作为兜底。

### 实体

[entities.py](entities.py) 定义所有实体，均为普通类，自身的 `update` 接收 `game` 引用以访问全局状态：

- `Terminal`：要守护的核心。升级等级 `repair_lv / shield_lv / radar_lv` 通过 `@property`（`repair_range`、`tower_range_bonus` 等）转化为实际效果。
- `Mech`：玩家机兵。`update_move`（沿 `path` 行进，建造期与战斗期共用）与 `update_combat`（自动索敌/治疗）分离。`role` 为 `melee/ranged/support`，support 用 `_do_support` 治疗而非攻击。`forced_target` 是玩家右键指定的优先目标。
  - **技能系统（数据驱动）**：每个机兵在 `config.MECH_TYPES[...]["abilities"]` 里配两个技能（slot0=Q、slot1=E），字段含 `target`（`self`/`point`/`enemy`）、`cost`（能量）、`cd`、`effect`（效果 id）。`Mech.use_ability(game, slot, target)` 校验 `can_use`（冷却+能量）后查 `entities._ABILITY_FX[effect]` 分派；新增技能=在 config 加条目 + 在 `_ABILITY_FX` 注册一个 `_fx_*(m, game, spec, target)` 函数，**不改 use_ability**。
  - **能量**：`energy`/`max_energy`/`energy_regen`，战斗中被动回能、攻击命中额外回能（`gain_energy`）；技能消耗能量。
  - **状态效果**：机兵有 `shield`(+timer)、`dmg_mult`/`range_mult`/`atkspd_mult`/`move_mult`(共用 `buff_timer`+`buff_kind`)、`root_timer`（生根不可移动）；敌人有 `slow_factor`(+timer)、`stun_timer`。均在各自 `_tick_status`/`update` 里推进并复位。战斗取值一律用 `eff_speed`/`eff_range`/`dmg_mult` 等有效值，新增涉及移动/攻击的逻辑务必走有效值而非原始字段。`take_damage` 对机兵先扣 `shield`。
- `Enemy`：来袭单位，靠流场移动，途中攻击贴近的机兵、到达后攻击终端、被围死时拆墙。
- `Tower` / `Wall`：自动炮塔 / 阻挡墙（墙是障碍物 + 可被攻击）。
- `Beam`：攻击/治疗的瞬时连线特效，带 TTL，每帧 `update` 衰减。
- **可部署物**（技能召唤，限时）：`SentryTurret`（自动炮台）/`SlowField`（减速灼烧力场）/`HealDrone`（治疗无人机）。统一接口 `update(dt, game) -> 存活bool`，存于 `Game.deployables`，在 `_update_wave` 里推进并用 `[d for d in ... if d.update(...)]` 清理；`Game.draw` 经 `sprites.draw_deployable`（按 `type(d).__name__` 分派）绘制。不可被攻击、不是障碍。参数在 `config.SENTRY/SLOW_FIELD/HEAL_DRONE`。
- **终端全局技能**（不绑机兵，耗资源）：`config.GLOBAL_SKILLS`（轨道炮 Z / 全场过载 X / 时滞力场 C）。`Game._try_global` 校验 `global_cd`+资源 → self 型即放、point 型走瞄准；`Game._do_global` 扣资源、置冷却、按 `effect` 分派效果。冷却在 `_update_wave` 里递减。
- **机兵兵种**：`config.STARTING_SQUAD` 现为 6 个（近接/炮击/突击/支援/电磁/工程）；电磁=控制（眩晕+减速力场）、工程=召唤（哨戒炮+治疗无人机）。所有机兵共用同一机甲剪影，靠 `color` 与 `sprites._MECH_LABEL` 的字标区分。

实体的朝向 `heading` 在移动时更新，供精灵旋转使用。

### 渲染（霓虹科幻发光风）

**超采样管线（关键）**：战场不直接画到窗口，而是画到 `Game.scene`——一块 `RENDER_SCALE`（=2，见 config）倍分辨率的离屏画布，每帧再用 `smoothscale` 降采样到 `Game._down` 并 blit 到窗口；HUD 之后才以原生 1× 直接画在窗口上（`ui.py` 不参与超采样，故保持 1× 坐标、未改动）。所以**所有战场绘制函数都接收一个缩放参数 `s`**（`sprites.draw_*` / `particles.draw*` / `Beam.draw` / `build_background`）：实体坐标/半径乘 `s`、形状点用半径比例表达，从而在 2× 画布上无失真。单位标签/伤害数字用 `Game.wfonts`（按 `RENDER_SCALE` 放大的字体）绘制，降采样后与 HUD 字号一致。改任何战场绘制时务必沿用 `s` 约定，否则会半截缩放导致变形。注：纯 Retina 屏上最终仍是 1280→2560 的系统拉伸，超采样主要提升边缘/抗锯齿质量与非 Retina/缩放分辨率场景的清晰度。

- [render.py](render.py)：底层渲染库。`aacircle/aaring/aapolygon` 用 `pygame.gfxdraw` 画**抗锯齿**图元；`glow()` 用缓存的径向渐变贴图以 `BLEND_RGB_ADD` 叠加**辉光/泛光**（按半径量化键缓存，`_glow_cache` 有界）；`beam()` 画发光光束；`build_background()` 一次性**烘焙背景**（径向渐变 + 双层网格 + 能量环 + 暗角），结果缓存在 `Game.bg`，每帧只 blit。
- [particles.py](particles.py)：`Particles` 管理命中火花、死亡爆炸（含冲击环）、推进器拖尾、伤害飘字。`Game._combat_fx` 每帧把实体累积的伤害（`_dmg_taken`）转成飘字+火花、衰减受击白闪（`hit_flash`），并在阵亡时触发爆炸。
- [sprites.py](sprites.py)：机兵/敌人/终端/炮塔/墙/障碍的造型，全部走 render 的抗锯齿+辉光，按 `heading` 旋转、受击 `hit_flash` 白闪、基于 `anim_time` 动画。障碍/墙纹理按尺寸缓存于 `_tile_cache`。敌人按类型查 `_ENEMY_DRAW` 分派。
- [ui.py](ui.py)：`HUD` 绘制信息栏与建造栏（带手绘图标、悬停高亮）；`HUD.buttons` 每帧填充 `{名称: Rect}` 供 `Game._click_hud` 命中检测——绘制与交互共用。`draw_hp_bar` 被各精灵复用。
- `Game.draw` 的绘制顺序（前段均画在 2× `scene` 上）：背景 → 障碍/墙 → 终端/炮塔 → 光束 → 敌人/机兵 → 粒子 → 路径/建造预览 → 伤害飘字 →（`smoothscale` 降采样到窗口）→ HUD。

**实体受击反馈链路**：任何 `take_damage` 都会累加 `_dmg_taken` 并置 `hit_flash`；`Game._combat_fx` 每帧统一消费。新增可受击实体时记得在 `__init__` 加这两个字段、在 `take_damage` 里维护，否则 `sprites.draw_*` 读 `hit_flash` 会报错。

### 几何

[geometry.py](geometry.py)：线段-矩形相交（`path_blocked` 用于校验玩家所画路径不穿障碍）、圆-矩形碰撞与解碰撞（`resolve_circle_rects` 防穿模）、`steer_around`（机兵移动时的局部避障）。

### 配置即平衡

[config.py](config.py) 是**唯一的调参入口**：窗口尺寸、颜色、机兵/敌人/建造物/基地升级的全部数值、波次定义（`WAVES`）、初始资源与小队。调难度、加单位类型、改造型配色都改这里。`ENEMY_TYPES` 加 `bomber=True`/`flying=True` 这类标志会被 `Enemy` 与 `sprites` 同时读取。

## 输入约定（改交互逻辑时参考）

事件全部经 `Game.handle_event` 分发。左键：点机兵=选中，选中后在空地拖拽=画移动路径（绿=合法/红=穿障碍），点建造栏按钮或场上空位=放置。右键：点敌人=指定攻击，点空地=停止。`空格`=暂停、`N`=下一波、`滚轮/Tab`=旋转挡墙、`ESC`=取消选择/建造/技能瞄准、`R`=重开。

**技能释放**：`Q`/`E` 触发所选机兵的 slot0/slot1（`_try_ability`）；`Z`/`X`/`C` 触发终端全局技能（`_try_global`）。`self` 型即时释放；`point`/`enemy` 型进入**瞄准态** `Game.aiming=dict(radius, src, cast)`（`cast` 为闭包，左键 `_cast_aimed` 调用之、右键/ESC 取消），瞄准时 `draw` 走 `_draw_aim_ghost` 画范围预览，左键被瞄准逻辑拦截不触发选中/画路径。机兵技能与全局技能共用这一套瞄准机制。
