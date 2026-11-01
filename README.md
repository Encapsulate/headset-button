# headset-button

**Make your Bluetooth headset's centre button do what *you* want — mute the
microphone, control playback, run a command, or all of the above.**

A Bluetooth headset's multifunction button only ever sends one thing: AVRCP
play/pause. On Linux that lands in `mpris-proxy` and goes straight to your music
player, whether you wanted it to or not. `headset-button` takes over that
button and turns it into a switchable, instantly reconfigurable action — with a
top-bar icon so you can change your mind mid-call.

```
  ┌──────────────────────────────────┐
  │ Headset button                   │
  ├──────────────────────────────────┤
  │ ◉ Microphone mute / unmute       │   ← press the button: mic toggles,
  │ ○ Default (play / pause)         │     music keeps playing
  │ ○ Both (mic + play/pause)        │
  │ ○ Custom command…                │
  ├──────────────────────────────────┤
  │ Microphone source           ▸    │
  │ ☑ Notify on change               │
  ├──────────────────────────────────┤
  │ Test: press the button           │
  │ Restart bridge                   │
  │ Edit config file…                │
  ├──────────────────────────────────┤
  │ Quit tray                        │
  └──────────────────────────────────┘
```

No patching BlueZ. No root. No compiling. One small daemon, one tray icon, and
a config file that is re-read on every single press — so switching between
"mute me" and "pause the music" is one click, effective immediately.

---

## Contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Using it](#using-it)
- [Configuration](#configuration)
- [Actions](#actions)
- [Choosing which microphone](#choosing-which-microphone)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Permissions and safety](#permissions-and-safety)
- [Portability](#portability)
- [Project layout](#project-layout)
- [Development](#development)
- [FAQ](#faq)
- [License](#license)

---

## Why this exists

Headsets with a centre button are everywhere. On Windows and macOS the vendor
app usually lets you remap it. On Linux you get play/pause, forever.

The reason is structural, not accidental. BlueZ exposes exactly one
`org.bluez.Media1.RegisterPlayer` slot per adapter, and `mpris-proxy.service`
claims it at login. Any "just register your own player" script therefore loses
silently — the button keeps hitting `mpris-proxy`, which dutifully forwards
play/pause to your player. `headset-button` frees that slot, takes it, and puts
your choice of action behind the button.

The original motivation was a headset with a useless hardware mute and a
constant need to mute a microphone on calls — while *not* wanting to pause the
music that was playing underneath.

## Features

- **Switchable action, live.** Microphone mute/unmute, classic play/pause,
  both at once, a specific forward (`play`, `pause`, `next`, …), or an
  arbitrary shell command.
- **Top-bar tray icon** with a radio menu. Pick an action; it applies on the
  very next press. No restart, no reconnect, no relogin.
- **Instant reconfiguration from anywhere.** The config file is re-read on
  every press, so the tray, the CLI and your editor are all equally valid ways
  to change behaviour.
- **Correct microphone targeting.** `default` follows your system default
  input; or pin it to the headset by substring (`bluez`) or exact source name.
- **Backend agnostic.** Works with PipeWire or PulseAudio via `pactl`, and
  falls back to `wpctl`.
- **Playback state stays honest.** The bridge mirrors the real player's
  `PlaybackStatus`, so the headset's own indicator is not lied to.
- **Optional notification** on mute/unmute.
- **`headset-button doctor`** — one command that checks every dependency, unit
  and setting and prints the fix for whatever is broken.
- **Fully reversible install.** `uninstall.sh` puts `mpris-proxy` back exactly
  as it was.
- **No root required** for the normal install.

## Requirements

| | |
| --- | --- |
| OS | Linux with systemd (developed and tested on Ubuntu 24.04 → 26.04, GNOME) |
| Session | X11 or Wayland, with a StatusNotifier/AppIndicator host (GNOME needs the App Indicator extension, shipped by Ubuntu by default) |
| Python | 3.11 or newer |
| Packages | `python3-dbus`, `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1` *(or `gir1.2-appindicator3-0.1`)*, and `pulseaudio-utils` or `pipewire-bin` |
| Hardware | A Bluetooth adapter with BlueZ, and a headset that actually speaks AVRCP |

```bash
sudo apt install python3-dbus python3-gi gir1.2-gtk-3.0 \
                 gir1.2-ayatanaappindicator3-0.1 pulseaudio-utils
```

`install.sh` checks all of this for you and tells you exactly what is missing.

## Install

```bash
git clone https://github.com/Encapsulate/headset-button.git
cd headset-button
./install.sh
```

That installs the package under `~/.local/lib/pythonX.Y/site-packages`, three
launchers in `~/.local/bin`, a config file, and two **user** systemd units — then
enables and starts them. It also masks `mpris-proxy.service`, which is the
whole trick.

Options:

```
--prefix DIR     install somewhere other than ~/.local
--no-tray        skip the top-bar indicator
--no-mask        leave mpris-proxy alone (the button may stay on play/pause)
--no-start       install but do not start the services
```

Verify:

```bash
headset-button doctor
headset-button simulate     # pretend the button was pressed
```

Then press the button on your headset. The microphone should mute.

## Using it

### The tray icon

Click the headset icon in the top bar. The menu switches the action instantly,
picks which microphone to mute, toggles notifications, fires a test press,
restarts the bridge, or opens the config file. Changes made elsewhere (CLI or
editor) are picked up by the icon within a few seconds.

### The CLI

```bash
headset-button status                    # what is configured and running
headset-button actions                   # list every action
headset-button set action mic-toggle     # mute/unmute the mic   (default)
headset-button set action media          # back to plain play/pause
headset-button set action both           # mic + play/pause together
headset-button set action next           # skip track instead
headset-button set mic bluez             # pin to the headset's microphone
headset-button set notify false          # silence the popups
headset-button mic toggle                # toggle the mic right now
headset-button mic status                # muted / live
headset-button simulate                  # fake a button press
headset-button restart bridge            # bounce the daemon
headset-button doctor                    # diagnose everything
```

`set action command` plus `set command "playerctl play-pause"` runs any shell
command on each press.

### Scripting the bridge

Anything can trigger a press over the session bus:

```bash
busctl --user call org.headsetbutton.Bridge /org/headsetbutton/control \
       org.headsetbutton.Control1 Press s PlayPause
```

Bind that to a keyboard shortcut, a Stream Deck, or a shell script.

## Configuration

`~/.config/headset-button/config.toml` — created on install, heavily commented:

```toml
# What the headset's centre button does.
action = "mic-toggle"

# Which source to mute. "default" follows the system default input;
# "bluez" substring-matches the headset; or give a full source name.
mic = "default"

# Used when action = "command".
command = ""

# Desktop notification on mute/unmute.
notify = true
```

Edits apply on the next press. Malformed files fall back to defaults rather
than crashing the daemon; `headset-button status` reports problems, and
`doctor` flags them.

## Actions

| `action` | Effect |
| --- | --- |
| `mic-toggle` | Mute / unmute the microphone. **Default.** |
| `media` | Classic behaviour: forward play/pause to the active player. |
| `both` | Toggle the mic *and* forward play/pause. |
| `command` | Run `command` from the config. |
| `play` `pause` `playpause` `stop` `next` `previous` | Forward that one command. |

Aliases `mic` and `mictoggle` are accepted for `mic-toggle`.

## Choosing which microphone

`mic = "default"` (recommended) follows whatever your system default input is,
so it mutes the headset when the headset is connected and your desk mic when it
is not. To pin it:

```bash
pactl list short sources          # find the exact name
headset-button set mic bluez      # case-insensitive substring match
headset-button set mic alsa_input.pci-0000_04_00.6.analog-stereo
```

The tray's **Microphone source** submenu does the same thing by clicking.

## How it works

BlueZ's AVRCP target hands button frames to whichever process owns the
adapter's single player slot. `headset-button` frees that slot by masking
`mpris-proxy`, registers its own `org.mpris.MediaPlayer2.Player` object on the
system bus, and dispatches each press according to the config — optionally
forwarding to the real player so playback controls still work.

Full write-up, including the exact BlueZ code paths, the D-Bus topology, why
there is a second control interface on the session bus, and the honest
limitations: **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)**.

## Troubleshooting

**[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** covers the common cases:
the button still pausing music, nothing happening at all, a missing tray icon,
muting the wrong device, and headsets that send HID keycodes instead of AVRCP.

Quick checks:

```bash
headset-button doctor
journalctl --user -fu headset-button.service
```

## Uninstall

```bash
./uninstall.sh            # stops services, removes files, unmasks mpris-proxy
./uninstall.sh --purge    # also deletes your config
```

Your headset button goes back to plain play/pause, exactly as before.

## Permissions and safety

- Everything runs as **your user**. The only privileged moment is installing
  distro packages, and even that is optional.
- The bridge registers a player on the **system bus**, which any user may do.
  It exposes only the standard MPRIS player interface plus one small control
  interface.
- The only file modified outside its own directories is the symlink that masks
  `mpris-proxy.service`; `uninstall.sh` removes it.
- `action = "command"` runs the string through shell-style splitting. It is
  your own config, so it is trusted by definition.
- Nothing phones home.

## Portability

Written to be distro-agnostic:

- No GNOME-specific APIs — plain Gtk3 + AppIndicator (Ayatana or classic).
- No hardcoded paths; XDG base directories are honoured, and
  `HEADSET_BUTTON_CONFIG` relocates the config for tests.
- Audio goes through `pactl`/`wpctl`, so PipeWire and PulseAudio both work.
- The tray degrades gracefully: `--no-tray` gives you a pure CLI install on a
  headless or minimal desktop.
- `install.sh --prefix` supports non-standard layouts.

Known-good: Ubuntu 24.04 and 26.04, GNOME, X11 and Wayland.

## Project layout

```
bin/                    launchers (also usable straight from a checkout)
config/config.toml      commented sample config
docs/                   architecture and troubleshooting
src/headset_button/     the package
  bridge.py             AVRCP target player + action dispatch
  tray.py               top-bar indicator
  cli.py                command line
  audio.py              pactl/wpctl shim
  config.py             atomic, comment-preserving config edits
systemd/                user units
tests/                  unit tests
install.sh uninstall.sh Makefile
```

## Development

```bash
make test        # unit tests
make lint        # byte-compile + bash -n
make install     # install for the current user
make dist        # source tarball
```

The package is importable straight from `src/`, and `bin/` launchers add it to
`sys.path` themselves, so you can run a checkout without installing:

```bash
./bin/headset-button status
```

## FAQ

**Will this break my media keys?**
No. Only the headset's AVRCP button is redirected, and `action = "media"`
restores the original behaviour exactly. Keyboard media keys are untouched.

**Does it need root?**
No.

**Does it work with Spotify / Firefox / mpv / VLC?**
Any MPRIS-compatible player, yes — that is the standard it forwards to.

**My headset has a separate mute button.**
Usually a hardware mute the OS never sees. This tool handles the *centre*
button; the hardware mute keeps working independently.

**Can I use double-clicks?**
Not reliably. AVRCP has no click counter — a double click is just two
`PlayPause` calls. `action = "command"` plus your own timing logic is the
escape hatch.

**What if the headset sends HID keycodes instead of AVRCP?**
Then BlueZ never sees the press and this tool cannot help; see the
troubleshooting guide for the `libinput debug-events` check and the kernel-side
alternative.

## License

[MIT](LICENSE) © 2026 Encapsulate
