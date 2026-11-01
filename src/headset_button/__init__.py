"""headset-button - repurpose a Bluetooth headset's centre button.

The headset's multifunction button normally only ever sends AVRCP
PLAY/PAUSE, which BlueZ hands to ``mpris-proxy`` and thence to whatever
media player is running.  This package registers its own AVRCP target
player so the button can do anything you like instead - mute the
microphone, control playback, both, or run a command.

See ``docs/HOW-IT-WORKS.md`` for the full mechanism.
"""

__version__ = "1.1.0"
__all__ = ["__version__"]

APP_NAME = "headset-button"
APP_ID = "org.headsetbutton.Bridge"

#: systemd user units
BRIDGE_UNIT = "headset-button.service"
TRAY_UNIT = "headset-button-tray.service"

#: BlueZ's stock AVRCP->MPRIS forwarder.  Masked while we run, because it
#: would otherwise claim the button first.
MPRIS_PROXY_UNIT = "mpris-proxy.service"

#: D-Bus surface used by the CLI and the tray to poke the running bridge.
CONTROL_NAME = APP_ID
CONTROL_PATH = "/org/headsetbutton/control"
CONTROL_IFACE = "org.headsetbutton.Control1"

#: Our org.bluez.MediaPlayer1 object on the system bus.
PLAYER_PATH = "/org/headsetbutton/player"

#: BlueZ / MPRIS constants
BLUEZ_BUS = "org.bluez"
MEDIA_IFACE = "org.bluez.Media1"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
MPRIS_IFACE = "org.mpris.MediaPlayer2.Player"
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"

#: Actions accepted in ``action = ...``
MIC_ACTIONS = frozenset({"mic-toggle", "mic", "mictoggle"})
FORWARD_ACTIONS = {
    "media": "PlayPause",
    "playpause": "PlayPause",
    "play": "Play",
    "pause": "Pause",
    "stop": "Stop",
    "next": "Next",
    "previous": "Previous",
}
ALL_ACTIONS = tuple(sorted(MIC_ACTIONS | set(FORWARD_ACTIONS) | {"both", "command"}))

#: The four choices offered by the tray icon, in menu order.
TRAY_ACTIONS = ("mic-toggle", "media", "both", "command")

ACTION_LABELS = {
    "mic-toggle": "Microphone mute / unmute",
    "mic": "Microphone mute / unmute (alias)",
    "mictoggle": "Microphone mute / unmute (alias)",
    "media": "Default (play / pause)",
    "playpause": "Play / pause only",
    "play": "Play only",
    "pause": "Pause only",
    "stop": "Stop",
    "next": "Next track",
    "previous": "Previous track",
    "both": "Both (mic + play/pause)",
    "command": "Custom command",
}

DEFAULTS = {
    "action": "mic-toggle",
    "mic": "default",
    "command": "",
    "notify": True,
    "sound": True,
    "sound_volume": 0.5,
    "sound_sink": "default",
    "sound_mute": "",
    "sound_unmute": "",
}
