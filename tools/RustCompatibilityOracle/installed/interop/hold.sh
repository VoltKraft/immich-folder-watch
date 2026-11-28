#!/bin/sh
# Keep the reviewed writer alive while both installed packages' native namespaces are observed.
set -eu
umask 077
case "$FLATPAK_ID" in
    org.example.IfwInteropProbe|io.github.voltkraft.immich-folder-watch) ;;
    *) exit 2 ;;
esac
grep -qx branch=test /.flatpak-info
test -r /.flatpak-info && test "$HOME" = /tmp/home && test -d "$XDG_RUNTIME_DIR"
stat -Lc 'XDG_RUNTIME_DIR %d %i %a' "$XDG_RUNTIME_DIR"
# This read checks only whether the normal application endpoint is visible, without opening it.
if test -S "$XDG_RUNTIME_DIR/immich-folder-watch.sock"; then
    stat -Lc 'NORMAL_ENDPOINT visible %d %i' "$XDG_RUNTIME_DIR/immich-folder-watch.sock"
else
    echo 'NORMAL_ENDPOINT absent'
fi
fixture=$(mktemp -d /tmp/ifw-profile.XXXXXXXX)
printf 'synthetic-only\n' > "$fixture/.ifw-instance-fixture"
: > "$fixture/writer.lock"
exec /app/bin/instance writer "$fixture" unix 0
