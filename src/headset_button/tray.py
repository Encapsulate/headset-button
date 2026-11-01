"""Top-bar indicator for picking what the headset button does.

Deliberately dumb: it edits the config file and lets the bridge notice on the
next press.  No IPC, no restart, no chance of the two getting out of sync.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

INDICATOR = None
for namespace in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(namespace, "0.1")
        INDICATOR = __import__("gi.repository", fromlist=[namespace]) \
            .__dict__[namespace]
        break
    except (ValueError, ImportError):
        continue

from . import (ACTION_LABELS, APP_ID, APP_NAME, BRIDGE_UNIT, TRAY_ACTIONS,
               TRAY_UNIT)  # noqa: E402
from . import audio, config  # noqa: E402

SYNC_SECONDS = 3


def _systemctl(*args: str) -> None:
    try:
        subprocess.Popen(["systemctl", "--user", *args],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class Tray:
    def __init__(self):
        if INDICATOR is None:
            raise SystemExit(
                "headset-button-tray: neither AyatanaAppIndicator3 nor "
                "AppIndicator3 is available.\n"
                "Install gir1.2-appindicator3-0.1 (or "
                "gir1.2-ayatanaappindicator3-0.1).")

        self.indicator = INDICATOR.Indicator.new(
            APP_ID + ".tray", "audio-headset",
            INDICATOR.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(INDICATOR.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)

        self.action_items: dict[str, Gtk.RadioMenuItem] = {}
        self.source_items: dict[str, Gtk.RadioMenuItem] = {}
        self.building = False

        self.menu = Gtk.Menu()
        self._build()
        self.indicator.set_menu(self.menu)
        self.menu.show_all()

        self.wait_for_watcher()
        GLib.timeout_add_seconds(SYNC_SECONDS, self.sync)

    # -- construction ----------------------------------------------------
    def _build(self) -> None:
        cfg = config.load()

        heading = Gtk.MenuItem(label="Headset button")
        heading.set_sensitive(False)
        self.menu.append(heading)

        self.menu.append(Gtk.SeparatorMenuItem())

        group: Gtk.RadioMenuItem | None = None
        for action in TRAY_ACTIONS:
            item = Gtk.RadioMenuItem(label=ACTION_LABELS.get(action, action))
            if group is None:
                group = item
            else:
                item.join_group(group)
            item.set_active(cfg.get("action") == action)
            item.connect("toggled", self._on_action, action)
            self.menu.append(item)
            self.action_items[action] = item

        self.menu.append(Gtk.SeparatorMenuItem())

        self.command_item = Gtk.MenuItem(label="Set custom command…")
        self.command_item.connect("activate", self._on_command)
        self.menu.append(self.command_item)

        # -- microphone source submenu -----------------------------------
        source_root = Gtk.MenuItem(label="Microphone source")
        source_menu = Gtk.Menu()
        source_root.set_submenu(source_menu)

        default_item = Gtk.RadioMenuItem(label="System default")
        default_item.set_active(cfg.get("mic", "default") == "default")
        default_item.connect("toggled", self._on_source, "default")
        source_menu.append(default_item)
        self.source_items["default"] = default_item

        current = cfg.get("mic", "default")
        for name in audio.list_sources():
            item = Gtk.RadioMenuItem(label=name)
            item.join_group(default_item)
            item.set_active(current != "default" and current in name)
            item.connect("toggled", self._on_source, name)
            source_menu.append(item)
            self.source_items[name] = item

        self.menu.append(source_root)

        self.notify_item = Gtk.CheckMenuItem(label="Notify on change")
        self.notify_item.set_active(bool(cfg.get("notify", True)))
        self.notify_item.connect("toggled", self._on_notify)
        self.menu.append(self.notify_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        test = Gtk.MenuItem(label="Test: press the button")
        test.connect("activate", lambda *_: self._press("PlayPause"))
        self.menu.append(test)

        restart = Gtk.MenuItem(label="Restart bridge")
        restart.connect("activate", lambda *_: _systemctl("restart", BRIDGE_UNIT))
        self.menu.append(restart)

        open_config = Gtk.MenuItem(label="Edit config file…")
        open_config.connect("activate", self._on_open_config)
        self.menu.append(open_config)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit tray")
        quit_item.connect("activate", lambda *_: _systemctl("stop", TRAY_UNIT))
        self.menu.append(quit_item)

    # -- handlers --------------------------------------------------------
    def _on_action(self, item: Gtk.RadioMenuItem, action: str) -> None:
        if self.building or not item.get_active():
            return
        config.save_key("action", action)
        self._refresh_label()

    def _on_source(self, item: Gtk.RadioMenuItem, name: str) -> None:
        if self.building or not item.get_active():
            return
        config.save_key("mic", name)

    def _on_notify(self, item: Gtk.CheckMenuItem) -> None:
        if self.building:
            return
        config.save_key("notify", "true" if item.get_active() else "false")

    def _on_command(self, *_args) -> None:
        current = config.load().get("command", "")
        dialog = Gtk.Dialog(title="Custom command", flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Save", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_width_chars(48)
        entry.set_text(str(current))
        entry.set_placeholder_text("e.g. playerctl play-pause")
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.add(Gtk.Label(label="Shell command to run when the button is pressed:",
                          xalign=0))
        box.add(entry)
        dialog.show_all()
        response = dialog.run()
        text = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            config.save_key("command", text)
            config.save_key("action", "command")
            self._select("command")

    def _on_open_config(self, *_args) -> None:
        path = str(config.config_path())
        for opener in (["xdg-open", path], ["gedit", path]):
            try:
                subprocess.Popen(opener)
                return
            except OSError:
                continue

    def _press(self, command: str) -> None:
        try:
            import dbus
            from . import CONTROL_IFACE, CONTROL_NAME, CONTROL_PATH
            bus = dbus.SessionBus()
            dbus.Interface(bus.get_object(CONTROL_NAME, CONTROL_PATH),
                           CONTROL_IFACE).Press(command)
        except Exception as exc:  # noqa: BLE001 - tray must never die
            print("headset-button-tray: press failed: %s" % exc, file=sys.stderr)

    # -- state sync ------------------------------------------------------
    def _select(self, action: str) -> None:
        self.building = True
        try:
            item = self.action_items.get(action)
            if item is not None:
                item.set_active(True)
        finally:
            self.building = False
        self._refresh_label()

    def _refresh_label(self) -> None:
        cfg = config.load()
        action = cfg.get("action", "mic-toggle")
        self.indicator.set_icon_full(
            "microphone-sensitivity-muted-symbols" if action in
            ("mic-toggle", "both") else "audio-headset",
            ACTION_LABELS.get(action, action))

    def sync(self) -> bool:
        """Pick up changes made outside the tray (CLI, editor)."""
        cfg = config.load()
        action = cfg.get("action", "mic-toggle")
        active = next((a for a, i in self.action_items.items()
                       if i.get_active()), None)
        if active != action:
            self._select(action)

        mic = cfg.get("mic", "default")
        active_source = next((n for n, i in self.source_items.items()
                              if i.get_active()), None)
        if active_source != mic and mic in self.source_items:
            self.building = True
            try:
                self.source_items[mic].set_active(True)
            finally:
                self.building = False

        notify = bool(cfg.get("notify", True))
        if self.notify_item.get_active() != notify:
            self.building = True
            try:
                self.notify_item.set_active(notify)
            finally:
                self.building = False

        self._refresh_label()
        return True

    def wait_for_watcher(self, attempts: int = 40) -> None:
        """gnome-shell may not own the StatusNotifierWatcher yet at login."""
        try:
            import dbus
        except ImportError:
            return
        try:
            bus = dbus.SessionBus()
        except Exception:  # noqa: BLE001
            return
        for _ in range(attempts):
            try:
                if bus.name_has_owner("org.kde.StatusNotifierWatcher"):
                    return
            except Exception:  # noqa: BLE001
                return
            time.sleep(0.25)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("GDK_BACKEND") is None and not os.environ.get("DISPLAY") \
            and not os.environ.get("WAYLAND_DISPLAY"):
        print("headset-button-tray: no display found", file=sys.stderr)
        return 1
    Tray()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
