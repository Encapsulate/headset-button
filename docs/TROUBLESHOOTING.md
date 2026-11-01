# Troubleshooting

Start here:

```bash
headset-button doctor
journalctl --user -fu headset-button.service
```

`doctor` checks every dependency, unit and setting this project relies on and
prints the exact fix command for anything broken.

---

## The button still plays/pauses music instead of muting

Almost always `mpris-proxy` — it registered first and owns the button slot.

```bash
systemctl --user status mpris-proxy.service          # should be masked
ls -l ~/.config/systemd/user/mpris-proxy.service     # should be -> /dev/null
systemctl --user mask mpris-proxy.service
systemctl --user restart headset-button.service
```

Then check the bridge actually got the slot:

```bash
journalctl --user -u headset-button.service -n 30
```

You want `registered /org/headsetbutton/player with BlueZ`. If you instead see
`AlreadyExists`, something else holds the slot — mask it too, or log out and
back in so the bridge starts first.

## Nothing happens at all when the button is pressed

Work down this list:

1. **Is the bridge running and registered?**
   `systemctl --user status headset-button.service`
2. **Is the headset connected with AVRCP?**
   `bluetoothctl info 4C:FE:2E:8F:8D:8A | grep -i uuid`
   You need `Advanced Audio Distribution`, `A/V Remote Control` and
   `AVRCP Target` in the list. If `A/V Remote Control` is missing, the headset
   is not negotiating AVRCP and no amount of local config will help —
   disconnect, remove the pairing and pair again.
3. **Does a simulated press work?**
   `headset-button simulate` → if the mic toggles, the bridge and audio path are
   fine and the problem is purely the radio link / headset firmware.
4. **Is the headset sending AVRCP at all?**
   ```bash
   sudo dbus-monitor --system "interface='org.bluez.MediaPlayer1'"
   ```
   (or watch `journalctl -fu bluetooth`). Press the button. Silence means the
   headset is emitting HID consumer codes instead — see below.

### My headset sends HID keycodes, not AVRCP

Some headsets (and most USB-C/3.5 mm "smart" headsets) present as keyboards.
They bypass BlueZ entirely, so this tool cannot see them. Confirm with:

```bash
sudo libinput debug-events --show-keycodes      # press the button
```

If you see `KEY_PLAYPAUSE`, remap it in the kernel instead — for example an
`hwdb` entry or a small `evdev` grabber — and leave the bridge running for
headsets that do use AVRCP.

## The tray icon does not appear

```bash
systemctl --user status headset-button-tray.service
journalctl --user -u headset-button-tray.service -n 40
```

* `neither AyatanaAppIndicator3 nor AppIndicator3 is available` →
  `sudo apt install gir1.2-ayatanaappindicator3-0.1` (or
  `gir1.2-appindicator3-0.1`).
* Icon missing but the service is active → the GNOME AppIndicator extension is
  off: `gnome-extensions enable ubuntu-appindicators@ubuntu.com`
  (`gnome-extensions list` to find the exact id on your distro).
* Started before the shell was ready → the tray waits for
  `org.kde.StatusNotifierWatcher` for up to ten seconds, but a very slow login
  can still beat it: `systemctl --user restart headset-button-tray.service`.

## It mutes the wrong microphone

The `mic` setting is `default` out of the box, which means "whatever the system
default input is". If you want it pinned to the headset:

```bash
pactl list short sources                 # find the exact name
headset-button set mic bluez             # substring match
headset-button set mic alsa_input.usb-mic
headset-button mic status
```

Or use the tray's **Microphone source** submenu.

## `Could not toggle microphone (no pactl/wpctl?)`

Neither `pactl` nor `wpctl` is installed or reachable.

```bash
sudo apt install pulseaudio-utils        # pactl
# or
sudo apt install pipewire-bin            # wpctl
```

Under a bare TTY or a `systemd --user` session started before PipeWire, the
tools exist but cannot reach the socket. Confirm with `pactl info`.

## `AccessDenied` when calling the bridge on the system bus

Expected. The system bus refuses user→user calls to a unique name. Use the
session-bus control interface instead:

```bash
busctl --user call org.headsetbutton.Bridge /org/headsetbutton/control \
       org.headsetbutton.Control1 Press s PlayPause
```

## The headset's own mute button and mine disagree

Many headsets have a separate hardware mute that the OS never learns about.
Nothing here can detect it; the LED on the headset is the truth.

## Restoring the stock behaviour

```bash
headset-button set action media          # button goes back to play/pause
systemctl --user unmask mpris-proxy.service   # hand the slot back to BlueZ
systemctl --user restart mpris-proxy.service
~/projects/headset-button/uninstall.sh        # remove everything
```

## Collecting a useful bug report

```bash
{
  headset-button doctor
  headset-button status
  systemctl --user status headset-button.service headset-button-tray.service
  journalctl --user -u headset-button.service -u headset-button-tray.service -n 100
  bluetoothctl info <MAC>
  python3 -VV
} > report.txt
```
