"""Own one disposable Windows VHD; never select, format or write a host disk."""

from __future__ import annotations

import ctypes as ct
import io
import json
import os
from pathlib import Path
import platform
import queue
import re
import shutil
import struct
import subprocess
import threading
import time
import uuid

import windows_image as image

U32 = ct.c_uint32
U64 = ct.c_uint64
HANDLE = ct.c_void_p
INVALID_HANDLE = ct.c_void_p(-1).value


class Unavailable(RuntimeError):
    """A required disposable-runner capability is unavailable; never a pass."""


def send_release_space(pipe: io.TextIOWrapper) -> dict:
    """Send the exact private Rust protocol token after independent full checks."""
    # Popen text-mode stdin otherwise translates LF to CRLF on Windows. The
    # Rust worker deliberately accepts only this exact token, without trimming.
    pipe.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    acknowledgement = "release-space\n"
    if pipe.write(acknowledgement) != len(acknowledgement):
        raise OSError("incomplete private filesystem release acknowledgement")
    pipe.flush()
    return {"bytes": len(acknowledgement), "utf8_hex": acknowledgement.encode("utf-8").hex()}


def hosted_gate(root: Path, env: dict) -> None:
    if (os.name != "nt" or env.get("GITHUB_ACTIONS") != "true"
            or env.get("RUNNER_ENVIRONMENT") != "github-hosted" or env.get("RUNNER_OS") != "Windows"
            or env.get("GITHUB_REPOSITORY", "").lower() != "voltkraft/immich-folder-watch"
            or (env.get("GITHUB_HEAD_REF") or env.get("GITHUB_REF_NAME")) != "rewrite/rust"
            or Path(env.get("GITHUB_WORKSPACE", "")).resolve() != root.resolve()):
        raise Unavailable("VHD exhaustion is restricted to this repository's disposable hosted rewrite/rust Windows candidate")
    architecture = platform.machine().lower()
    if (architecture not in ("amd64", "arm64") or env.get("RUNNER_ARCH", "").lower() != {"amd64": "x64", "arm64": "arm64"}[architecture]
            or ct.sizeof(ct.c_void_p) != 8):
        raise Unavailable("native Windows x64/ARM64 process and runner are required")


class StorageType(ct.Structure):
    _fields_ = [("device", U32), ("vendor", ct.c_ubyte * 16)]


class Api:
    def __init__(self) -> None:
        self.kernel = ct.WinDLL("kernel32", use_last_error=True, winmode=0x800)
        self.virtual = ct.WinDLL("virtdisk", use_last_error=True, winmode=0x800)
        self.functions = {}

        def bind(library, name, result, arguments):
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
            self.functions[name] = function

        ptr = ct.c_void_p
        string = ct.c_wchar_p
        bind(self.kernel, "CreateFileW", HANDLE, [string, U32, U32, ptr, U32, U32, HANDLE])
        bind(self.kernel, "CloseHandle", ct.c_int, [HANDLE])
        bind(self.kernel, "ReadFile", ct.c_int, [HANDLE, ptr, U32, ct.POINTER(U32), ptr])
        bind(self.kernel, "SetFilePointerEx", ct.c_int, [HANDLE, ct.c_int64, ptr, U32])
        bind(self.kernel, "DeviceIoControl", ct.c_int, [HANDLE, U32, ptr, U32, ptr, U32, ct.POINTER(U32), ptr])
        bind(self.kernel, "GetFileInformationByHandle", ct.c_int, [HANDLE, ptr])
        bind(self.kernel, "GetFileInformationByHandleEx", ct.c_int, [HANDLE, U32, ptr, U32])
        bind(self.kernel, "GetFinalPathNameByHandleW", U32, [HANDLE, string, U32, U32])
        bind(self.kernel, "GetModuleFileNameW", U32, [HANDLE, string, U32])
        bind(self.kernel, "FindFirstVolumeW", HANDLE, [string, U32])
        bind(self.kernel, "FindNextVolumeW", ct.c_int, [HANDLE, string, U32])
        bind(self.kernel, "FindVolumeClose", ct.c_int, [HANDLE])
        bind(self.kernel, "GetVolumePathNamesForVolumeNameW", ct.c_int, [string, string, U32, ct.POINTER(U32)])
        bind(self.kernel, "GetVolumeInformationW", ct.c_int, [string, string, U32, ct.POINTER(U32), ct.POINTER(U32), ct.POINTER(U32), string, U32])
        bind(self.kernel, "GetDiskFreeSpaceExW", ct.c_int, [string, ct.POINTER(U64), ct.POINTER(U64), ct.POINTER(U64)])
        bind(self.kernel, "GetDiskFreeSpaceW", ct.c_int, [string, ct.POINTER(U32), ct.POINTER(U32), ct.POINTER(U32), ct.POINTER(U32)])
        bind(self.kernel, "GetDriveTypeW", U32, [string])
        bind(self.kernel, "MoveFileW", ct.c_int, [string, string])
        bind(self.virtual, "OpenVirtualDisk", U32, [ct.POINTER(StorageType), string, U32, U32, ptr, ct.POINTER(HANDLE)])
        bind(self.virtual, "AttachVirtualDisk", U32, [HANDLE, ptr, U32, U32, ptr, ptr])
        bind(self.virtual, "DetachVirtualDisk", U32, [HANDLE, U32, U32])
        bind(self.virtual, "GetVirtualDiskPhysicalPath", U32, [HANDLE, ct.POINTER(U32), string])

    def __getattr__(self, name):
        return self.functions[name]

    @staticmethod
    def require(ok, operation: str) -> None:
        if not ok:
            raise OSError(ct.get_last_error(), operation)

    def open_file(self, path: str, access: int = 0, share: int = 3) -> int:
        handle = self.CreateFileW(path, access, share, None, 3, 0, None)
        if handle in (None, INVALID_HANDLE):
            raise OSError(ct.get_last_error(), "CreateFileW: " + path)
        return handle

    def ioctl(self, handle: int, code: int, size: int) -> bytes:
        data = ct.create_string_buffer(size)
        used = U32()
        self.require(self.DeviceIoControl(handle, code, None, 0, data, size, ct.byref(used), None), "DeviceIoControl")
        return data.raw[:used.value]

    def identity(self, handle: int) -> dict:
        legacy = ct.create_string_buffer(52)
        self.require(self.GetFileInformationByHandle(handle, legacy), "GetFileInformationByHandle")
        fields = struct.unpack("<13I", legacy.raw)
        extended = ct.create_string_buffer(24)
        supported = bool(self.GetFileInformationByHandleEx(handle, 18, extended, 24))
        error = 0 if supported else ct.get_last_error()
        if not supported and error not in (1, 50, 87):
            raise OSError(error, "FileIdInfo")
        return {"attributes": fields[0], "volume_serial": fields[7], "links": fields[10],
                "legacy_id": (fields[11] << 32) | fields[12], "extended_supported": supported,
                "extended_error": error, "extended_volume_serial": int.from_bytes(extended.raw[:8], "little") if supported else None,
                "extended_id": extended.raw[8:].hex() if supported else None}

    def physical_path(self, disk: int) -> str:
        buffer = ct.create_unicode_buffer(512)
        size = U32(ct.sizeof(buffer))
        code = self.GetVirtualDiskPhysicalPath(disk, ct.byref(size), buffer)
        if code:
            raise OSError(code, "GetVirtualDiskPhysicalPath")
        if not re.fullmatch(r"\\\\\.\\PhysicalDrive[0-9]+", buffer.value, re.IGNORECASE):
            raise ValueError("unexpected handle-derived physical path")
        return buffer.value

    def volumes(self) -> set[str]:
        buffer = ct.create_unicode_buffer(1024)
        handle = self.FindFirstVolumeW(buffer, len(buffer))
        if handle in (None, INVALID_HANDLE):
            raise OSError(ct.get_last_error(), "FindFirstVolumeW")
        result = set()
        try:
            while True:
                result.add(buffer.value)
                if not self.FindNextVolumeW(handle, buffer, len(buffer)):
                    if ct.get_last_error() != 18:
                        raise OSError(ct.get_last_error(), "FindNextVolumeW")
                    return result
                if len(result) > 128:
                    raise ValueError("unexpected runner volume inventory size")
        finally:
            self.FindVolumeClose(handle)

    def capacity(self, volume: str) -> dict:
        available, total, free = U64(), U64(), U64()
        self.require(self.GetDiskFreeSpaceExW(volume, ct.byref(available), ct.byref(total), ct.byref(free)), "GetDiskFreeSpaceExW")
        return {"available_bytes": available.value, "total_bytes": total.value, "free_bytes": free.value}

    def system_modules(self) -> dict:
        result = {}
        for library in (self.kernel, self.virtual):
            path = ct.create_unicode_buffer(32768)
            length = self.GetModuleFileNameW(library._handle, path, len(path))
            if not length or length >= len(path):
                raise OSError(ct.get_last_error(), "GetModuleFileNameW")
            file = Path(path.value)
            if file.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("unexpected native OS module size")
            result[file.name] = {"path": path.value, "sha256": image.sha256(file.read_bytes()),
                                 "loader": "LOAD_LIBRARY_SEARCH_SYSTEM32"}
        return result


def run(executable: Path, seed: Path, output: Path, mode: str, env: dict, root: Path) -> dict:
    directory = output.with_name(output.name + "-volume")
    directory.mkdir(exist_ok=False)
    receipt_path = directory / "windows-vhd.json"
    report = {"format": "ifw-private-windows-vhd-v1", "status": "preparing", "events": [], "snapshot_checks": []}

    def save() -> None:
        receipt_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    api = None
    disk = backing = physical = volume_handle = None
    process = None
    attached = False
    volume = None
    vhd = directory / "owned.vhd"
    anchor = None
    try:
        hosted_gate(root, env)
        image.no_reparse(directory)
        api = Api()
        report["system_modules"] = api.system_modules()
        if api.GetDriveTypeW(str(directory.anchor)) != 3 or shutil.disk_usage(directory).free < 256 * 1024 * 1024:
            raise Unavailable("backing file requires a local fixed host volume with at least 256 MiB free")
        before_volumes = api.volumes()
        new_id = uuid.uuid4()
        report["image"] = image.create(vhd, new_id)
        expected_mbr = vhd.read_bytes()[:512]
        expected_footer = vhd.read_bytes()[-512:]
        # Deny delete/rename of the exact backing file for the entire attachment.
        backing = api.open_file(str(vhd), 0x80000000, 3)
        backing_id = api.identity(backing)
        if backing_id["links"] != 1 or backing_id["legacy_id"] == 0 or backing_id["attributes"] & (0x400 | 0x200 | 0x800 | 0x4000):
            raise ValueError("backing file is redirected, sparse, compressed, encrypted or lacks identity")
        final = ct.create_unicode_buffer(32768)
        length = api.GetFinalPathNameByHandleW(backing, final, len(final), 0)
        if not length or length >= len(final) or os.path.normcase(final.value.removeprefix("\\\\?\\")) != os.path.normcase(str(vhd)):
            raise ValueError("opened backing file differs from the exact newly created path")
        report["backing_file_identity"] = backing_id
        # Independently re-read and validate every byte before attachment.
        if image.verify(vhd, new_id) != report["image"]:
            raise ValueError("backing file changed before attachment")
        storage = StorageType(2, (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID("ec984aec-a0f9-47e9-901f-71415a66345b").bytes_le))
        owned_handle = HANDLE()
        code = api.OpenVirtualDisk(ct.byref(storage), str(vhd), 0x000e0000, 0, None, ct.byref(owned_handle))
        if code:
            raise Unavailable(f"OpenVirtualDisk capability unavailable: Win32 {code}")
        disk = owned_handle.value
        code = api.AttachVirtualDisk(disk, None, 2, 0, None, None)
        if code:
            raise Unavailable(f"AttachVirtualDisk requires available native VHD/admin capability: Win32 {code}")
        attached = True
        physical_path = api.physical_path(disk)
        physical = api.open_file(physical_path, 0x80000000)
        device = api.ioctl(physical, 0x002d1080, 12)
        if len(device) != 12:
            raise ValueError("unexpected STORAGE_DEVICE_NUMBER size")
        device_type, device_number, _ = struct.unpack("<III", device)
        if device_type != 7 or device_number != int(re.search(r"[0-9]+$", physical_path)[0]):
            raise ValueError("physical handle does not identify its VHD disk")
        if struct.unpack("<Q", api.ioctl(physical, 0x0007405c, 8))[0] != image.DISK_BYTES:
            raise ValueError("attached physical capacity differs from the bounded image")

        def validate_backing() -> None:
            if api.physical_path(disk) != physical_path or api.identity(backing) != backing_id or vhd.stat().st_size != image.DISK_BYTES + 512:
                raise ValueError("live backing file or virtual-disk handle identity changed")
            api.require(api.SetFilePointerEx(physical, 0, None, 0), "SetFilePointerEx for readonly MBR")
            mbr = ct.create_string_buffer(512)
            used = U32()
            api.require(api.ReadFile(physical, mbr, 512, ct.byref(used), None), "ReadFile readonly MBR")
            if used.value != 512 or mbr.raw != expected_mbr:
                raise ValueError("attached disk differs from the newly initialized MBR")

        validate_backing()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and volume is None:
            for candidate in api.volumes() - before_volumes:
                if not re.fullmatch(r"\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\", candidate):
                    continue
                handle = None
                try:
                    handle = api.open_file(candidate.rstrip("\\"))
                    extents = api.ioctl(handle, 0x00560000, 128)
                    if (len(extents) == 32 and struct.unpack_from("<I", extents, 0)[0] == 1
                            and struct.unpack_from("<I", extents, 8)[0] == device_number
                            and struct.unpack_from("<QQ", extents, 16) == (image.PARTITION_OFFSET, image.PARTITION_BYTES)):
                        if volume is not None:
                            raise ValueError("more than one matching new volume")
                        volume, volume_handle = candidate, handle
                        handle = None
                except OSError:
                    pass
                finally:
                    if handle is not None:
                        api.CloseHandle(handle)
            if volume is None:
                time.sleep(0.2)
        if volume is None:
            raise Unavailable("new bounded FAT16 volume did not become available; no online/format fallback is permitted")
        paths = ct.create_unicode_buffer(4096)
        length = U32()
        api.require(api.GetVolumePathNamesForVolumeNameW(volume, paths, len(paths), ct.byref(length)), "GetVolumePathNamesForVolumeNameW")
        if paths.value:
            raise ValueError("new volume unexpectedly received a drive letter or other mount path")
        label, filesystem = ct.create_unicode_buffer(256), ct.create_unicode_buffer(256)
        serial, maximum, flags = U32(), U32(), U32()
        api.require(api.GetVolumeInformationW(volume, label, len(label), ct.byref(serial), ct.byref(maximum), ct.byref(flags), filesystem, len(filesystem)), "GetVolumeInformationW")
        cluster_sectors, sector_bytes, free_clusters, total_clusters = U32(), U32(), U32(), U32()
        api.require(api.GetDiskFreeSpaceW(volume, ct.byref(cluster_sectors), ct.byref(sector_bytes), ct.byref(free_clusters), ct.byref(total_clusters)), "GetDiskFreeSpaceW")
        if (filesystem.value != "FAT" or label.value != "IFWFAULT" or serial.value != report["image"]["filesystem_serial"]
                or sector_bytes.value != 512 or cluster_sectors.value != 4 or total_clusters.value != report["image"]["data_clusters"]):
            raise ValueError("mounted filesystem/serial/geometry differs from the new template")

        def validate_volume() -> dict:
            validate_backing()
            extents = api.ioctl(volume_handle, 0x00560000, 128)
            if (len(extents) != 32 or struct.unpack_from("<I", extents, 0)[0] != 1
                    or struct.unpack_from("<I", extents, 8)[0] != device_number
                    or struct.unpack_from("<QQ", extents, 16) != (image.PARTITION_OFFSET, image.PARTITION_BYTES)):
                raise ValueError("mounted volume extent changed")
            capacity = api.capacity(volume)
            if capacity["total_bytes"] != report["image"]["data_bytes"]:
                raise ValueError("volume capacity exceeds or differs from its known data region")
            return capacity

        report.update({"physical_device": physical_path, "device_number": device_number, "volume_guid": volume,
                       "filesystem": filesystem.value, "volume_serial": serial.value, "attach_flags": ["NO_DRIVE_LETTER"],
                       "handle_bound_lifetime": True, "capacity_before": validate_volume()})
        # Observation only: FAT identifiers may change on rename. They never
        # select a delete, rename, disk, mount or restoration destination.
        probe, renamed = Path(volume) / "handle-id-probe.txt", Path(volume) / "handle-id-renamed.txt"
        with probe.open("xb") as stream:
            stream.write(b"synthetic FAT handle identity observation\n")
        probe_handle = api.open_file(str(probe), 0x80000000, 7)
        try:
            before_identity = api.identity(probe_handle)
            if before_identity["legacy_id"] == 0:
                raise ValueError("owned FAT file lacks its ordinary nonzero legacy identifier")
            validate_volume()
            api.require(api.MoveFileW(str(probe), str(renamed)), "MoveFileW owned observation")
            after_identity = api.identity(probe_handle)
            report["fat_handle_identity"] = {"before": before_identity, "after_same_handle": after_identity,
                "rename_changed_legacy_id": before_identity["legacy_id"] != after_identity["legacy_id"],
                "authorization_by_cached_id": False}
        finally:
            api.CloseHandle(probe_handle)
        validate_volume()
        renamed.unlink()
        nonce = str(uuid.uuid4())
        authority = {"format": "ifw-owned-vhd-authority-v1", "volume_guid": volume,
                     "virtual_bytes": image.DISK_BYTES, "nonce": nonce,
                     "initial_image_sha256": report["image"]["image_sha256"]}
        with (Path(volume) / "ifw-vhd-authorization.json").open("x", encoding="utf-8") as stream:
            json.dump(authority, stream)
        child_env = dict(env, IFW_STORAGE_VHD_VOLUME=volume, IFW_STORAGE_VHD_NONCE=nonce)
        validate_volume()
        save()
        process = subprocess.Popen([str(executable), "worker", str(seed), str(output), mode, "windows-full", volume],
                                   cwd=root, env=child_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8")
        lines = queue.Queue()
        errors = []

        def receive() -> None:
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=receive, daemon=True)
        error_reader = threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True)
        reader.start()
        error_reader.start()
        deadline = time.monotonic() + 60

        def check_snapshot(phase: str) -> None:
            actual = image.sha256((output / "snapshot.db").read_bytes())
            if anchor is None or actual != anchor:
                raise ValueError("SNAPSHOT_SHA256_MISMATCH in Windows volume supervisor")
            report["snapshot_checks"].append({"phase": phase, "sha256": actual})

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Windows VHD worker exceeded 60 seconds")
            line = lines.get(timeout=remaining)
            if line is None:
                break
            event = json.loads(line)
            report["events"].append(event)
            if event["phase"] == "backup-completed" and event["file"] == "snapshot.db":
                if anchor is not None:
                    raise ValueError("duplicate original snapshot event")
                anchor = event["sha256"]
                check_snapshot("backup-completed")
            if "snapshot_sha256" in event and event["snapshot_sha256"] != anchor:
                raise ValueError("Windows fault event changed the original digest")
            if event["phase"] == "windows-full-observed":
                capacity = validate_volume()
                if capacity["available_bytes"] != 0 or capacity["free_bytes"] != 0 or event["win32_error"] not in (39, 112) or event["sqlite_extended_error"] != 13:
                    raise ValueError("missing actual Windows filesystem-full observation")
                if shutil.disk_usage(directory).free < 128 * 1024 * 1024:
                    raise ValueError("host free-space floor changed unexpectedly")
                report["capacity_at_error"] = capacity
                report["win32_error"] = event["win32_error"]
                check_snapshot("filesystem-full-before-release-and-restore")
                save()
                report["release_acknowledgement"] = send_release_space(process.stdin)
            save()
        code = process.wait(timeout=10)
        reader.join(timeout=5)
        error_reader.join(timeout=5)
        report["exit_code"], report["stderr"] = code, "".join(errors)
        if code or "capacity_at_error" not in report:
            raise RuntimeError("Windows full-volume worker failed or did not reach its genuine full barrier")
        report["capacity_after"] = validate_volume()
        if report["capacity_after"]["available_bytes"] <= 0:
            raise ValueError("owned filler was not released before same-volume restore")
        check_snapshot("after-same-volume-restore")
        report["snapshot_sha256"] = anchor
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "unavailable" if isinstance(error, Unavailable) else "failed"
        report["error"] = str(error)
        raise
    finally:
        cleanup_errors = []
        if process is not None and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except Exception as error:
                cleanup_errors.append("owned child termination: " + str(error))
        if api is not None:
            try:
                for handle in (volume_handle, physical):
                    if handle is not None and not api.CloseHandle(handle):
                        cleanup_errors.append("closing owned volume/physical read handle failed")
                if attached:
                    code = api.DetachVirtualDisk(disk, 0, 0)
                    report["detach_win32_error"] = code
                    if code:
                        cleanup_errors.append("explicit detach failed; handle close still ends non-permanent lifetime: " + str(code))
            except Exception as error:
                cleanup_errors.append("explicit detach: " + str(error))
            finally:
                # Never skip virtual handle close if an earlier cleanup step
                # fails. PERMANENT_LIFETIME was deliberately never requested.
                if disk is not None and not api.CloseHandle(disk):
                    cleanup_errors.append("closing owned virtual-disk handle failed")
            try:
                if attached and report.get("detach_win32_error") == 0:
                    deadline = time.monotonic() + 10
                    while volume is not None and volume in api.volumes() and time.monotonic() < deadline:
                        time.sleep(0.2)
                    report["volume_absent_after_detach"] = volume is None or volume not in api.volumes()
                    if not report["volume_absent_after_detach"]:
                        cleanup_errors.append("owned volume remains after detach")
                    if api.identity(backing) != backing_id:
                        cleanup_errors.append("retained backing-file identity changed")
                    final_bytes = vhd.read_bytes()
                    report["detached_image_sha256"] = image.sha256(final_bytes)
                    report["detached_image_bytes"] = len(final_bytes)
                    report["retained_layout_unchanged"] = final_bytes[:512] == expected_mbr and final_bytes[-512:] == expected_footer
                    if len(final_bytes) != image.DISK_BYTES + 512 or not report["retained_layout_unchanged"]:
                        cleanup_errors.append("detached image size or fixed layout changed")
            except Exception as error:
                cleanup_errors.append("detached readback: " + str(error))
            finally:
                if backing is not None and not api.CloseHandle(backing):
                    cleanup_errors.append("closing retained backing-file handle failed")
        report["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            report["status"] = "failed"
        save()
    if report["status"] != "passed":
        raise RuntimeError("Windows VHD cleanup or detached readback failed")
    (output / "windows-vhd.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
