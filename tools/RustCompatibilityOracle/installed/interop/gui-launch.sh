#!/bin/sh
set -eu
test "$FLATPAK_ID" = io.github.voltkraft.immich-folder-watch && test "$HOME" = /tmp/home
grep -qx branch=test /.flatpak-info
socket=${DBUS_SESSION_BUS_ADDRESS#unix:path=}
case "$socket" in /run/flatpak/bus|/run/user/0/bus) ;; *) exit 2 ;; esac
test -S "$socket"
if ! ln -s "$socket" /tmp/session-bus 2>/dev/null; then
    test -L /tmp/session-bus && test "$(readlink /tmp/session-bus)" = "$socket"
fi
export DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/session-bus IFW_QA_ISOLATED=1
exec /app/bin/native-gui-assessment "$@"
