"""Tests for config parsing and rewriting."""

import os
import tempfile
import unittest

from headset_button import config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.toml")
        os.environ[config.ENV_OVERRIDE] = self.path

    def tearDown(self):
        os.environ.pop(config.ENV_OVERRIDE, None)
        self.tmp.cleanup()

    def test_defaults_when_missing(self):
        cfg = config.load()
        self.assertEqual(cfg["action"], "mic-toggle")
        self.assertTrue(cfg["notify"])

    def test_env_override_is_honoured(self):
        self.assertEqual(config.config_path(), self.path)

    def test_load_ignores_unknown_keys(self):
        with open(self.path, "w") as fh:
            fh.write('action = "media"\nbogus = 1\n')
        cfg = config.load()
        self.assertEqual(cfg["action"], "media")
        self.assertNotIn("bogus", cfg)

    def test_broken_file_falls_back_to_defaults(self):
        with open(self.path, "w") as fh:
            fh.write("this is not toml")
        self.assertEqual(config.load()["action"], "mic-toggle")

    def test_save_key_preserves_comments(self):
        with open(self.path, "w") as fh:
            fh.write("# keep me\naction = \"media\"\n")
        config.save_key("action", "mic-toggle")
        with open(self.path) as fh:
            text = fh.read()
        self.assertIn("# keep me", text)
        self.assertIn('action = "mic-toggle"', text)
        self.assertEqual(text.count("action ="), 1)

    def test_save_key_appends_new_key(self):
        config.save_key("notify", False)
        self.assertEqual(config.load()["notify"], False)

    def test_save_key_is_atomic(self):
        config.save_key("mic", "default")
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_problems_flags_bad_action(self):
        self.assertTrue(config.problems({"action": "nope"}))

    def test_problems_flags_empty_command(self):
        self.assertTrue(config.problems({"action": "command", "command": " "}))

    def test_valid_config_has_no_problems(self):
        self.assertEqual(config.problems(config.load()), [])


if __name__ == "__main__":
    unittest.main()
