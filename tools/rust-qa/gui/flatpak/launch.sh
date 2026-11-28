#!/bin/sh
set -eu
test "$FLATPAK_ID" = org.example.IfwGuiProbe && test "$HOME" = /tmp/home && test -r /.flatpak-info
socket=${DBUS_SESSION_BUS_ADDRESS#unix:path=}
case "$socket" in /run/flatpak/bus|/run/user/0/bus) ;; *) exit 2;; esac
test -S "$socket"
if ! ln -s "$socket" /tmp/session-bus 2>/dev/null; then
    test -L /tmp/session-bus && test "$(readlink /tmp/session-bus)" = "$socket"
fi
# The native QA guard expects this name. Its target is Flatpak's private proxy socket.
export DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/session-bus IFW_QA_ISOLATED=1
instance=$(sed -n 's/^instance-id=//p' /.flatpak-info)
commit=$(sed -n 's/^app-commit=//p' /.flatpak-info)
printf 'FLATPAK_LAUNCH instance=%s pid=%s socket=%s commit=%s\n' "$instance" "$$" "$socket" "$commit"
exec /app/bin/native-gui-assessment "$@"
