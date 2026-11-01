"""Audible cue for mute / unmute.

A headset user is usually looking at a camera, not the screen, so the state
change needs to be *heard*.  Two short synthesised notes are used rather than
a system sound file: no theme dependency, identical on every distro, and the
direction of the interval carries the meaning on its own.

    unmute / live  ->  rising   (low, high)
    mute           ->  falling  (high, low)

Either cue can be replaced with your own file via ``sound_mute`` /
``sound_unmute`` in the config.
"""

from __future__ import annotations

import array
import math
import os
import shutil
import subprocess
import wave

RATE = 44100
NOTE_GAP = 0.035
FADE = 0.006

#: (frequency Hz, seconds) - order matters, it is the cue.
CUES = {
    True: ((988, 0.085), (659, 0.135)),    # muted  -> falling
    False: ((659, 0.095), (1047, 0.145)),  # live   -> rising
}

#: (binary, device flag template, extra args) - first one found wins.
PLAYERS = (
    ("paplay", "--device={}", ()),
    ("pw-play", "--target={}", ()),
    ("aplay", "-D{}", ("-q",)),
    ("ffplay", None, ("-nodisp", "-autoexit", "-loglevel", "quiet")),
)


def player() -> tuple[str, str | None, tuple[str, ...]] | None:
    """First available player as (binary, device_flag_template, extra_args)."""
    for name, flag, extra in PLAYERS:
        path = shutil.which(name)
        if path:
            return path, flag, extra
    return None


def cache_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = os.path.join(base, "headset-button")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        path = "/tmp"
    return path


# --------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------

def _render(notes, volume: float) -> bytes:
    frames = array.array("h")
    gap = [0] * int(RATE * NOTE_GAP)
    for freq, seconds in notes:
        count = int(RATE * seconds)
        fade = max(1, int(RATE * FADE))
        peak = max(0.0, min(1.0, volume)) * 32000
        for i in range(count):
            envelope = 1.0
            if i < fade:
                envelope = i / fade
            elif i > count - fade:
                envelope = (count - i) / fade
            frames.append(int(peak * envelope *
                              math.sin(2.0 * math.pi * freq * i / RATE)))
        frames.extend(gap)
    return frames.tobytes()


def _wav_file(muted: bool, volume: float) -> str:
    """Path to a cached WAV for this cue; regenerated if the volume changes."""
    tag = "mute" if muted else "unmute"
    path = os.path.join(cache_dir(), "%s-%03d.wav" % (tag, round(volume * 99)))
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return path
    tmp = path + ".%d.tmp" % os.getpid()
    with wave.open(tmp, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(_render(CUES[muted], volume))
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------
# playback
# --------------------------------------------------------------------------

def _sinks() -> list[str]:
    try:
        out = subprocess.run(["pactl", "list", "short", "sinks"],
                             capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in out.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2:
            names.append(fields[1])
    return names


def resolve_sink(target: str) -> str | None:
    """None means "let the player use the default sink"."""
    target = (target or "default").strip()
    if target in ("", "default", "@DEFAULT_SINK@"):
        return None
    lowered = target.lower()
    for name in _sinks():
        if lowered in name.lower():
            return name
    return None


def play(muted: bool, volume: float = 0.5, sink: str = "default",
         custom: str = "") -> bool:
    """Fire the cue without blocking the caller. True if a player was spawned."""
    chosen = player()
    if chosen is None:
        return False
    binary, flag, extra = chosen

    source = os.path.expanduser(custom) if custom else ""
    if source and os.path.isfile(source):
        path = source
    else:
        try:
            path = _wav_file(muted, volume)
        except (OSError, wave.Error):
            return False

    argv = [binary, *extra]
    device = resolve_sink(sink)
    if device and flag:
        argv.append(flag.format(device))
    argv.append(path)

    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
