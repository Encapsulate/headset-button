#!/usr/bin/env bash
# Install headset-button for the current user.
#
# Everything lands under $PREFIX (default ~/.local) plus the systemd user
# directory, so no root is required.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONFIG_DIR/systemd/user"
APPDIR="$CONFIG_DIR/headset-button"

WITH_TRAY=1
MASK_PROXY=1
START=1

usage() {
    cat <<EOF
Usage: ./install.sh [options]

  --prefix DIR     install under DIR instead of \$HOME/.local
  --no-tray        skip the top-bar indicator
  --no-mask        leave mpris-proxy.service alone (it may steal the button)
  --no-start       install but do not enable/start the services
  -h, --help       this text
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --no-tray) WITH_TRAY=0; shift ;;
        --no-mask) MASK_PROXY=0; shift ;;
        --no-start) START=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------
command -v python3 >/dev/null || die "python3 not found"
command -v systemctl >/dev/null || die "systemctl not found (systemd required)"

PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$PYVER" in
    3.1[1-9]|3.[2-9][0-9]) ;;
    *) die "python 3.11+ required, found $PYVER" ;;
esac

missing=()
python3 -c 'import dbus'            2>/dev/null || missing+=("python3-dbus")
python3 -c 'import gi'              2>/dev/null || missing+=("python3-gi")
python3 -c 'import gi; gi.require_version("Gtk","3.0")' 2>/dev/null \
    || missing+=("gir1.2-gtk-3.0")
if [ "$WITH_TRAY" = 1 ]; then
    python3 - <<'PY' 2>/dev/null || missing+=("gir1.2-appindicator3-0.1 or gir1.2-ayatanaappindicator3-0.1")
import gi
for ns in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(ns, "0.1"); raise SystemExit(0)
    except ValueError:
        pass
raise SystemExit(1)
PY
fi
if ! command -v pactl >/dev/null && ! command -v wpctl >/dev/null; then
    missing+=("pulseaudio-utils or pipewire-bin")
fi

if [ ${#missing[@]} -gt 0 ]; then
    warn "missing dependencies: ${missing[*]}"
    warn "install them with:  sudo apt install ${missing[*]}"
    warn "continuing anyway - run 'headset-button doctor' afterwards"
fi

# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------
SITE="$PREFIX/lib/python$PYVER/site-packages"
BINDIR="$PREFIX/bin"

say "installing python package -> $SITE/headset_button"
install -d "$SITE"
rm -rf "${SITE:?}/headset_button"
cp -r "$REPO_DIR/src/headset_button" "$SITE/headset_button"
find "$SITE/headset_button" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

say "installing launchers -> $BINDIR"
install -d "$BINDIR"
install -m 0755 "$REPO_DIR/bin/headset-button"        "$BINDIR/headset-button"
install -m 0755 "$REPO_DIR/bin/headset-button-bridge" "$BINDIR/headset-button-bridge"
if [ "$WITH_TRAY" = 1 ]; then
    install -m 0755 "$REPO_DIR/bin/headset-button-tray" "$BINDIR/headset-button-tray"
fi

say "installing config -> $APPDIR/config.toml"
install -d "$APPDIR"
if [ -f "$APPDIR/config.toml" ]; then
    echo "    keeping your existing config"
    if ! grep -q '^sound' "$APPDIR/config.toml"; then
        echo "    adding the sound-cue settings (new in 1.1.0)"
        cat >> "$APPDIR/config.toml" <<'EOF'

# Audible cue when the microphone is muted / unmuted, so you can tell which
# way it went without looking at the screen.
#   unmute / live -> rising two-note cue
#   mute          -> falling two-note cue
sound = true
sound_volume = 0.5
sound_sink = "default"
sound_mute = ""
sound_unmute = ""
EOF
    fi
else
    install -m 0644 "$REPO_DIR/config/config.toml" "$APPDIR/config.toml"
fi

say "installing systemd user units -> $UNIT_DIR"
install -d "$UNIT_DIR"
for unit in headset-button.service headset-button-tray.service; do
    sed "s|%h/.local|$PREFIX|g" "$REPO_DIR/systemd/$unit" > "$UNIT_DIR/$unit"
done

if [ "$MASK_PROXY" = 1 ]; then
    if systemctl --user list-unit-files mpris-proxy.service >/dev/null 2>&1; then
        say "masking mpris-proxy.service (it would otherwise own the button)"
        systemctl --user mask mpris-proxy.service || warn "could not mask mpris-proxy"
    fi
fi

# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------
systemctl --user daemon-reload

if [ "$START" = 1 ]; then
    say "enabling and starting services"
    systemctl --user enable --now headset-button.service
    if [ "$WITH_TRAY" = 1 ]; then
        systemctl --user enable --now headset-button-tray.service
    fi
    sleep 1
    systemctl --user --no-pager --lines=0 status headset-button.service || true
else
    say "skipping service start (--no-start)"
fi

cat <<EOF

$(printf '\033[32mDone.\033[0m')

  Try it      press the centre button on your headset
  Or fake it  headset-button simulate
  Change it   click the headset icon in the top bar
  Diagnose    headset-button doctor
  Undo        $REPO_DIR/uninstall.sh

EOF
