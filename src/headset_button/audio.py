"""Microphone mute control.

Speaks to PipeWire/PulseAudio through ``pactl`` when available and falls back
to PipeWire's own ``wpctl``.  Nothing here is GNOME-specific.
"""

from __future__ import annotations

import re
import shutil
import subprocess

TIMEOUT = 8


def _run(argv: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None


def backend() -> str | None:
    """Return ``"pactl"``, ``"wpctl"`` or None."""
    if shutil.which("pactl"):
        probe = _run(["pactl", "info"])
        if probe is not None and probe.returncode == 0:
            return "pactl"
    if shutil.which("wpctl"):
        probe = _run(["wpctl", "status"])
        if probe is not None and probe.returncode == 0:
            return "wpctl"
    return None


# --------------------------------------------------------------------------
# pactl backend
# --------------------------------------------------------------------------

def _pactl_sources() -> list[str]:
    out = _run(["pactl", "list", "short", "sources"])
    if out is None or out.returncode != 0:
        return []
    names = []
    for line in out.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2:
            names.append(fields[1])
    return names


def _pactl_default() -> str | None:
    out = _run(["pactl", "get-default-source"])
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip() or None


# --------------------------------------------------------------------------
# wpctl backend
# --------------------------------------------------------------------------

_TREE = "│├└─ \t"
_SECTION = re.compile(r"^(Devices|Sinks|Sources|Filters|Streams|Video):\s*$")
_WPCTL_ENTRY = re.compile(r"^(?:\*\s*)?(\d+)\.\s+(.*?)\s*\[")


def _wpctl_sources() -> list[tuple[str, str]]:
    """[(node_id, name)] parsed out of ``wpctl status``."""
    out = _run(["wpctl", "status"])
    if out is None or out.returncode != 0:
        return []
    found: list[tuple[str, str]] = []
    in_sources = False
    for raw in out.stdout.splitlines():
        line = raw.lstrip(_TREE)
        section = _SECTION.match(line)
        if section:
            in_sources = section.group(1) == "Sources"
            continue
        if not in_sources:
            continue
        match = _WPCTL_ENTRY.match(line)
        if match:
            found.append((match.group(1), match.group(2)))
    return found


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def list_sources() -> list[str]:
    """Every capturable source name the current backend knows about."""
    if backend() == "pactl":
        return _pactl_sources()
    return [name for _id, name in _wpctl_sources()]


def default_source() -> str | None:
    if backend() == "pactl":
        return _pactl_default()
    return "@DEFAULT_AUDIO_SOURCE@"


def resolve(target: str) -> str:
    """Turn a config value into something the backend understands.

    ``default`` (or empty) means "whatever is currently the default source".
    Anything else is a case-insensitive substring match against source names.
    """
    target = (target or "default").strip()
    if target in ("default", "@DEFAULT_SOURCE@", "@DEFAULT_AUDIO_SOURCE@"):
        return default_source() or "@DEFAULT_SOURCE@"
    lowered = target.lower()
    for name in list_sources():
        if lowered in name.lower():
            return name
    return default_source() or "@DEFAULT_SOURCE@"


def _wpctl_id_for(name: str) -> str | None:
    for node_id, node_name in _wpctl_sources():
        if node_name == name or name.lower() in node_name.lower():
            return node_id
    return None


def toggle(target: str = "default") -> bool | None:
    """Flip mute on the resolved source. Returns the new muted state."""
    kind = backend()
    if kind is None:
        return None
    name = resolve(target)

    if kind == "pactl":
        out = _run(["pactl", "set-source-mute", name, "toggle"])
        if out is None or out.returncode != 0:
            return None
    else:
        node = "@DEFAULT_AUDIO_SOURCE@" if name.startswith("@") \
            else (_wpctl_id_for(name) or "@DEFAULT_AUDIO_SOURCE@")
        out = _run(["wpctl", "set-mute", node, "toggle"])
        if out is None or out.returncode != 0:
            return None

    return is_muted(target)


def set_muted(target: str = "default", muted: bool = True) -> bool | None:
    """Force mute on/off. Returns the resulting muted state."""
    kind = backend()
    if kind is None:
        return None
    name = resolve(target)
    want = "1" if muted else "0"

    if kind == "pactl":
        out = _run(["pactl", "set-source-mute", name, want])
    else:
        node = "@DEFAULT_AUDIO_SOURCE@" if name.startswith("@") \
            else (_wpctl_id_for(name) or "@DEFAULT_AUDIO_SOURCE@")
        out = _run(["wpctl", "set-mute", node, want])

    if out is None or out.returncode != 0:
        return None
    return is_muted(target)


def is_muted(target: str = "default") -> bool | None:
    """True/False, or None when the state cannot be determined."""
    kind = backend()
    if kind is None:
        return None
    name = resolve(target)

    if kind == "pactl":
        out = _run(["pactl", "get-source-mute", name])
        if out is None or out.returncode != 0:
            return None
        return "yes" in out.stdout.lower()

    node = "@DEFAULT_AUDIO_SOURCE@" if name.startswith("@") \
        else (_wpctl_id_for(name) or "@DEFAULT_AUDIO_SOURCE@")
    out = _run(["wpctl", "get-volume", node])
    if out is None or out.returncode != 0:
        return None
    return "muted" in out.stdout.lower()
