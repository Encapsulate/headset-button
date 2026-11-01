"""Tests for the audio backend shim (no real sound server involved)."""

import unittest
from unittest import mock

from headset_button import audio


class FakeCompleted:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


SOURCES = "1\talsa_input.usb-mic\n2\tbluez_input.4C:FE:2E:8F:8D:8A\n"
WPCTL_STATUS = """\
Audio
 ├─ Devices:
 │      40. Built-in Audio Analog Stereo        [vol: 1.00]
 ├─ Sinks:
 │  *   41. Built-in Audio Analog Stereo        [vol: 0.92]
 ├─ Sources:
 │  *   31. Built-in Audio Analog Stereo        [vol: 1.00]
 │      44. bluez_input.4C:FE:2E:8F:8D:8A       [vol: 1.00]
 ├─ Filters:
 └─ Streams:
"""


def router(table):
    def run(argv, **_kw):
        for key, value in table.items():
            if argv[:len(key)] == list(key):
                return value
        return FakeCompleted(returncode=1)
    return run


class TestBackendSelection(unittest.TestCase):
    def test_prefers_pactl(self):
        with mock.patch.object(audio.shutil, "which", lambda n: "/usr/bin/" + n), \
             mock.patch.object(audio, "_run", router({("pactl", "info"): FakeCompleted()})):
            self.assertEqual(audio.backend(), "pactl")

    def test_falls_back_to_wpctl(self):
        with mock.patch.object(audio.shutil, "which",
                               lambda n: "/usr/bin/wpctl" if n == "wpctl" else None), \
             mock.patch.object(audio, "_run", router({("wpctl", "status"): FakeCompleted()})):
            self.assertEqual(audio.backend(), "wpctl")

    def test_none_when_neither_works(self):
        with mock.patch.object(audio.shutil, "which", lambda n: None), \
             mock.patch.object(audio, "_run", router({})):
            self.assertIsNone(audio.backend())


class TestResolve(unittest.TestCase):
    def test_default_means_default_source(self):
        with mock.patch.object(audio, "backend", lambda: "pactl"), \
             mock.patch.object(audio, "_run",
                               router({("pactl", "get-default-source"):
                                       FakeCompleted("alsa_input.usb-mic\n")})):
            self.assertEqual(audio.resolve("default"), "alsa_input.usb-mic")

    def test_substring_match(self):
        with mock.patch.object(audio, "backend", lambda: "pactl"), \
             mock.patch.object(audio, "_run",
                               router({("pactl", "list", "short", "sources"):
                                       FakeCompleted(SOURCES)})):
            self.assertEqual(audio.resolve("bluez"),
                             "bluez_input.4C:FE:2E:8F:8D:8A")

    def test_unknown_falls_back_to_default(self):
        with mock.patch.object(audio, "backend", lambda: "pactl"), \
             mock.patch.object(audio, "_run",
                               router({("pactl", "list", "short", "sources"):
                                       FakeCompleted(SOURCES),
                                       ("pactl", "get-default-source"):
                                       FakeCompleted("alsa_input.usb-mic")})):
            self.assertEqual(audio.resolve("nope"), "alsa_input.usb-mic")


class TestToggle(unittest.TestCase):
    def test_toggle_reports_new_state(self):
        table = {
            ("pactl", "set-source-mute"): FakeCompleted(),
            ("pactl", "get-source-mute"): FakeCompleted("Source #1\n\tMute: yes\n"),
            ("pactl", "get-default-source"): FakeCompleted("alsa_input.usb-mic"),
        }
        with mock.patch.object(audio, "backend", lambda: "pactl"), \
             mock.patch.object(audio, "_run", router(table)):
            self.assertIs(audio.toggle("default"), True)

    def test_toggle_returns_none_on_failure(self):
        table = {("pactl", "set-source-mute"): FakeCompleted(returncode=1)}
        with mock.patch.object(audio, "backend", lambda: "pactl"), \
             mock.patch.object(audio, "_run", router(table)):
            self.assertIsNone(audio.toggle("default"))

    def test_toggle_without_backend(self):
        with mock.patch.object(audio, "backend", lambda: None):
            self.assertIsNone(audio.toggle("default"))


class TestWpctlParsing(unittest.TestCase):
    def test_sources_are_parsed(self):
        with mock.patch.object(audio, "backend", lambda: "wpctl"), \
             mock.patch.object(audio, "_run",
                               router({("wpctl", "status"): FakeCompleted(WPCTL_STATUS)})):
            names = audio.list_sources()
        self.assertIn("bluez_input.4C:FE:2E:8F:8D:8A", names)
        self.assertIn("Built-in Audio Analog Stereo", names)

    def test_node_id_lookup(self):
        with mock.patch.object(audio, "backend", lambda: "wpctl"), \
             mock.patch.object(audio, "_run",
                               router({("wpctl", "status"): FakeCompleted(WPCTL_STATUS)})):
            self.assertEqual(audio._wpctl_id_for("bluez_input.4C:FE:2E:8F:8D:8A"), "44")

    def test_wpctl_mute_state(self):
        with mock.patch.object(audio, "backend", lambda: "wpctl"), \
             mock.patch.object(audio, "_run",
                               router({("wpctl", "status"): FakeCompleted(WPCTL_STATUS),
                                       ("wpctl", "get-volume"):
                                       FakeCompleted("Volume: 1.00 [MUTED]")})):
            self.assertIs(audio.is_muted("bluez"), True)


if __name__ == "__main__":
    unittest.main()
