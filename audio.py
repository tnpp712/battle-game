"""程序化音效与音乐：用 pygame.mixer + array 合成 16-bit 单声道样本，无任何外部素材。

设计为「无声也不崩」：mixer 初始化失败（无音频设备/dummy 异常）时整体降级为静音 no-op，
冒烟测试与无音频环境照常运行。游戏侧只调用 audio.play("名") / audio.start_music() 等。
"""
import math
import array
import random

import pygame

SR = 44100
_enabled = False
_muted = False
_sfx = {}
_music = None
_music_chan = None
_last_play = {}        # 各音效上次播放时刻，用于节流
_clock = 0.0


# ---------------- 合成原语 ----------------
def _clamp16(x):
    return max(-32767, min(32767, int(x * 32767)))


def _to_sound(samples):
    buf = array.array("h", (_clamp16(s) for s in samples))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _env(i, n, atk=0.01, rel=0.3):
    """线性 attack / release 包络（i/n 为归一化位置）。"""
    a = max(1, int(n * atk))
    r = max(1, int(n * rel))
    if i < a:
        return i / a
    if i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def _sine(f, t):
    return math.sin(2 * math.pi * f * t)


def _saw(f, t):
    return 2.0 * ((f * t) % 1.0) - 1.0


def _square(f, t):
    return 1.0 if (f * t) % 1.0 < 0.5 else -1.0


# ---------------- 各音效生成 ----------------
def _gen_laser():
    n = int(SR * 0.09)
    out = []
    for i in range(n):
        t = i / SR
        f = 900 - 5200 * t            # 快速下扫
        s = (_square(f, t) * 0.5 + _saw(f, t) * 0.5)
        out.append(s * _env(i, n, 0.005, 0.6) * 0.35)
    return out


def _gen_hit():
    n = int(SR * 0.06)
    return [random.uniform(-1, 1) * _env(i, n, 0.002, 0.7) * 0.3 for i in range(n)]


def _gen_explosion():
    n = int(SR * 0.45)
    out = []
    for i in range(n):
        t = i / SR
        noise = random.uniform(-1, 1)
        rumble = _sine(70 - 30 * t, t)    # 低频下坠
        s = (noise * 0.6 + rumble * 0.4)
        out.append(s * _env(i, n, 0.005, 0.85) * 0.5)
    return out


def _gen_alarm():
    n = int(SR * 0.22)
    out = []
    for i in range(n):
        t = i / SR
        f = 220 if (t * 14) % 1.0 < 0.5 else 165
        out.append(_square(f, t) * _env(i, n, 0.01, 0.4) * 0.28)
    return out


def _gen_cast():
    n = int(SR * 0.28)
    out = []
    for i in range(n):
        t = i / SR
        f = 300 + 900 * (t / 0.28)        # 上扫
        s = _sine(f, t) * 0.6 + _sine(f * 1.5, t) * 0.4
        out.append(s * _env(i, n, 0.02, 0.5) * 0.3)
    return out


def _gen_heal():
    return _gen_chord([523, 659, 784], 0.35, 0.25)


def _gen_build():
    n = int(SR * 0.14)
    out = []
    for i in range(n):
        t = i / SR
        f = 440 if t < 0.07 else 660
        out.append(_square(f, t) * _env(i, n, 0.01, 0.4) * 0.25)
    return out


def _gen_ui():
    n = int(SR * 0.04)
    return [_square(880, i / SR) * _env(i, n, 0.005, 0.6) * 0.2 for i in range(n)]


def _gen_chord(freqs, dur, vol):
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        s = sum(_sine(f, t) for f in freqs) / len(freqs)
        out.append(s * _env(i, n, 0.01, 0.5) * vol)
    return out


def _gen_arp(freqs, dur, vol, wave=_sine):
    """依次弹奏一串音符。"""
    n = int(SR * dur)
    step = n // len(freqs)
    out = []
    for k, f in enumerate(freqs):
        for i in range(step):
            t = i / SR
            out.append(wave(f, t) * _env(i, step, 0.01, 0.5) * vol)
    return out


def _gen_wave():
    return _gen_arp([330, 440, 554, 660], 0.5, 0.3, _saw)


def _gen_win():
    return _gen_arp([523, 659, 784, 1047], 0.7, 0.3)


def _gen_lose():
    return _gen_arp([440, 392, 311, 233], 0.8, 0.32, _square)


def _gen_music():
    """6 秒可循环的环境音：低频脉冲 + 小调琶音垫。"""
    dur = 6.0
    n = int(SR * dur)
    bass_notes = [110, 110, 98, 87]            # A2 A2 G2 F2
    arp = [220, 262, 330, 262, 392, 330, 262, 330]   # A 小调琶音
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        # 低频脉冲（每 1.5s 一拍）
        bn = bass_notes[int(t / 1.5) % len(bass_notes)]
        beat_t = (t % 1.5)
        bass = _sine(bn, t) * math.exp(-beat_t * 1.5) * 0.18
        # 缓慢琶音（每 0.375s 一个音）
        an = arp[int(t / 0.375) % len(arp)]
        ar_t = (t % 0.375)
        arp_s = (_sine(an, t) * 0.5 + _saw(an, t) * 0.5) * math.exp(-ar_t * 4) * 0.06
        # 远景垫音
        pad = _sine(55, t) * 0.05
        out[i] = bass + arp_s + pad
    # 首尾交叉淡化，保证循环无缝
    fade = int(SR * 0.05)
    for i in range(fade):
        g = i / fade
        out[i] *= g
        out[n - 1 - i] *= g
    return out


_GENERATORS = {
    "laser": _gen_laser, "hit": _gen_hit, "explosion": _gen_explosion,
    "alarm": _gen_alarm, "cast": _gen_cast, "heal": _gen_heal,
    "build": _gen_build, "ui": _gen_ui, "wave": _gen_wave,
    "win": _gen_win, "lose": _gen_lose,
}


# ---------------- 对外接口 ----------------
def init():
    """初始化混音器并合成全部音效；失败则保持静音（不抛异常）。"""
    global _enabled, _music
    if _enabled:
        return
    try:
        pygame.mixer.quit()
        pygame.mixer.init(frequency=SR, size=-16, channels=1, buffer=512)
        pygame.mixer.set_num_channels(16)
        for name, gen in _GENERATORS.items():
            _sfx[name] = _to_sound(gen())
        _music = _to_sound(_gen_music())
        _enabled = True
    except Exception:
        _enabled = False


def tick(dt):
    global _clock
    _clock += dt


def play(name, vol=1.0, throttle=0.0):
    """播放音效。throttle>0 时，距上次同名播放不足该秒数则跳过（防刷屏）。"""
    if not _enabled or _muted:
        return
    if throttle > 0 and _clock - _last_play.get(name, -1e9) < throttle:
        return
    snd = _sfx.get(name)
    if snd is None:
        return
    _last_play[name] = _clock
    snd.set_volume(vol)
    snd.play()


def start_music(vol=0.5):
    global _music_chan
    if not _enabled or _music is None:
        return
    try:
        _music.set_volume(vol)
        _music_chan = _music.play(loops=-1)
    except Exception:
        pass


def toggle_mute():
    """静音开关；返回当前是否静音。"""
    global _muted
    _muted = not _muted
    if _enabled:
        if _muted:
            pygame.mixer.pause()
            if _music_chan:
                _music_chan.set_volume(0.0)
        else:
            pygame.mixer.unpause()
            if _music_chan:
                _music_chan.set_volume(0.5)
    return _muted
