"""极简存档：解锁兵种与最佳战绩，JSON 持久化。

存档路径默认 ~/.battle_game_save.json，可用环境变量 BATTLE_GAME_SAVE 覆盖
（测试/CI 指向临时文件，避免污染用户目录）。读写失败一律静默降级，不影响游戏。
"""
import os
import json

import config as C


def _path():
    return os.environ.get("BATTLE_GAME_SAVE",
                          os.path.join(os.path.expanduser("~"), ".battle_game_save.json"))


def _default():
    return {"unlocked": list(C.STARTING_UNLOCKED), "wins": 0, "best_wave": 0, "best_score": 0}


def load():
    data = _default()
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            disk = json.load(f)
        for k in data:
            if k in disk:
                data[k] = disk[k]
        # 仅保留池内合法兵种，且保证初始解锁项始终在
        valid = [m for m in data["unlocked"] if m in C.MECH_POOL]
        for m in C.STARTING_UNLOCKED:
            if m not in valid:
                valid.append(m)
        data["unlocked"] = valid
    except Exception:
        pass
    return data


def save(data):
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
