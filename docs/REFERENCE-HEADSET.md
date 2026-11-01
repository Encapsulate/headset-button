# Reference headset: onn. Wireless Earphones (Black)

This project was built for one specific, extremely cheap pair of earbuds. This
page records exactly what that device is, what it reports, how its button
behaves, and what had to be true for any of this to work — so that when
something breaks you can compare against a known-good baseline instead of
guessing, and so that anyone with a different headset knows what to look for.

Everything below was read off the live device, not copied from a spec sheet.

## The device

| | |
| --- | --- |
| Retail listing | [Walmart item 616108422](https://www.walmart.com/ip/New-onn-Wireless-Earphones-7-Hours-Playtime-Black-New/616108422) — "New onn. Wireless Earphones, 7 Hours Playtime, Black" |
| Brand | onn. (Walmart's house brand) |
| Form factor | True-wireless in-ear earbuds, charging case |
| Advertised | ~7–8 h playtime (the listing title and body disagree), 2 h full charge, ~33 ft / 10 m range, IPX4 splash resistant, USB-C |
| In the box | earbuds, USB-C cable, two sizes of silicone tips, quick start guide |
| Bluetooth name | `onn In-Ear` |
| Bluetooth address | `4C:FE:2E:8F:8D:8A` (public) |
| Device class | `0x00240404` — Audio/Video, *Wearable Headset Device* |
| Modalias | `bluetooth:v05D6p000Ad0240` |
| Paired as | bonded, trusted, `LegacyPairing: no` |

Cheap, generic, and sold in enormous quantities — which is exactly why it is a
useful reference. If it works here, most AVRCP headsets will.

## What it advertises over SDP

Read with `bluetoothctl info 4C:FE:2E:8F:8D:8A`:

| UUID | Service | Relevance |
| --- | --- | --- |
| `0x110b` | Audio Sink | A2DP playback into the earbuds |
| `0x110c` | **A/V Remote Control Target** | **The one that matters** — the earbuds accept AVRCP commands |
| `0x110d` | Advanced Audio Distribution | A2DP |
| `0x110e` | **A/V Remote Control** | The earbuds also act as an AVRCP controller |
| `0x111e` | Handsfree | HFP, for the microphone |
| `0x1101` | Serial Port | SPP, unused here |
| `0x1200` | PnP Information | vendor/model identity |

The presence of **`0x110c` (AVRCP Target)** is the whole ballgame. It means the
button is delivered to the host as an AVRCP `PASSTHROUGH` frame, which lands in
BlueZ's `handle_passthrough()` — and that is the function this project
intercepts. Without `0x110c` there is nothing to intercept; see
[OTHER-HEADSETS.md](OTHER-HEADSETS.md).

`0x110e` is why the earbuds can also control a phone when paired to one: the
same physical button speaks AVRCP in both directions depending on who is the
target.

## Button behaviour, as observed

* A single press of either earbud's outer face sends AVRCP **PLAYPAUSE**.
* With stock BlueZ (`mpris-proxy` owning the player slot) that reaches the
  active MPRIS player as `Play` / `Pause`, alternating.
* With this project installed, the same frame reaches the bridge and runs the
  configured action — microphone mute/unmute by default.
* Presses arrive identically from the left and right earbud; there is no
  distinction in the AVRCP frame.
* Playback is **not** interrupted by a press while `action = "mic-toggle"`;
  the bridge simply never forwards it.
* No double- or triple-click distinction — a double tap arrives as two
  `PLAYPAUSE` frames roughly 200–400 ms apart.

## Audio profiles and codecs

The card offers, and PipeWire reports as available:

```
a2dp-sink          A2DP Sink, codec SBC        (sinks: 1, sources: 0)
a2dp-sink-sbc_xq   A2DP Sink, codec SBC-XQ     (sinks: 1, sources: 0)
headset-head-unit  HSP/HFP,   codec mSBC       (sinks: 1, sources: 1)
headset-head-unit-cvsd  HSP/HFP, codec CVSD    (sinks: 1, sources: 1)
```

**Important consequence:** the earbuds' microphone only exists in the
`headset-head-unit` (HFP/HSP) profiles. Under `a2dp-sink` there is no capture
source at all — A2DP is playback-only, and switching to HFP drops playback to
narrowband. That is a property of Bluetooth, not of this project.

So the honest picture for using the *headset's own* microphone:

```bash
# switch the card to HFP so bluez_input exists
pactl set-card-profile bluez_card.4C_FE_2E_8F_8D_8A headset-head-unit
headset-button set mic bluez     # target bluez_input.4C:FE:2E:8F:8D:8A
headset-button mic status
```

The default `mic = "default"` follows the *system default input*, which on a
laptop is usually the built-in analogue mic — the sensible choice for calls
where you want full-quality playback and are happy to talk into the laptop.
Pin `mic = "bluez"` if you specifically want the earbuds' mic, and accept the
codec downgrade.

## Other observations

* **Battery** is reported over GATT (`Battery Percentage: 0x5a (90)`), so
  desktops with a battery widget will show the earbud charge.
* The earbuds appear as `bluez_output.4C:FE:2E:8F:8D:8A` (sink) and
  `bluez_input.4C:FE:2E:8F:8D:8A` (source, HFP only).
* The host adapter used was an onboard Intel/USB controller
  (`hci0`, `C0:35:32:9C:A5:DA`) under BlueZ 5.85, kernel 7.0.0, Ubuntu 26.04.
* Pairing was ordinary: no PIN dance, no vendor app, no firmware update.

## Not verified

Honest gaps, so nobody assumes more than was tested:

* **Multipoint** (simultaneous phone + laptop) was never exercised. If the
  earbuds keep the AVRCP session with the phone, presses may not reach the
  laptop at all — that is a device behaviour, not a bug here.
* Whether the button sends anything different on a long press. AVRCP has no
  long-press concept, so it is almost certainly just another `PLAYPAUSE`.
* Whether the charging case affects any of this (it does not, electrically —
  it is a battery with a lid).
* Other colourways of the same listing. They share a chassis and firmware
  family, so they will behave the same, but that is an assumption.

## Raw captures

Unedited command outputs from the development machine, for diffing against your
own setup: [`docs/reference-device/`](reference-device/) — `bluetoothctl info`,
card/codec topology, and the verified environment (Ubuntu 26.04, kernel
7.0.0-38, BlueZ 5.85, PipeWire 1.6.2, GNOME 50.1 on Wayland, onboard `hci0`).

## Reproducing this characterisation```bash
# identify
bluetoothctl info <MAC>                       # UUIDs, class, modalias, battery

# confirm the button path is AVRCP and not HID
sudo dbus-monitor --system "interface='org.bluez.MediaPlayer1'"
#   press the button -> method calls appear => AVRCP, this project applies

# confirm the opposite (HID headset) would look like this instead
sudo libinput debug-events --show-keycodes
#   press the button -> KEY_PLAYPAUSE => HID, this project cannot see it

# profiles and codecs
pactl list cards | grep -A30 bluez_card
```

## Working configuration for this device

```toml
action = "mic-toggle"
mic = "default"          # or "bluez" to use the earbuds' own mic (HFP)
sound = true
sound_volume = 0.5
sound_sink = "default"   # the earbuds are the default sink
notify = true
```

Verified working: pressing the earbud's face toggles the microphone, plays the
falling/rising cue, leaves playback untouched, and logs

```
headset-button: microphone alsa_input.pci-0000_04_00.6.analog-stereo -> MUTED
headset-button: sound cue: falling (muted)
```
