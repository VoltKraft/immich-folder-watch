#!/bin/bash
# Install, qualify and restore the actual packages in a fresh, offline test VM.
set -eu -o pipefail
test "$(cat /sys/class/dmi/id/product_name)" = IFW-Noble-Portal-QA
test "$(cat /sys/class/dmi/id/product_serial)" = "$(cat /mnt/ifw/trial-id)"
test "$(findmnt -no LABEL -T /mnt/ifw)" = cidata
test "$(findmnt -no LABEL -T /mnt/result)" = IFWRESULT
seed=/mnt/ifw/payload
base=1.18.4-1ubuntu2.24.04.3
stock="$seed/debs/xdg-desktop-portal_${base}_amd64.deb"
app=org.example.IfwPortalLease
home=/home/ifwqa
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
python3 -B - "$seed" "$stock" <<'PY'
import hashlib, json, pathlib, sys
def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
seed = pathlib.Path(sys.argv[1])
data = json.loads((seed / "inputs.json").read_text())
checks = [(pathlib.Path("/var/lib/dpkg/status"), data["guestStatus"]),
                       (pathlib.Path(sys.argv[2]), data["stock"]),
                       (seed / "reader", data["reader"]), (seed / "platform.flatpak", data["runtime"]["sha256"])]
if (seed.parent / "stage").read_text().strip() == "lease":
    checks.append((seed / "candidate.deb", data["candidate"]))
for path, expected in checks:
    if sha(path) != expected:
        raise ValueError("Lease guest received a different input: " + str(path))
PY
apt_dir=/var/tmp/ifw-offline-apt
mkdir -p "$apt_dir/lists/partial" "$apt_dir/sources.list.d"
touch "$apt_dir/sources.list"
install_local() {
    apt-get --no-install-recommends --no-remove -y -o Dir::Etc::sourcelist="$apt_dir/sources.list" \
        -o Dir::Etc::sourceparts="$apt_dir/sources.list.d" -o Dir::State::lists="$apt_dir/lists" "$@"
}
install_local install "$seed"/debs/*.deb
test "$(dpkg-query -W -f='${Version}' xdg-desktop-portal)" = "$base"
useradd --create-home --shell /bin/bash ifwqa
uid=$(id -u ifwqa)
loginctl enable-linger ifwqa
systemctl start "user@${uid}.service"
as_user() {
    runuser -u ifwqa -- env -i HOME="$home" USER=ifwqa LOGNAME=ifwqa LC_ALL=C.UTF-8 \
        PATH=/usr/bin:/bin XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" "$@"
}
as_user flatpak --user install --bundle --noninteractive --no-deps --no-related "$seed/platform.flatpak"
runtime_commit=$(as_user flatpak --user info --show-commit org.freedesktop.Platform//26.08)
test "$runtime_commit" = "$(cat "$seed/runtime-commit")"
mkdir -p /var/tmp/ifw-lease/app/files/bin /var/tmp/ifw-lease/app/var
appdir=/var/tmp/ifw-lease/app
printf '[Application]\nname=%s\nruntime=org.freedesktop.Platform/x86_64/26.08\nsdk=org.freedesktop.Sdk/x86_64/26.08\n' "$app" > "$appdir/metadata"
install -m 0755 "$seed/reader" "$appdir/files/bin/reader"
flatpak build-finish --command=reader "$appdir"
flatpak build-export --arch=x86_64 /var/tmp/ifw-lease/app-ref "$appdir" test
as_user flatpak --user remote-add --no-gpg-verify fixture file:///var/tmp/ifw-lease/app-ref
as_user flatpak --user install --noninteractive --no-deps --no-related fixture "app/$app/x86_64/test"
app_commit=$(as_user flatpak --user info --show-commit "$app//test")
test "$app_commit" = "$(ostree --repo=/var/tmp/ifw-lease/app-ref rev-parse "app/$app/x86_64/test")"
dpkg-deb -x "$stock" /var/tmp/ifw-lease/stock
observe() {
    local phase=$1 expected=$2 payload=$3 report="$home/$1.json" rc=0
    test "$(dpkg-query -W -f='${Status} ${Version}' xdg-desktop-portal)" = "install ok installed $expected" || return 1
    as_user python3 -B "$seed/lease.py" --phase "$phase" --output "$report" --payload "$payload" || rc=$?
    if test -f "$report"; then cp "$report" "/mnt/result/$phase.json" || return 1; fi
    return "$rc"
}
stop_portals() {
    as_user systemctl --user stop xdg-document-portal.service xdg-permission-store.service
}
observe stock "$base" /var/tmp/ifw-lease/stock
candidate_rc=0
restored_rc=0
if test "$(cat /mnt/ifw/stage)" = lease; then
    dpkg-deb -x "$seed/candidate.deb" /var/tmp/ifw-lease/candidate
    stop_portals
    install_local install "$seed/candidate.deb" || candidate_rc=$?
    if test "$candidate_rc" = 0; then
        observe candidate "$base+ifwqa1" /var/tmp/ifw-lease/candidate || candidate_rc=$?
    fi
    # Try each rollback step even when the candidate or one restoration step failed.
    stop_portals || restored_rc=$?
    install_local --allow-downgrades install "$stock" || restored_rc=$?
    observe restored "$base" /var/tmp/ifw-lease/stock || restored_rc=$?
    test -z "$(dpkg --audit)" || restored_rc=1
fi
state=$(dpkg-query -W -f='${Status} ${Version}' xdg-desktop-portal)
python3 -B "$seed/lease_result.py" "$seed" /mnt/result "$app_commit" "$runtime_commit" \
    "$candidate_rc" "$restored_rc" "$state"
