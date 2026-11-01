# How it works

A short tour of the mechanism, so you can debug it instead of guessing.

## The problem

When you press the centre button on a Bluetooth headset, the headset does not
send a keyboard key. It sends an **AVRCP** `PASSTHROUGH` frame — the same
protocol that carries play/pause from the headset to the phone or laptop it is
paired with. On Linux, BlueZ receives that frame and hands it to a *media
player*, which plays or pauses. There is no built-in way to say "actually,
mute my microphone".

Three pieces of BlueZ matter:

| File | Role |
| --- | --- |
| `profiles/audio/avrcp.c` | `handle_passthrough()` decodes the frame. For `AVC_PLAY`, `AVC_PAUSE`, `AVC_STOP`, `AVC_FORWARD`, `AVC_BACKWARD` it looks up `target_get_player(session)` and calls `player->cb->play` / `pause` / `stop` / `next` / `previous`. |
| `profiles/audio/media.c` | Implements `org.bluez.Media1.RegisterPlayer`. That is the hook: any process can hand BlueZ a D-Bus object and become the thing the button talks to. |
| `src/mpris-proxy.c` (`mpris-proxy` binary) | The stock client. It registers a dummy player and forwards every callback to whatever MPRIS player is currently running. |

Two consequences drive the whole design:

1. **`RegisterPlayer` is a public seam.** We do not patch BlueZ. We register
   our own player object and BlueZ calls *us*.
2. **There is exactly one player slot per adapter.** `media_register_player()`
   rejects a second registration with `AlreadyExists`. Whichever process
   registers first owns the button for the lifetime of that registration —
   and `mpris-proxy.service` starts at login, long before anything you launch
   by hand. So a naive "just register too" attempt silently loses.

## What this project does

```
        headset                 BlueZ                    headset-button
   ┌───────────────┐      ┌────────────────┐      ┌──────────────────────┐
   │ centre button │─────▶│ avrcp.c        │─────▶│ bridge (our player)  │
   │ AVRCP PASSTHRU│      │ handle_        │      │  on_button(cmd)      │
   └───────────────┘      │ passthrough()  │      └──────────┬───────────┘
                          └────────────────┘                 │
                                                    ┌────────┴────────┐
                                                    ▼                 ▼
                                            mic toggle        forward to the
                                          (pactl / wpctl)     real MPRIS player
```

1. `install.sh` **masks `mpris-proxy.service`** so the slot is free.
2. `headset-button-bridge` connects to the **system bus**, exposes
   `org.mpris.MediaPlayer2.Player` at `/org/headsetbutton/player`, and calls
   `org.bluez.Media1.RegisterPlayer` on the adapter. BlueZ now believes we are
   the media player.
3. BlueZ validates the registration with `parse_player_properties()`, which
   insists on `CanPlay`, `CanPause` and `CanControl` being true. The bridge
   advertises all three, plus a plausible `Metadata` dictionary.
4. When the button is pressed, BlueZ calls `Play`, `Pause`, `PlayPause`,
   `Stop`, `Next` or `Previous` on our object.
5. `Bridge.on_button()` loads the config **fresh on every press** and does what
   it says: toggle the microphone, forward the command to the real player, run
   a shell command, or several of those.

Because the config is re-read per press, changing your mind costs nothing: no
restart, no reconnect, no relogin. The tray icon simply writes the file.

## Staying honest about playback state

The headset displays a play/pause state on some models, and players care about
`PlaybackStatus`. The bridge therefore subscribes to `PropertiesChanged` on
`/org/mpris/MediaPlayer2` for the *real* player and mirrors
`PlaybackStatus` onto its own object. When the action is `media` or `both`,
the command is forwarded to the real player by name, so playback stays in sync
with reality rather than with our shadow object.

## Why there is a session-bus control interface

BlueZ lives on the system bus, so the player object must too. But the system
bus's default policy refuses a *user* process calling a *unique name* it does
not own, which makes `busctl --system call :1.45 …` fail with `AccessDenied`.

Rather than fight the policy, the bridge publishes a tiny extra interface on
the **session** bus:

```
name    org.headsetbutton.Bridge
path    /org/headsetbutton/control
iface   org.headsetbutton.Control1
methods Press(command), Reload(), Status() -> json
```

The CLI's `simulate` and the tray's "Test" item use it. It also gives you a
scriptable trigger:

```bash
busctl --user call org.headsetbutton.Bridge /org/headsetbutton/control \
       org.headsetbutton.Control1 Press s PlayPause
```

## Audio backend

`audio.py` prefers `pactl` and falls back to `wpctl`; both speak to the same
PipeWire/PulseAudio graph. The `mic` setting is resolved as:

* `default` → whatever the system default input is *right now* (so it follows
  your headset when it connects and your desk mic when it does not),
* anything else → case-insensitive substring match against source names
  (`bluez` is the usual choice for the headset itself),
* no match → the system default.

## The sound cue

Muting is invisible, so `sound.py` gives the state change an audible shape:
a **rising** interval for live, a **falling** one for muted. Direction carries
the meaning, so there is nothing to memorise.

The cue is *synthesised*, not borrowed from a sound theme:

* `_render()` writes 16-bit mono PCM at 44.1 kHz — two sine notes with a 6 ms
  fade in/out so there is no click, separated by a 35 ms gap.
* `_wav_file()` caches the result in `$XDG_RUNTIME_DIR/headset-button/`,
  keyed by cue and volume, and writes it atomically. Regeneration is free and
  the cache survives for the session.
* `play()` picks the first available player (`paplay`, `pw-play`, `aplay`,
  `ffplay`), resolves `sound_sink` against `pactl list short sinks`, and
  spawns it without blocking the D-Bus callback.

`sound_mute` / `sound_unmute` swap in your own files; a missing file falls
back to the tone rather than failing silently. The cue plays *after* the mute
call returns, so what you hear always describes the state you are now in.

## Files

| Path | Purpose |
| --- | --- |
| `src/headset_button/bridge.py` | The daemon: player object, control interface, action dispatch. |
| `src/headset_button/tray.py` | Gtk3/AppIndicator top-bar menu. Writes config; no IPC. |
| `src/headset_button/cli.py` | `headset-button` subcommands, including `doctor`. |
| `src/headset_button/audio.py` | `pactl`/`wpctl` shim. |
| `src/headset_button/sound.py` | Synthesises and plays the mute / unmute cue. |
| `src/headset_button/config.py` | Comment-preserving, atomic config edits. |
| `systemd/*.service` | Two user units: bridge (always) and tray (graphical session). |

## Honest limitations

* **The headset must actually speak AVRCP.** Cheap headsets sometimes send HID
  consumer-control codes over the HID profile instead; those never reach BlueZ
  AVRCP and need a completely different fix (an `evdev`/`hwdb` remap). Check
  with `headset-button doctor` plus `journalctl --user -fu headset-button`, and
  see [OTHER-HEADSETS.md](OTHER-HEADSETS.md) for the decision tree. The device
  this was verified on, and its full capability dump, is in
  [REFERENCE-HEADSET.md](REFERENCE-HEADSET.md).
* **Double and triple clicks are not distinguishable.** AVRCP has no notion of
  click count; a double click arrives as two `PlayPause` calls a few hundred
  milliseconds apart. Timing-based detection is possible but fragile.
* **Only one button.** Volume up/down travel as AVRCP volume and are untouched.
* **One adapter, one player.** Anything else registering a player first wins.
* **Multipoint** headsets keep the AVRCP session with whichever device is
  active; the bridge only sees presses routed to this machine.
