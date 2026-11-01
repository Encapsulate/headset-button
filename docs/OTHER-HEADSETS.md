# Will it work with your headset?

**Short answer: if your headset's button shows up as AVRCP, yes, and you change
nothing. If it shows up as a keyboard, this project cannot see it and you need
a kernel-side remap instead.**

Most Bluetooth headsets with a centre button do the AVRCP thing — that is the
standard, and it is what this project hooks. But "most" is not "all", and some
very common designs (especially USB-C and 3.5 mm headsets, and a minority of
Bluetooth ones) send ordinary HID keyboard codes instead. Those never reach
BlueZ's AVRCP code, so nothing here can intercept them.

This page tells you which kind you have in about thirty seconds, and what to do
about each.

The device this project was developed and verified against is documented in
[REFERENCE-HEADSET.md](REFERENCE-HEADSET.md) — a $20 pair of onn. earbuds.

---

## Step 1: which kind is your headset?

Connect it, then run **one** of these and press the button.

### Test A — is it AVRCP?

```bash
sudo dbus-monitor --system "interface='org.bluez.MediaPlayer1'"
```

Press the button. If you see `member=Play`, `member=Pause` or
`member=PlayPause` scroll past, you are in **Category A**. Stop here — this
project works, and you only need to pick an action.

### Test B — is it a keyboard?

```bash
sudo libinput debug-events --show-keycodes
```

(or `sudo evtest` if you prefer). Press the button. If you see
`KEY_PLAYPAUSE`, `KEY_PLAYCD`, `KEY_MUTE` or similar, you are in **Category
B**.

### Test C — is it even Bluetooth?

```bash
bluetoothctl info <MAC> | grep -iE "icon|class|uuid"
```

* `Icon: audio-headset` + a UUID containing `A/V Remote Control` → Category A.
* `Icon: input-keyboard` / `input-mouse` → Category B.
* The device does not appear in `bluetoothctl` at all, and came with a little
  USB-A dongle → **Category C**.

---

## Category A — AVRCP headset (this project applies)

Signs: the headset advertises `A/V Remote Control Target` (`0x110c`), and Test
A shows BlueZ method calls.

**Nothing to change.** Install, then choose what the button does:

```bash
./install.sh
headset-button set action mic-toggle     # or media / both / command
```

Adjust these two to your hardware:

* `mic` — which source to mute. `default` follows the system default input;
  `bluez` substring-matches the headset's own mic (which usually requires the
  HFP/HSP profile to be active, since A2DP is playback-only).
* `sound_sink` — where the mute/unmute cue plays. `default` follows the system
  output, which is normally the headset itself.

Things that vary between AVRCP headsets and need no code change:

| Variation | Effect | Handling |
| --- | --- | --- |
| Headset sends `PLAYPAUSE` for every press | normal | `action = "mic-toggle"` ignores it entirely |
| Headset sends separate `PLAY` then `PAUSE` (it toggles internally) | normal | same — the bridge does not care which frame arrived |
| Headset sends `STOP`, `NEXT`, `PREVIOUS` from other buttons | untouched | those still forward to your player |
| Volume buttons | AVRCP volume / absolute volume | never touched by this project |
| Headset only offers HFP, no A2DP | playback is narrowband | unrelated to the button |

### If the button does nothing even though it is AVRCP

Almost always the player slot, not the headset:

```bash
systemctl --user status mpris-proxy.service    # must be masked
headset-button doctor
journalctl --user -fu headset-button.service
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Category B — HID headset (this project cannot see it)

Signs: Test B prints `KEY_PLAYPAUSE`; `bluetoothctl info` shows
`Icon: input-keyboard`; there is no `A/V Remote Control` UUID. The button is a
keyboard key travelling over the HID profile, and BlueZ's AVRCP code is never
involved.

You have three options. All of them are kernel/input-layer, and all of them
leave this project's tray and CLI unused (though you can still keep them
installed for other headsets).

### Option 1 — remap the keycode with hwdb (best, no daemon)

Tell udev that this device's `PLAYPAUSE` should actually be `MICMUTE`. Desktops
already bind `XF86AudioMicMute` to mute the microphone, so you get the desired
behaviour with no extra software.

Find the modalias:

```bash
cat /sys/class/input/event*/device/modalias | grep -i bluetooth
# e.g. input:b0005v05D6p000Ae0100-e0,1,4,14,k...
```

Write a rule using the vendor/product from that string:

```ini
# /etc/udev/hwdb.d/90-headset-mic.hwdb
evdev:input:b0005v05D6p000A*
 KEY_PLAYPAUSE=KEY_MICMUTE
```

Apply:

```bash
sudo systemd-hwdb update
sudo udevadm trigger --subsystem-match=input --action=change
```

Disconnect and reconnect the headset, then test with `libinput debug-events`.
Trade-off: you lose play/pause from that button (it becomes mic mute) and gain
nothing else.

### Option 2 — `input-remapper` (GUI, reversible, per-device)

```bash
sudo apt install input-remapper
```

Map the button to `KEY_MICMUTE` (or to a macro) in the GUI. Heavier than hwdb,
but easier to undo and to scope to one device.

### Option 3 — a small `evdev` grabber (most control)

Read the device, swallow the `KEY_PLAYPAUSE`, and do whatever you like —
including calling this project's bridge over D-Bus:

```python
import evdev
dev = evdev.InputDevice("/dev/input/by-id/usb-...-event-kbd")
dev.grab()                                    # exclusive: no stray play/pause
for event in dev.read_loop():
    if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.KEY_PLAYPAUSE:
        if event.value == 1:                  # key down only
            ...  # toggle the mic yourself, or call the bridge
```

Requires the `evdev` package (`pip install evdev`) and membership of the
`input` group. This is the route to take if you want double-click detection,
which AVRCP cannot give you either.

---

## Category C — 2.4 GHz dongle, not Bluetooth

If the headset came with a USB-A dongle and never appears in `bluetoothctl`,
it is a proprietary wireless link. BlueZ and this project are irrelevant; the
dongle usually enumerates as a USB audio device plus a HID keyboard, so
**Category B's advice applies** — check with `libinput debug-events`, then use
hwdb.

---

## Category D — wired USB-C or 3.5 mm

Same as Category C minus the radio: it is a USB composite device, the button is
a HID keycode. Use `libinput debug-events` to confirm, then hwdb or
`input-remapper`.

A neat trick for these: because the button is a real key, you can bind it in
your desktop's keyboard settings directly, with no root and no udev rules.

---

## Special cases

**The headset has its own hardware mute button.** Usually a switch wired into
the analogue path, invisible to the OS. It keeps working independently; this
project only touches the centre button.

**Multipoint (paired to phone *and* laptop).** The headset keeps the AVRCP
session with whichever device is "active". If presses go to the phone, no
amount of laptop-side config will help — unpair or disconnect the phone.

**Phone-first headsets.** A few cheap models only honour AVRCP from a phone.
If `dbus-monitor` shows nothing while the headset is definitely connected and
playing, that is the cause.

**Headsets that send both AVRCP and HID.** Rare but real. Pick one path; if
you remap the HID key you may end up toggling the mic twice per press. Remove
the hwdb rule if you see doubling.

**Headset with a companion app.** Irrelevant on Linux. Nothing here needs one.

---

## Reporting a new headset

Adding a device to the docs is a five-minute job and helps the next person.
Open an issue with:

```
Headset:        brand + model (and retail link if there is one)
Firmware:       if known
Distro/kernel:  e.g. Ubuntu 26.04, 7.0.0-38
Bluez version:  bluetoothd --version
Icon/class:     bluetoothctl info <MAC> | grep -iE "icon|class"
UUIDs:          bluetoothctl info <MAC> | grep UUID
Button path:    AVRCP (dbus-monitor) or HID (libinput debug-events)
Profiles:       pactl list cards | grep -A20 bluez_card
Result:         worked / worked after X / did not work, because Y
```

Please redact your own MAC addresses if you care; they are not secret, just
identifying.

## Summary table

| Your headset | Where the button goes | This project | Extra work |
| --- | --- | --- | --- |
| AVRCP headset (`0x110c` UUID) | BlueZ AVRCP | **works** | none — pick an action |
| HID headset (`KEY_PLAYPAUSE`) | kernel input | not used | hwdb / input-remapper / evdev |
| 2.4 GHz dongle | kernel input | not used | same as HID |
| Wired USB-C / 3.5 mm | kernel input | not used | desktop shortcut is easiest |
| Headset with hardware mute | analogue switch | not used | nothing |
