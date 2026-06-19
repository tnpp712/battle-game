"""入口：初始化 pygame、加载中文字体、运行主循环。"""
import os
import sys
import pygame

import config as C
from game import Game


# macOS 上常见的中文字体路径，按优先级尝试
CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


_FONT_SIZES = {"tiny": 14, "small": 18, "mid": 24, "big": 48}


def _font_maker():
    path = next((p for p in CJK_FONT_CANDIDATES if os.path.exists(p)), None)
    if path:
        return lambda s: pygame.font.Font(path, s)
    # 退而求其次，用系统字体（可能无法显示中文）
    name = pygame.font.match_font("pingfangsc, stheiti, arialunicode, applegothic") or None
    return lambda s: (pygame.font.Font(name, s) if name else pygame.font.SysFont(None, s))


def load_fonts():
    """返回 (hud_fonts, world_fonts)。world_fonts 按 RENDER_SCALE 放大，
    用于在 2× 超采样画布上绘制单位标签/伤害数字，降采样后与 HUD 字号一致。"""
    mk = _font_maker()
    fonts = {k: mk(v) for k, v in _FONT_SIZES.items()}
    wfonts = {k: mk(v * C.RENDER_SCALE) for k, v in _FONT_SIZES.items()}
    return fonts, wfonts


def main():
    pygame.init()
    pygame.display.set_caption("机兵防卫圈 — 崩坏战")
    screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
    clock = pygame.time.Clock()
    fonts, wfonts = load_fonts()
    game = Game(fonts, wfonts)

    running = True
    while running:
        dt = min(clock.tick(C.FPS) / 1000.0, 1.0 / 30.0)  # 限制最大步长，防穿模
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and \
                    (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                running = False   # Shift+ESC 退出
            else:
                game.handle_event(ev)
        game.update(dt)
        game.draw(screen)
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
