# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-11-01

### Added
- **docs/REFERENCE-HEADSET.md** — the exact headset this was built for (onn.
  Wireless Earphones, Walmart 616108422): full SDP UUID dump, device class,
  modalias, codecs and profiles, observed button behaviour, the working
  config, and an explicit list of what was *not* tested.
- **docs/OTHER-HEADSETS.md** — portability guide: a thirty-second test to tell
  whether a headset speaks AVRCP or HID, what to change for AVRCP devices,
  and the kernel-side workarounds (hwdb, `input-remapper`, `evdev`) for HID,
  dongle and wired headsets. Includes a device-report template.
- README sections "Will it work with my headset?" and "Reference hardware".

### Changed
- Documented that the reference earbuds' microphone only exists in the HFP/HSP
  profile, so `mic = "bluez"` implies a codec downgrade.

## [1.1.0] - 2026-11-01

### Added
- **Audible mute / unmute cue.** A short rising two-note tone means the
  microphone went live; a falling one means it is muted — so you can tell which
  way it went without looking at the screen. Synthesised at runtime, so there
  is no sound-theme dependency; `sound_mute` / `sound_unmute` replace either
  cue with your own file.
- `sound`, `sound_volume`, `sound_sink`, `sound_mute`, `sound_unmute` config
  keys. The cue is emitted on the default output (or a substring-matched sink)
  at a configurable volume.
- Tray: **Sound cue on change** toggle and **Preview sound cue**.
- CLI: `headset-button sound [mute|unmute|both]`; `status` reports the cue
  state and `doctor` checks for a usable player.
- Tests for cue generation, caching, sink resolution and playback argv.

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
