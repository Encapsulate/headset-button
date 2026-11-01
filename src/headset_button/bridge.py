"""The daemon: an AVRCP target player that runs your chosen action.

BlueZ's AVRCP target routes each incoming passthrough op to whichever client
owns an ``org.bluez.MediaPlayer1`` player registered with the adapter.  Stock
BlueZ ships ``mpris-proxy`` in that role; we take it over so the button can do
something other than play/pause.

The object we register lives on the *system* bus (that is where BlueZ is), but
the methods BlueZ calls are the plain MPRIS names, so BlueZ needs no special
casing for us.
"""

from __future__ import annotations

import json
import shlex
import signal
import subprocess
import sys

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

from . import (APP_ID, BLUEZ_BUS, CONTROL_IFACE, CONTROL_NAME, CONTROL_PATH,
               FORWARD_ACTIONS, MEDIA_IFACE, MIC_ACTIONS, MPRIS_IFACE,
               MPRIS_PATH, MPRIS_PREFIX, OM_IFACE, PLAYER_PATH, PROPS_IFACE)
from . import audio, config, sound


def log(message: str) -> None:
    print("headset-button: %s" % message, flush=True)


def _notify(title: str, body: str) -> None:
    try:
        subprocess.Popen(["notify-send", "-a", "Headset button", "-i",
                          "microphone-sensitivity-high-symbols", title, body])
    except OSError:
        pass


class Player(dbus.service.Object):
    """Minimal ``org.mpris.MediaPlayer2.Player`` on the system bus."""

    def __init__(self, bus, bridge: "Bridge"):
        super().__init__(bus, PLAYER_PATH)
        self.bridge = bridge
        self.props = dbus.Dictionary({
            "PlaybackStatus": "Stopped",
            "LoopStatus": "None",
            "Rate": 1.0,
            "Shuffle": False,
            "Metadata": dbus.Dictionary(
                {"mpris:trackid": dbus.ObjectPath("/org/headsetbutton/track")},
                signature="sv"),
            "Volume": 1.0,
            "Position": dbus.Int64(0),
            "MinimumRate": 1.0,
            "MaximumRate": 1.0,
            "CanGoNext": True,
            "CanGoPrevious": True,
            "CanPlay": True,
            "CanPause": True,
            "CanSeek": False,
            "CanControl": True,
        }, signature="sv")

    # -- org.freedesktop.DBus.Properties --------------------------------
    @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self.props[prop]

    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.props

    @dbus.service.method(PROPS_IFACE, in_signature="ssv", out_signature="")
    def Set(self, interface, prop, value):
        self.props[prop] = value

    @dbus.service.signal(PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def set_playback_status(self, status: str) -> None:
        if self.props["PlaybackStatus"] == status:
            return
        self.props["PlaybackStatus"] = status
        self.PropertiesChanged(
            MPRIS_IFACE,
            dbus.Dictionary({"PlaybackStatus": status}, signature="sv"), [])

    # -- the methods BlueZ invokes --------------------------------------
    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def Play(self):
        self.bridge.on_button("Play")

    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def Pause(self):
        self.bridge.on_button("Pause")

    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def PlayPause(self):
        self.bridge.on_button("PlayPause")

    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def Stop(self):
        self.bridge.on_button("Stop")

    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def Next(self):
        self.bridge.on_button("Next")

    @dbus.service.method(MPRIS_IFACE, in_signature="", out_signature="")
    def Previous(self):
        self.bridge.on_button("Previous")

    @dbus.service.method(MPRIS_IFACE, in_signature="x", out_signature="")
    def Seek(self, offset):
        pass

    @dbus.service.method(MPRIS_IFACE, in_signature="ox", out_signature="")
    def SetPosition(self, track_id, position):
        pass

    @dbus.service.method(MPRIS_IFACE, in_signature="s", out_signature="")
    def OpenUri(self, uri):
        pass

    @dbus.service.signal(MPRIS_IFACE, signature="x")
    def Seeked(self, position):
        pass


class Control(dbus.service.Object):
    """Session-bus surface used by the CLI and the tray icon."""

    def __init__(self, bus, bridge: "Bridge"):
        super().__init__(bus, CONTROL_PATH)
        self.bridge = bridge

    @dbus.service.method(CONTROL_IFACE, in_signature="s", out_signature="")
    def Press(self, command="PlayPause"):
        self.bridge.on_button(str(command))

    @dbus.service.method(CONTROL_IFACE, in_signature="", out_signature="")
    def Reload(self):
        log("config reload requested")

    @dbus.service.method(CONTROL_IFACE, in_signature="", out_signature="s")
    def Status(self):
        cfg = config.load()
        return json.dumps({
            "version": _version(),
            "action": cfg.get("action"),
            "mic": cfg.get("mic"),
            "mic_muted": audio.is_muted(str(cfg.get("mic", "default"))),
            "backend": audio.backend(),
            "player": self.bridge.real_player(),
            "registered": self.bridge.registered,
        })


def _version() -> str:
    from . import __version__
    return __version__


class Bridge:
    def __init__(self):
        self.system = dbus.SystemBus()
        self.session = dbus.SessionBus()
        self.player = Player(self.system, self)
        self.adapter_path = self._find_adapter()
        self.registered = False
        self._watch_real_player()

    # -- BlueZ plumbing --------------------------------------------------
    def _find_adapter(self) -> str:
        manager = dbus.Interface(self.system.get_object(BLUEZ_BUS, "/"),
                                 OM_IFACE)
        candidates = []
        for path, interfaces in manager.GetManagedObjects().items():
            if MEDIA_IFACE in interfaces:
                candidates.append(path)
        if not candidates:
            raise SystemExit(
                "headset-button: no BlueZ adapter exposing %s found "
                "(is bluetooth.service running?)" % MEDIA_IFACE)
        path = sorted(candidates)[0]
        log("using adapter %s" % path)
        return path

    def register(self) -> None:
        media = dbus.Interface(
            self.system.get_object(BLUEZ_BUS, self.adapter_path), MEDIA_IFACE)
        media.RegisterPlayer(PLAYER_PATH, self.player.props)
        self.registered = True
        log("registered %s with BlueZ" % PLAYER_PATH)

    def unregister(self) -> None:
        if not self.registered:
            return
        try:
            media = dbus.Interface(
                self.system.get_object(BLUEZ_BUS, self.adapter_path),
                MEDIA_IFACE)
            media.UnregisterPlayer(PLAYER_PATH)
        except dbus.DBusException as exc:
            log("unregister failed: %s" % exc)
        self.registered = False

    # -- mirror the real player so the headset sees the truth ------------
    def real_player(self) -> str | None:
        try:
            names = self.session.list_names()
        except dbus.DBusException:
            return None
        for name in names:
            if name.startswith(MPRIS_PREFIX):
                return name
        return None

    def _watch_real_player(self) -> None:
        self.session.add_signal_receiver(
            self._on_real_props, dbus_interface=PROPS_IFACE,
            signal_name="PropertiesChanged", arg0=MPRIS_IFACE,
            path=MPRIS_PATH)
        name = self.real_player()
        if not name:
            return
        try:
            props = dbus.Interface(self.session.get_object(name, MPRIS_PATH),
                                   PROPS_IFACE)
            self.player.set_playback_status(str(props.Get(MPRIS_IFACE,
                                                          "PlaybackStatus")))
        except dbus.DBusException:
            pass

    def _on_real_props(self, _interface, changed, _invalidated, **_kw):
        if "PlaybackStatus" in changed:
            self.player.set_playback_status(str(changed["PlaybackStatus"]))

    def forward(self, command: str) -> None:
        name = self.real_player()
        if name is None:
            log("no MPRIS player to forward %s to" % command)
            return
        try:
            iface = dbus.Interface(self.session.get_object(name, MPRIS_PATH),
                                   MPRIS_IFACE)
            getattr(iface, command)()
        except dbus.DBusException as exc:
            log("forward %s to %s failed: %s" % (command, name, exc))

    # -- the button ------------------------------------------------------
    def on_button(self, command: str) -> None:
        cfg = config.load()
        action = str(cfg.get("action", "mic-toggle")).strip().lower()

        if action in MIC_ACTIONS:
            self._mic(str(cfg.get("mic", "default")), cfg)
        elif action == "command":
            cmd = str(cfg.get("command", "")).strip()
            if cmd:
                try:
                    subprocess.Popen(shlex.split(cmd))
                except (OSError, ValueError) as exc:
                    log("command failed: %s" % exc)
            else:
                log("action=command but no command configured")
        elif action == "both":
            self._mic(str(cfg.get("mic", "default")), cfg)
            self.forward(FORWARD_ACTIONS.get(command, command))
        elif action in FORWARD_ACTIONS:
            self.forward(FORWARD_ACTIONS[action])
        else:
            log("unknown action %r; forwarding %s" % (action, command))
            self.forward(command)

    def _mic(self, target: str, cfg: dict) -> None:
        source = audio.resolve(target)
        muted = audio.toggle(target)
        if muted is None:
            log("could not toggle microphone (no pactl/wpctl?)")
            return
        log("microphone %s -> %s" % (source, "MUTED" if muted else "live"))

        if cfg.get("sound", True):
            custom = str(cfg.get("sound_mute" if muted else "sound_unmute", ""))
            played = sound.play(
                muted,
                volume=float(cfg.get("sound_volume", 0.5) or 0.5),
                sink=str(cfg.get("sound_sink", "default")),
                custom=custom)
            if played:
                log("sound cue: %s" % ("falling (muted)" if muted
                                       else "rising (live)"))
            else:
                log("no audio player found for the sound cue")

        if cfg.get("notify", True):
            _notify("Microphone", "Muted" if muted else "Live")


def main(argv: list[str] | None = None) -> int:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bridge = Bridge()
    bridge.register()

    # Keep references: dbus-python releases the name when these are collected.
    bridge.control_name = dbus.service.BusName(CONTROL_NAME, bus=bridge.session)
    bridge.control = Control(bridge.session, bridge)
    log("control interface on %s" % CONTROL_NAME)

    loop = GLib.MainLoop()

    def shutdown(*_args):
        bridge.unregister()
        loop.quit()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, shutdown)

    log("ready - config: %s" % config.config_path())
    try:
        loop.run()
    finally:
        bridge.unregister()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
