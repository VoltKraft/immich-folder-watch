#!/bin/bash
# Build only inside the disposable cloud-init VM that owns the mounted evidence disk.
set -eu -o pipefail
test "$(cat /sys/class/dmi/id/product_name)" = IFW-Noble-Portal-QA
test "$(cat /sys/class/dmi/id/product_serial)" = "$(cat /mnt/ifw/trial-id)"
test "$(findmnt -no LABEL -T /mnt/ifw)" = cidata
test "$(findmnt -no LABEL -T /mnt/result)" = IFWRESULT
seed=/mnt/ifw/payload
out=/mnt/result
work=/var/tmp/ifw-build
exec >"$out/build.log" 2>&1
collect() {
    status=$?
    trap - EXIT
    if test -f "$work/result.json"; then
        cp "$work/result.json" "$out/package-result.json"
    else
        printf '{"status":"guest-setup-failed","exitCode":%d}\n' "$status" >"$out/package-result.json"
    fi
    if test -d "$work"; then
        # Preserve original source and binary package records and full test diagnostics.
        (cd "$work" && find . -maxdepth 1 -type f -print0 &&
            find reconstructed -type f \( -path '*/meson-logs/*' -o -name config.log \) -print0 2>/dev/null) |
            tar --null -C "$work" -T - -cf "$out/build-evidence.tar"
        if test "$status" -eq 0; then
            cp "$work"/xdg-desktop-portal_*_amd64.deb "$out/candidate.deb"
        fi
    else
        tar -C "$out" -cf "$out/build-evidence.tar" package-result.json
    fi
    journalctl -b -u geoclue.service --no-pager || true
    sync
    exit "$status"
}
trap collect EXIT
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
python3 -B - "$seed" <<'PY'
import hashlib, json, pathlib, sys
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
s = pathlib.Path(sys.argv[1])
plan = json.loads((s / "plan.json").read_text())
if digest(pathlib.Path("/var/lib/dpkg/status")) != plan["status"]:
    raise ValueError("Guest dpkg status differs from dependency resolution")
members = {pathlib.Path(row["Filename"]).name: row for row in plan["packages"]}
actual = {p.name for p in (s / "debs").iterdir()}
if not members or len(members) != len(plan["packages"]) or set(members) != actual:
    raise ValueError("Guest package medium differs from the dependency plan")
signed = json.loads((s / "apt-packages.json").read_text())["packages"]
for name, row in members.items():
    p = s / "debs" / name
    if p.stat().st_size != int(row["Size"]) or digest(p) != row["SHA256"] or signed[row["Filename"]] != row["SHA256"]:
        raise ValueError("Wrong Ubuntu package on the input medium: " + name)
PY
# APT must stage the named local archives. --no-download also forbids that local copy.
install -d /var/tmp/ifw-offline-apt/lists/partial /var/tmp/ifw-offline-apt/sources.list.d
touch /var/tmp/ifw-offline-apt/sources.list
apt-get -y --no-install-recommends --no-remove -o Dir::Etc::sourcelist=/var/tmp/ifw-offline-apt/sources.list \
    -o Dir::Etc::sourceparts=/var/tmp/ifw-offline-apt/sources.list.d -o Dir::State::lists=/var/tmp/ifw-offline-apt/lists \
    install "$seed"/debs/*.deb
dpkg --audit
useradd --create-home --shell /bin/bash ifwbuild
install -m 0700 -o ifwbuild -g ifwbuild -d /run/ifw-build
# The distribution's Location suite calls the real GeoClue system service. Give
# the test user its packaged agent and a synthetic static location in this VM.
test ! -e /etc/geolocation
printf '%s\n' 0.0 0.0 0.0 1.0 >/etc/geolocation
{
    for source in wifi network-nmea 3g cdma modem-gps compass; do
        printf '[%s]\nenable=false\n' "$source"
    done
    printf '[static-source]\nenable=true\n[xdg-desktop-portal]\nallowed=true\nsystem=true\nusers=%s;\n' "$(id -u ifwbuild)"
} >/etc/geoclue/conf.d/99-ifw-test.conf
systemctl restart geoclue.service
runuser -u ifwbuild -- env -i HOME=/home/ifwbuild USER=ifwbuild LOGNAME=ifwbuild LANG=C.UTF-8 \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin XDG_RUNTIME_DIR=/run/ifw-build \
    dbus-run-session -- bash -euc '
        /usr/libexec/geoclue-2.0/demos/agent &
        agent=$!
        trap "kill $agent 2>/dev/null || true" EXIT
        for try in {1..10}; do
            if gdbus call --system --dest org.freedesktop.GeoClue2 --timeout 3 \
                --object-path /org/freedesktop/GeoClue2/Manager --method org.freedesktop.GeoClue2.Manager.GetClient; then
                break
            fi
            if test "$try" = 10; then exit 1; fi
            sleep 1
        done
        python3 -B "$1/tools/rust-qa/portal-noble/installed/package/build.py" --inputs "$1/ubuntu-source" --output "$2"
    ' bash "$seed" "$work"
