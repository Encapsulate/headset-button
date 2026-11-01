# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-01

First release. Extracted from a working one-off setup into a portable tool.

### Added
- `headset-button-bridge` — a BlueZ AVRCP *target* player that receives the
  headset's centre-button presses and runs a configurable action instead of
  unconditionally forwarding play/pause to the media player.
- Actions: `mic-toggle` (default), `media`, `both`, `command`, plus the
  individual `play` / `pause` / `playpause` / `stop` / `next` / `previous`
  forwards.
- `headset-button-tray` — AppIndicator/Gtk3 top-bar icon with a radio menu to
  switch action live, pick which microphone to mute, toggle notifications,
  fire a test press, restart the bridge and open the config file.
- `headset-button` CLI: `status`, `get`, `set`, `actions`, `mic`, `simulate`,
  `restart`, `doctor`, `config`.
- Config hot-reload: the config file is re-read on every button press, so
  changes from the tray, the CLI or an editor apply instantly with no restart.
- Backend-agnostic microphone control (`pactl`, falling back to `wpctl`) with
  source selection by `default`, substring, or full source name.
- Optional desktop notification on mute/unmute.
- `install.sh` / `uninstall.sh` (fully reversible, no root required) and a
  `Makefile`.
- Unit tests for config handling and the audio shim.
- Documentation: architecture notes and a troubleshooting guide.

### Notes
- Installing masks `mpris-proxy.service`, which otherwise claims the button
  first. `uninstall.sh` restores it.
