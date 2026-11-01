#!/usr/bin/env bash
# Reverse everything install.sh did.

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
UNIT_DIR="$CONFIG_DIR/systemd/user"
APPDIR="$CONFIG_DIR/headset-button"

PURGE=0
UNMASK=1

usage() {
    cat <<EOF
Usage: ./uninstall.sh [options]

  --prefix DIR   prefix used at install time (default \$HOME/.local)
  --purge        also delete $APPDIR
  --keep-masked  leave mpris-proxy.service masked
  -h, --help     this text
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --purge) PURGE=1; shift ;;
        --keep-masked) UNMASK=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 3.12)"
SITE="$PREFIX/lib/python$PYVER/site-packages"

say "stopping and disabling services"
systemctl --user disable --now headset-button-tray.service 2>/dev/null || true
systemctl --user disable --now headset-button.service 2>/dev/null || true

say "removing units"
rm -f "$UNIT_DIR/headset-button.service" "$UNIT_DIR/headset-button-tray.service"
systemctl --user daemon-reload || true

say "removing launchers"
rm -f "$PREFIX/bin/headset-button" \
      "$PREFIX/bin/headset-button-bridge" \
      "$PREFIX/bin/headset-button-tray"

say "removing python package"
rm -rf "${SITE:?}/headset_button"

if [ "$UNMASK" = 1 ]; then
    if [ -L "$UNIT_DIR/mpris-proxy.service" ]; then
        say "unmasking mpris-proxy.service"
        systemctl --user unmask mpris-proxy.service || true
    fi
fi

if [ "$PURGE" = 1 ]; then
    say "removing $APPDIR"
    rm -rf "$APPDIR"
fi

echo
echo "Uninstalled. Reboot or log out and back in if the tray icon lingers."
