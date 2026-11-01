"""``headset-button`` command line front end."""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

from . import (ACTION_LABELS, ALL_ACTIONS, BRIDGE_UNIT, CONTROL_IFACE,
               CONTROL_NAME, CONTROL_PATH, MPRIS_PROXY_UNIT, TRAY_UNIT,
               __version__)
from . import audio, config, sound

OK = "\033[32m✔\033[0m"
BAD = "\033[31m✘\033[0m"
WARN = "\033[33m•\033[0m"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True)


def _unit_state(unit: str) -> str:
    out = _systemctl("is-active", unit)
    return out.stdout.strip() or "unknown"


def _press(command: str) -> None:
    import dbus
    bus = dbus.SessionBus()
    dbus.Interface(bus.get_object(CONTROL_NAME, CONTROL_PATH),
                   CONTROL_IFACE).Press(command)


def _fail(message: str) -> int:
    print("headset-button: %s" % message, file=sys.stderr)
    return 1


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(_args) -> int:
    cfg = config.load()
    muted = audio.is_muted(str(cfg.get("mic", "default")))
    print("version       %s" % __version__)
    print("config        %s" % config.config_path())
    print("action        %s   (%s)"
          % (cfg.get("action"), ACTION_LABELS.get(str(cfg.get("action")), "-")))
    print("microphone    %s" % cfg.get("mic"))
    print("mic state     %s"
          % ("muted" if muted else "live" if muted is False else "unknown"))
    print("audio backend %s" % (audio.backend() or "none found"))
    print("sound cue     %s%s"
          % ("on" if cfg.get("sound", True) else "off",
             "" if sound.player() else "  (no player found!)"))
    print("bridge unit   %s" % _unit_state(BRIDGE_UNIT))
    print("tray unit     %s" % _unit_state(TRAY_UNIT))
    print("mpris-proxy   %s"
          % ("masked" if os.path.islink(
              os.path.expanduser("~/.config/systemd/user/%s" % MPRIS_PROXY_UNIT))
              else "enabled (may steal the button!)"))

    for issue in config.problems(cfg):
        print("problem       %s" % issue)
    return 0


def cmd_get(args) -> int:
    cfg = config.load()
    if args.key not in cfg:
        return _fail("unknown key %r (have: %s)"
                     % (args.key, ", ".join(sorted(cfg))))
    print(cfg[args.key])
    return 0


def cmd_set(args) -> int:
    key, value = args.key, args.value
    if key not in config.DEFAULTS:
        return _fail("unknown key %r (have: %s)"
                     % (key, ", ".join(sorted(config.DEFAULTS))))
    if key == "action" and value not in ALL_ACTIONS:
        return _fail("action must be one of: %s" % ", ".join(ALL_ACTIONS))
    if key == "notify":
        value = value.strip().lower() in ("1", "true", "yes", "on")
    config.save_key(key, value)
    print("%s = %s" % (key, value))
    return 0


def cmd_actions(_args) -> int:
    from . import TRAY_ACTIONS
    print("Offered in the tray menu:")
    for action in TRAY_ACTIONS:
        print("  %-12s %s" % (action, ACTION_LABELS.get(action, "")))
    print("\nAlso accepted (set with 'headset-button set action NAME'):")
    for action in sorted(ALL_ACTIONS):
        if action in TRAY_ACTIONS:
            continue
        print("  %-12s %s" % (action, ACTION_LABELS.get(action, "")))
    return 0


def cmd_mic(args) -> int:
    target = config.load().get("mic", "default")
    if args.what == "status":
        muted = audio.is_muted(str(target))
        print("unknown" if muted is None else ("muted" if muted else "live"))
        return 0 if muted is not None else 1
    if args.what == "toggle":
        result = audio.toggle(str(target))
    else:
        result = audio.set_muted(str(target), args.what == "mute")
    if result is None:
        return _fail("no working audio backend (need pactl or wpctl)")
    print("muted" if result else "live")
    return 0


def cmd_sound(args) -> int:
    cfg = config.load()
    volume = float(cfg.get("sound_volume", 0.5) or 0.5)
    sink = str(cfg.get("sound_sink", "default"))

    def fire(muted: bool) -> bool:
        return sound.play(muted, volume=volume, sink=sink,
                          custom=str(cfg.get("sound_mute" if muted
                                             else "sound_unmute", "")))

    if args.what == "mute":
        ok = fire(True)
    elif args.what == "unmute":
        ok = fire(False)
    else:
        ok = fire(False)
        if ok:
            time.sleep(0.7)
            ok = fire(True)
    if not ok:
        return _fail("no audio player found (need paplay, pw-play, aplay "
                     "or ffplay)")
    print("played %s cue" % args.what)
    return 0


def cmd_simulate(args) -> int:
    try:
        _press(args.command)
    except Exception as exc:  # noqa: BLE001
        return _fail("could not reach the bridge (%s). Is %s running?"
                     % (exc, BRIDGE_UNIT))
    print("sent %s" % args.command)
    return 0


def cmd_restart(args) -> int:
    units = {"bridge": [BRIDGE_UNIT], "tray": [TRAY_UNIT],
             "all": [BRIDGE_UNIT, TRAY_UNIT]}[args.what]
    for unit in units:
        out = _systemctl("restart", unit)
        if out.returncode != 0:
            return _fail("restart %s failed: %s"
                         % (unit, out.stderr.strip() or out.stdout.strip()))
    print("restarted %s" % ", ".join(units))
    return 0


def cmd_doctor(_args) -> int:
    failures = []

    def check(label: str, ok: bool, hint: str = "", fatal: bool = True):
        print("%s %s%s" % (OK if ok else (BAD if fatal else WARN), label,
                           "" if ok else "  -> %s" % hint if hint else ""))
        if not ok and fatal:
            failures.append(label)

    print("headset-button %s\n" % __version__)

    check("python >= 3.11", sys.version_info >= (3, 11),
          "found %s" % sys.version.split()[0])
    for module in ("dbus", "dbus.service", "gi"):
        try:
            __import__(module)
            check("python module %s" % module, True)
        except ImportError:
            check("python module %s" % module, False,
                  "apt install python3-dbus python3-gi")
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        check("GTK 3 bindings", True)
    except Exception as exc:  # noqa: BLE001
        check("GTK 3 bindings", False, str(exc))
    try:
        import gi
        found = False
        for ns in ("AyatanaAppIndicator3", "AppIndicator3"):
            try:
                gi.require_version(ns, "0.1")
                found = True
            except ValueError:
                continue
        check("AppIndicator bindings", found,
              "apt install gir1.2-ayatanaappindicator3-0.1")
    except Exception:  # noqa: BLE001
        check("AppIndicator bindings", False, "python3-gi missing")

    backend = audio.backend()
    check("audio backend", backend is not None, "need pactl or wpctl")
    check("sound cue player", sound.player() is not None,
          "apt install pulseaudio-utils (paplay)", fatal=False)

    check("bluetooth service active",
          subprocess.run(["systemctl", "is-active", "--quiet", "bluetooth"],
                         capture_output=True).returncode == 0,
          "sudo systemctl enable --now bluetooth")
    check("bluetooth adapter present", bool(glob.glob("/sys/class/bluetooth/hci*")),
          "plug in / enable an adapter")
    check("mpris-proxy masked",
          os.path.islink(os.path.expanduser(
              "~/.config/systemd/user/%s" % MPRIS_PROXY_UNIT)),
          "systemctl --user mask %s" % MPRIS_PROXY_UNIT, fatal=False)

    for unit in (BRIDGE_UNIT, TRAY_UNIT):
        state = _unit_state(unit)
        check("%s active" % unit, state == "active",
              "systemctl --user restart %s" % unit, fatal=False)

    for issue in config.problems(config.load()):
        check("config: %s" % issue, False, config.config_path(), fatal=False)

    print()
    if failures:
        print("%d problem(s) need attention." % len(failures))
        return 1
    print("Everything looks good.")
    return 0


def cmd_config(_args) -> int:
    print(config.config_path())
    return 0


def cmd_version(_args) -> int:
    print(__version__)
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="headset-button",
        description="Repurpose a Bluetooth headset's centre button.")
    parser.add_argument("-V", "--version", action="version",
                        version=__version__)
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("status", help="show current state").set_defaults(
        func=cmd_status)

    p = subs.add_parser("get", help="print one config value")
    p.add_argument("key")
    p.set_defaults(func=cmd_get)

    p = subs.add_parser("set", help="change one config value")
    p.add_argument("key", choices=sorted(config.DEFAULTS))
    p.add_argument("value")
    p.set_defaults(func=cmd_set)

    subs.add_parser("actions", help="list available actions").set_defaults(
        func=cmd_actions)
    subs.add_parser("config", help="print the config file path").set_defaults(
        func=cmd_config)
    subs.add_parser("doctor", help="diagnose the installation").set_defaults(
        func=cmd_doctor)

    p = subs.add_parser("mic", help="control the microphone directly")
    p.add_argument("what", nargs="?", default="status",
                   choices=["toggle", "mute", "unmute", "status"])
    p.set_defaults(func=cmd_mic)

    p = subs.add_parser("sound", help="play the mute / unmute cue")
    p.add_argument("what", nargs="?", default="both",
                   choices=["mute", "unmute", "both"])
    p.set_defaults(func=cmd_sound)

    p = subs.add_parser("simulate", help="pretend the button was pressed")
    p.add_argument("command", nargs="?", default="PlayPause",
                   choices=["PlayPause", "Play", "Pause", "Stop", "Next",
                            "Previous"])
    p.set_defaults(func=cmd_simulate)

    p = subs.add_parser("restart", help="restart the user services")
    p.add_argument("what", nargs="?", default="all",
                   choices=["bridge", "tray", "all"])
    p.set_defaults(func=cmd_restart)

    return parser


def main(argv: list[str] | None = None) -> int:
    if shutil.which("systemctl") is None:
        print("headset-button: warning: systemctl not found", file=sys.stderr)
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
