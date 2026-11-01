"""Tests for the mute / unmute cue."""

import os
import tempfile
import unittest
import wave
from unittest import mock

from headset_button import sound


class TestCues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_cues_are_distinct_and_ordered(self):
        mute = [f for f, _ in sound.CUES[True]]
        unmute = [f for f, _ in sound.CUES[False]]
        self.assertNotEqual(mute, unmute)
        self.assertGreater(mute[0], mute[-1], "mute cue should fall")
        self.assertLess(unmute[0], unmute[-1], "unmute cue should rise")

    def test_rendered_wav_is_valid(self):
        path = sound._wav_file(True, 0.5)
        with wave.open(path, "rb") as fh:
            self.assertEqual(fh.getnchannels(), 1)
            self.assertEqual(fh.getsampwidth(), 2)
            self.assertEqual(fh.getframerate(), sound.RATE)
            self.assertGreater(fh.getnframes(), sound.RATE // 10)

    def test_cache_is_reused(self):
        first = sound._wav_file(False, 0.5)
        stamp = os.path.getmtime(first)
        self.assertEqual(sound._wav_file(False, 0.5), first)
        self.assertEqual(os.path.getmtime(first), stamp)

    def test_volume_changes_the_file(self):
        self.assertNotEqual(sound._wav_file(True, 0.2),
                            sound._wav_file(True, 0.9))

    def test_no_temp_files_left_behind(self):
        sound._wav_file(True, 0.5)
        leftovers = [n for n in os.listdir(self.tmp.name) if ".tmp" in n]
        self.assertEqual(leftovers, [])


class TestSinkResolution(unittest.TestCase):
    SINKS = "56\talsa_output.pci-0000_04_00.6.analog-stereo\n1703\tbluez_output.4C:FE\n"

    def _patch(self):
        fake = mock.Mock(stdout=self.SINKS, returncode=0)
        return mock.patch.object(sound.subprocess, "run", return_value=fake)

    def test_default_means_no_device_flag(self):
        self.assertIsNone(sound.resolve_sink("default"))

    def test_substring_match(self):
        with self._patch():
            self.assertEqual(sound.resolve_sink("bluez"), "bluez_output.4C:FE")

    def test_unknown_falls_back_to_default(self):
        with self._patch():
            self.assertIsNone(sound.resolve_sink("nope"))


class TestPlayback(unittest.TestCase):
    def test_no_player_returns_false(self):
        with mock.patch.object(sound.shutil, "which", lambda _n: None):
            self.assertIs(sound.play(True), False)

    def test_paplay_gets_a_device_flag(self):
        with mock.patch.object(sound.shutil, "which",
                               lambda n: "/usr/bin/paplay" if n == "paplay" else None), \
             mock.patch.object(sound, "resolve_sink", lambda _s: "bluez_out"), \
             mock.patch.object(sound, "_wav_file", lambda *_a: "/tmp/x.wav"), \
             mock.patch.object(sound.subprocess, "Popen") as popen:
            self.assertIs(sound.play(True, sink="bluez"), True)
        argv = popen.call_args[0][0]
        self.assertEqual(argv[0], "/usr/bin/paplay")
        self.assertIn("--device=bluez_out", argv)
        self.assertEqual(argv[-1], "/tmp/x.wav")

    def test_custom_file_overrides_the_tone(self):
        with tempfile.NamedTemporaryFile(suffix=".oga") as custom, \
             mock.patch.object(sound.shutil, "which",
                               lambda n: "/usr/bin/paplay" if n == "paplay" else None), \
             mock.patch.object(sound, "resolve_sink", lambda _s: None), \
             mock.patch.object(sound.subprocess, "Popen") as popen:
            sound.play(True, custom=custom.name)
        self.assertEqual(popen.call_args[0][0][-1], custom.name)

    def test_missing_custom_file_falls_back_to_tone(self):
        with mock.patch.object(sound.shutil, "which",
                               lambda n: "/usr/bin/paplay" if n == "paplay" else None), \
             mock.patch.object(sound, "resolve_sink", lambda _s: None), \
             mock.patch.object(sound, "_wav_file", lambda *_a: "/tmp/y.wav"), \
             mock.patch.object(sound.subprocess, "Popen") as popen:
            sound.play(True, custom="/nope/missing.oga")
        self.assertEqual(popen.call_args[0][0][-1], "/tmp/y.wav")


if __name__ == "__main__":
    unittest.main()
