"""无窗口冒烟测试：在 dummy 视频/音频驱动下驱动完整游戏循环，验证不崩溃。

两套测试：
1. 逻辑冒烟——跑完整波次（出怪/战斗/清波/胜负），验证主循环与战斗逻辑。
2. 交互冒烟——选中机兵、释放 Q/E 与全局技能（含点位瞄准）、并在这些状态下绘制
   HUD，覆盖自动循环不会触及的输入/UI 路径（历史 bug 多藏于此）。

供 CI 调用：`python smoke_test.py`，失败时抛异常非零退出。
"""
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["BATTLE_GAME_SAVE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              ".smoke_save.json")   # 隔离存档，避免污染用户目录

import pygame
from pygame.math import Vector2

import config as C
from game import Game
from main import load_fonts


def _new_game():
    fonts, wfonts = load_fonts()
    g = Game(fonts, wfonts)
    g._start_game()      # 跳过开局菜单（MENU → BUILD）
    return g


def logic_smoke(screen):
    """跑到分出胜负或上限帧数，验证整局不崩。"""
    g = _new_game()
    g.start_wave()
    cleared = 0
    for _ in range(60 * 60 * 4):
        g.update(1 / 60)
        g.draw(screen)
        if g.state == "BUILD":
            cleared += 1
            g.start_wave()
        if g.state in ("WON", "LOST"):
            break
    assert g.state in ("WON", "LOST"), f"未在上限帧内分出胜负，停在 {g.state}"
    print(f"  逻辑冒烟 OK -> {g.state}，清波 {cleared}")


def interaction_smoke(screen):
    """驱动选中/瞄准/技能/全局技能 + 带这些状态绘制 HUD。"""
    g = _new_game()
    g.start_wave()
    for _ in range(90):
        g.update(1 / 60)
    target = Vector2(g.terminal.pos) + Vector2(50, 0)

    def click(x, y, button=1):
        ev = type("E", (), {})()
        ev.type = pygame.MOUSEBUTTONDOWN
        ev.button = button
        ev.pos = (int(x), int(y))
        g._on_mouse_down(ev)

    # 逐个机兵：选中 -> 画 HUD -> Q/E（点位则点击释放）-> 画 HUD
    for m in g.mechs:
        g.selected_mech = m
        m.selected = True
        g.draw(screen)
        for slot in range(len(m.abilities)):
            m.energy = m.max_energy
            m.ability_timers[slot] = 0
            g._try_ability(slot)
            g.draw(screen)
            if g.aiming is not None:
                click(target.x, target.y)
            g.draw(screen)

    # 全局技能 Z/X/C
    for name in C.GLOBAL_SKILLS:
        g.resources = 300
        g.global_cd[name] = 0
        g._try_global(name)
        g.draw(screen)
        if g.aiming is not None:
            click(target.x, target.y)
        g.draw(screen)

    # 右键取消瞄准
    g.selected_mech = g.mechs[1]
    g.mechs[1].energy = 100
    g.mechs[1].ability_timers[0] = 0
    g._try_ability(0)
    assert g.aiming is not None, "点位技能未进入瞄准态"
    click(target.x, target.y, button=3)
    assert g.aiming is None, "右键未取消瞄准"
    g.draw(screen)
    print("  交互冒烟 OK")


def main():
    pygame.init()
    screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
    logic_smoke(screen)
    interaction_smoke(screen)
    pygame.quit()
    print("全部冒烟通过")


if __name__ == "__main__":
    main()
