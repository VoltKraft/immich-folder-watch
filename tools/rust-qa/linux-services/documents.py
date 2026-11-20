"""Exercise an actual Documents portal directory grant and its per-application FUSE view."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess

from gi.repository import Gio, GLib
from session import checked_start, check_alive, wait_for


SERVICE = "org.freedesktop.portal.Documents"
OBJECT = "/org/freedesktop/portal/documents"
APP = "org.example.IfwServices"


def probe(stack, expected_lock):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    def method(name, args=None):
        return bus.call_sync(SERVICE, OBJECT, SERVICE, name, args, None, Gio.DBusCallFlags.NONE, 4000, None).unpack()

    store_log = Path("/qa/permission-store.log")
    store = checked_start(stack, ["/usr/libexec/xdg-permission-store", "-v"], store_log)
    log = Path("/qa/documents.log")
    daemon = checked_start(stack, ["/probe/xdg-document-portal", "-v"], log)
    def mountpoint():
        check_alive(daemon, log)
        check_alive(store, store_log)
        try:
            return method("GetMountPoint")
        except GLib.Error:
            return None
    raw_mount, = wait_for(mountpoint, 10, "Document portal did not report its FUSE mount")
    mount = Path(os.fsdecode(bytes(raw_mount).removesuffix(b"\0")))
    mountinfo = [line for line in Path("/proc/self/mountinfo").read_text().splitlines()
                 if line.split()[4] == str(mount)]
    if len(mountinfo) != 1 or " - fuse.portal " not in mountinfo[0]:
        raise RuntimeError("Returned path is not a mounted Documents portal filesystem")
    base = Path("/tmp/producer")
    backing = base / "source"
    album = backing / "album"
    album.mkdir(mode=0o700, parents=True)
    (album / "original.jpg").write_text("Synthetic upload fixture\n")
    sentinel = base / "outside"
    sentinel.write_text("Outside sentinel\n")
    unsafe_entries = backing / "links"
    unsafe_entries.mkdir()
    (unsafe_entries / "outside-link").symlink_to(sentinel)
    (unsafe_entries / "control.jpg").write_bytes(b"Synthetic in-grant link target\n")
    (unsafe_entries / "in-grant-link").symlink_to("control.jpg")
    descriptor = os.open(backing, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        handles = Gio.UnixFDList.new()
        handle = handles.append(descriptor)
        reply, _ = bus.call_with_unix_fd_list_sync(SERVICE, OBJECT, SERVICE, "AddFull",
            GLib.Variant("(ahusas)", ([handle], 8, APP, ["read"])), None, Gio.DBusCallFlags.NONE, 4000, handles, None)
    finally:
        os.close(descriptor)
    ids, extra = reply.unpack()
    if len(ids) != 1 or Path(ids[0]).name != ids[0] or ids[0] in ("", ".", "..", "by-app"):
        raise RuntimeError("Unexpected document token")
    token, = ids
    result = {"mountinfo": mountinfo[0], "document_id": token, "access_view": str(mount / "by-app" / APP / token / backing.name),
              "extra_mountpoint": os.fsdecode(bytes(extra.get("mountpoint", [])).removesuffix(b"\0")),
              "synthetic_backing": str(backing), "namespace_uid_map": Path("/proc/self/uid_map").read_text().strip(),
              "consumer": "nested private mount with hidden producer and dropped capabilities", "expected_lock": expected_lock,
              "operations": {}}
    output = Path("/qa/documents.json")
    def save():
        output.write_text(json.dumps(result, indent=2) + "\n")
    def consumer(mode):
        # The daemon keeps its original mount view. The client sees an empty tmpfs over the entire producer.
        command = ["bwrap", "--die-with-parent", "--bind", "/", "/", "--dev", "/dev",
                   "--tmpfs", str(base), "--cap-drop", "ALL", "--", "/probe/grant", token, backing.name, mode]
        proc = subprocess.run(command, capture_output=True, timeout=10, text=True)
        result["operations"][mode] = {"code": proc.returncode, "stdout": proc.stdout.splitlines(),
                                      "stderr": proc.stderr.splitlines()}
        save()
        if proc.returncode:
            raise RuntimeError(f"Grant-relative {mode} failed: {proc.stderr.strip()}")
        if mode != "revoked":
            lines = proc.stdout.splitlines()
            if expected_lock == "supported":
                if not any(line.startswith("READ ") for line in lines):
                    raise RuntimeError("The supported portal did not return a validated handle-relative read")
            elif not any(line.startswith("READ_CAPABILITY_REFUSED ") and "os error 38" in line for line in lines):
                raise RuntimeError("Expected the distribution portal to refuse flock with ENOSYS")
    save()
    try:
        version, = bus.call_sync(SERVICE, OBJECT, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (SERVICE, "version")), None, Gio.DBusCallFlags.NONE, 4000, None).unpack()
        result["interface_version"] = version
        if version >= 5:
            paths, = method("GetHostPaths", GLib.Variant("(as)", ([token],)))
            result["display_host_path"] = os.fsdecode(bytes(paths[token]).removesuffix(b"\0"))
            if result["display_host_path"] != str(backing):
                raise RuntimeError("Portal host-path observation did not match the synthetic chooser directory")
        consumer("read-only")
        if (backing / "forbidden.jpg").exists() or sorted(p.name for p in backing.iterdir()) != ["album", "links"]:
            raise RuntimeError("Read-only operation created a backing entry")
        method("GrantPermissions", GLib.Variant("(ssas)", (token, APP, ["write"])))
        from locks import lock_checks
        lock_checks(backing, Path(result["access_view"]), expected_lock)
        consumer("read-write")
        if (album / "download.jpg").read_bytes() != b"Synthetic download fixture\n":
            raise RuntimeError("Producer readback did not find the grant-relative publication")
        outer = [p for p in album.iterdir() if p.name not in {"download.jpg", "original.jpg"}]
        if (len(outer) != 1 or not re.fullmatch(r"\.ifw-internal-[0-9a-f]{32}", outer[0].name)
                or not stat.S_ISDIR(outer[0].lstat().st_mode) or outer[0].stat().st_mode & 0o777 != 0o700
                or any(outer[0].iterdir())):
            raise RuntimeError("Unexpected payload or transaction entries in the synthetic producer")
        result["empty_private_staging_container"] = True
        method("RevokePermissions", GLib.Variant("(ssas)", (token, APP, ["write", "read"])))
        consumer("revoked")
        if sentinel.read_text() != "Outside sentinel\n":
            raise RuntimeError("Outside sentinel changed")
        result.update(backing_readback=True, outside_sentinel_unchanged=True)
    finally:
        method("Delete", GLib.Variant("(s)", (token,)))
        save()
    return result
