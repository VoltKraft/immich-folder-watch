#!/bin/sh
# Read the actual buses exposed to the installed ref using its unmodified runtime.
set -eu
test "$FLATPAK_ID" = org.example.IfwGuiProbe
test -r /.flatpak-info
sed -n '/^app-commit=/p; /^instance-id=/p' /.flatpak-info
printf 'gdbus='
sha256sum /usr/bin/gdbus
printf 'AT_SPI_BUS_ADDRESS=%s\n' "${AT_SPI_BUS_ADDRESS-}"
printf 'DBUS_SESSION_BUS_ADDRESS=%s\n' "${DBUS_SESSION_BUS_ADDRESS-}"

query() {
    name=$1
    shift
    printf 'BEGIN %s\n' "$name"
    result=0
    /usr/bin/gdbus call --timeout 3 "$@" 2>&1 || result=$?
    printf 'END %s %s\n' "$name" "$result"
}
query enabled --session --dest org.a11y.Bus --object-path /org/a11y/bus \
    --method org.freedesktop.DBus.Properties.Get org.a11y.Status IsEnabled
query address --session --dest org.a11y.Bus --object-path /org/a11y/bus --method org.a11y.Bus.GetAddress

test -S /run/flatpak/at-spi-bus
query registry --address unix:path=/run/flatpak/at-spi-bus --dest org.a11y.atspi.Registry \
    --object-path /org/a11y/atspi/accessible/root --method org.a11y.atspi.Accessible.GetChildren
query events --address unix:path=/run/flatpak/at-spi-bus --dest org.a11y.atspi.Registry \
    --object-path /org/a11y/atspi/registry --method org.a11y.atspi.Registry.GetRegisteredEvents
