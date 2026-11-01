"""Configuration file handling.

The config is deliberately re-read on every button press: that is what makes
"change it whenever you feel like it" work without a restart, whether the
change comes from the tray icon, the CLI, or a text editor.
"""

from __future__ import annotations

import os
import re
import tomllib

from . import ALL_ACTIONS, DEFAULTS

#: Set ``HEADSET_BUTTON_CONFIG`` to relocate the file (handy for tests).
ENV_OVERRIDE = "HEADSET_BUTTON_CONFIG"


def config_path() -> str:
    """Absolute path of the config file, honouring XDG and the env override."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "headset-button", "config.toml")


def load(path: str | None = None) -> dict:
    """Return the merged config. Never raises on a broken file."""
    cfg = dict(DEFAULTS)
    target = path or config_path()
    try:
        with open(target, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return cfg
    except (tomllib.TOMLDecodeError, OSError):
        return cfg
    for key, value in data.items():
        if key in DEFAULTS:
            cfg[key] = value
    return cfg


def problems(cfg: dict) -> list[str]:
    """Human-readable list of things wrong with a config dict."""
    issues = []
    action = str(cfg.get("action", "")).strip().lower()
    if action not in ALL_ACTIONS:
        issues.append("action %r is not one of: %s"
                      % (action, ", ".join(ALL_ACTIONS)))
    if action == "command" and not str(cfg.get("command", "")).strip():
        issues.append("action is 'command' but command is empty")
    if not isinstance(cfg.get("notify", True), bool):
        issues.append("notify must be true or false")
    return issues


def _render(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


def save_key(key: str, value, path: str | None = None) -> None:
    """Rewrite a single ``key = value`` line, preserving comments."""
    target = path or config_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        with open(target) as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    line = "%s = %s" % (key, _render(value))
    pattern = re.compile(r"^%s\s*=.*$" % re.escape(key), re.M)
    if pattern.search(text):
        text = pattern.sub(lambda _m: line, text, count=1)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    tmp = target + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, target)
