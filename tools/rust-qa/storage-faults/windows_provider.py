"""Opt-in ordinary safe-fs observation on an already recovered, owned VHD."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import windows_image as image

CONTENTS = b"synthetic ordinary safe-fs FAT provider file\n"
CHECKS = ("opened_read", "ordinary_rename", "held_read_after_rename", "old_name_not_current",
          "new_name_reopened_read", "new_name_current", "handles_closed")


class Unavailable(RuntimeError):
    """A pre-existing capability is absent; never a passing observation."""


class ChildNotQuiescent(RuntimeError):
    """Do not remove names while an owned child might still access them."""


def durable_json(path: Path, value: dict) -> None:
    """Close and flush the complete receipt before granting the next phase."""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def require_recovery(path: Path) -> str:
    data = path.read_bytes()
    value = json.loads(data)
    if (value.get("format") != "ifw-before-provider-recovery-v1" or value.get("status") != "passed"
            or value.get("completed_cases") != 8 or value.get("csharp_assertions") != 208
            or value.get("original_snapshot_checks") != 8):
        raise ValueError("provider setup requires all eight completed recovery cases")
    return hashlib.sha256(data).hexdigest()


def source_files(repository: Path) -> list[Path]:
    crate = repository / "rust/crates/safe-fs"
    return [repository / "rust/Cargo.toml", crate / "Cargo.toml", *sorted((crate / "src").glob("*.rs"))]


def require_no_mount_paths(api, volume: str) -> None:
    paths = ct.create_unicode_buffer(4096)
    length = ct.c_uint32()
    api.require(api.GetVolumePathNamesForVolumeNameW(volume, paths, len(paths), ct.byref(length)),
                "read owned volume mount paths")
    if paths.value:
        raise ValueError("owned volume unexpectedly has a remaining mount path")


def require_native_pe(path: Path, target: str) -> None:
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("provider executable is not PE")
    offset = int.from_bytes(data[60:64], "little")
    expected = {"x86_64-pc-windows-msvc": 0x8664, "aarch64-pc-windows-msvc": 0xaa64}[target]
    if (data[offset:offset + 4] != b"PE\0\0"
            or int.from_bytes(data[offset + 4:offset + 6], "little") != expected):
        raise ValueError("provider executable has the wrong native machine")


def run_child(command: list[str], env: dict, cwd: Path, timeout: float = 15) -> dict:
    """Wait for this direct child before any owned-file cleanup, including timeout."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except Exception as error:
                raise ChildNotQuiescent(f"owned child {process.pid} termination not confirmed") from error
    if len(stdout) > 8192 or len(stderr) > 8192:
        raise ValueError("bounded provider produced oversized output")
    return {"pid": process.pid, "exit_code": process.returncode, "timed_out": timed_out,
            "wait_completed": True, "stdout": stdout.decode("utf-8", errors="strict"),
            "stderr": stderr.decode("utf-8", errors="replace")}


def validate_observation(child: dict) -> dict:
    if child["timed_out"] or not child["wait_completed"]:
        raise ValueError("provider child did not finish within its bound")
    if child["exit_code"] == 2:
        raise Unavailable("ordinary safe-fs provider lacks an existing right or supported identity")
    if child["exit_code"] != 0:
        raise ValueError("ordinary safe-fs provider failed")
    value = json.loads(child["stdout"])
    if value.get("format") != "ifw-safe-fs-fat-provider-v1" or any(value.get(key) is not True for key in CHECKS):
        raise ValueError("missing ordinary provider observations")
    pattern = r"FileIdentity \{ volume: [0-9]+, file: [1-9][0-9]* \}"
    if any(not re.fullmatch(pattern, value.get(key, "")) for key in ("acquired_identity", "reopened_identity")):
        raise ValueError("missing actual safe-fs file identities")
    if value.get("identity_changed_on_reopen") is not (value["acquired_identity"] != value["reopened_identity"]):
        raise ValueError("inconsistent identity observation")
    return value


def volume_files(volume: Path) -> dict:
    """Read only this bounded synthetic volume; never recurse into other entries."""
    entries = list(volume.iterdir())
    if len(entries) > 16:
        raise ValueError("unexpected synthetic volume inventory")
    result, total = {}, 0
    for entry in sorted(entries):
        if entry.is_file():
            total += entry.stat().st_size
            if total > image.DISK_BYTES:
                raise ValueError("synthetic volume exceeds its byte bound")
            result[entry.name] = hashlib.sha256(entry.read_bytes()).hexdigest()
        else:
            result[entry.name] = "directory-not-traversed"
    return result


class Mount:
    """One new empty NTFS directory bound only to the already owned volume GUID."""

    def __init__(self, api, directory: Path, volume: str):
        self.api, self.volume = api, volume
        self.path = directory / "provider-mount"
        self.parent = self.handle = None
        self.created = self.mounted = False
        self.identity = None
        self.receipt = {"mount_path": str(self.path), "volume_guid": volume, "created": False,
                        "mounted": False, "removed": False, "mapping_removed": False}
        self.functions = {}
        for name, arguments in (
                ("SetVolumeMountPointW", [ct.c_wchar_p, ct.c_wchar_p]),
                ("DeleteVolumeMountPointW", [ct.c_wchar_p]),
                ("GetVolumeNameForVolumeMountPointW", [ct.c_wchar_p, ct.c_wchar_p, ct.c_uint32]),
                ("GetVolumeInformationByHandleW", [ct.c_void_p, ct.c_wchar_p, ct.c_uint32,
                    ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_wchar_p, ct.c_uint32])):
            function = getattr(api.kernel, name)
            function.restype, function.argtypes = ct.c_int, arguments
            self.functions[name] = function

    def open_directory(self, path: Path):
        handle = self.api.CreateFileW(str(path), 0x100081, 3, None, 3, 0x02200000, None)
        if handle in (None, ct.c_void_p(-1).value):
            error = ct.get_last_error()
            if error in (5, 50, 1314):
                raise Unavailable(f"owned NTFS directory capability unavailable: Win32 {error}")
            raise OSError(error, "open owned NTFS directory")
        return handle

    def identity_of(self, handle):
        value = self.api.identity(handle)
        if not value["extended_supported"] or int(value["extended_id"], 16) == 0:
            raise Unavailable("owned NTFS mount directory lacks its live extended identity")
        return value["extended_volume_serial"], value["extended_id"]

    def verify_owned(self) -> dict:
        if self.identity_of(self.handle) != self.identity:
            raise ValueError("held mount directory identity changed")
        named = self.open_directory(self.path)
        try:
            if self.identity_of(named) != self.identity:
                raise ValueError("owned mount directory name changed")
            return self.api.identity(named)
        finally:
            self.api.require(self.api.CloseHandle(named), "close mount-name observation")

    def mapped_volume(self) -> str:
        value = ct.create_unicode_buffer(128)
        self.api.require(self.functions["GetVolumeNameForVolumeMountPointW"](str(self.path) + "\\", value, len(value)),
                         "read owned mount mapping")
        return value.value

    def create(self) -> None:
        image.no_reparse(self.path.parent)
        self.parent = self.open_directory(self.path.parent)
        self.receipt["ntfs_parent_identity"] = self.identity_of(self.parent)
        fs = ct.create_unicode_buffer(32)
        if not self.functions["GetVolumeInformationByHandleW"](self.parent, None, 0, None, None, None, fs, len(fs)):
            error = ct.get_last_error()
            if error in (5, 50, 1314):
                raise Unavailable(f"mount parent filesystem query unavailable: Win32 {error}")
            raise OSError(error, "read mount parent filesystem")
        if fs.value != "NTFS":
            raise Unavailable("private mount parent is not NTFS")
        self.receipt["parent_filesystem"] = fs.value
        self.path.mkdir(exist_ok=False)
        self.created = self.receipt["created"] = True
        self.handle = self.open_directory(self.path)
        self.identity = self.identity_of(self.handle)
        self.receipt["created_directory_identity"] = self.identity
        if self.verify_owned()["attributes"] & 0x400 or list(self.path.iterdir()):
            raise ValueError("new mount directory is not ordinary and empty")
        if not self.functions["SetVolumeMountPointW"](str(self.path) + "\\", self.volume):
            error = ct.get_last_error()
            if error in (5, 50, 1314):
                raise Unavailable(f"existing directory-mount capability unavailable: Win32 {error}")
            raise OSError(error, "mount only the owned recovered volume")
        self.mounted = self.receipt["mounted"] = True
        self.verify()

    def verify(self) -> None:
        mapped = self.mapped_volume()
        if not self.verify_owned()["attributes"] & 0x400 or mapped.lower() != self.volume.lower():
            raise ValueError("private mount does not identify the owned volume")
        self.receipt["mapping_readback"] = mapped

    def probe_root(self, name: str) -> Path:
        return self.path / name

    def close(self, *, remove=True) -> list[str]:
        errors = []
        try:
            if self.created:
                if not remove:
                    raise ValueError("owned mount retained because child termination is unconfirmed")
                if self.handle is None or self.identity is None:
                    raise ValueError("cannot authenticate created mount directory for removal")
                observed = self.verify_owned()
                if observed["attributes"] & 0x400:
                    if self.mapped_volume().lower() != self.volume.lower():
                        raise ValueError("refuse to remove an unowned mount mapping")
                    self.api.require(self.functions["DeleteVolumeMountPointW"](str(self.path) + "\\"), "remove owned mount mapping")
                    if self.verify_owned()["attributes"] & 0x400:
                        raise ValueError("owned mapping remains after removal")
                self.receipt["mapping_removed"] = True
                if list(self.path.iterdir()):
                    raise ValueError("owned mount stub is not empty after unmount")
                self.api.require(self.api.CloseHandle(self.handle), "close owned mount directory")
                self.handle = None
                self.path.rmdir()
                if self.path.exists():
                    raise ValueError("owned mount directory remains")
                self.receipt["removed"] = True
        except Exception as error:
            errors.append(str(error))
        finally:
            for name in ("handle", "parent"):
                handle = getattr(self, name)
                if handle is not None:
                    if not self.api.CloseHandle(handle):
                        errors.append("closing owned " + name + " failed")
                    setattr(self, name, None)
        return errors


def run(executable: Path, env: dict, api, volume: str, directory: Path, validate_volume, recovery: Path) -> dict:
    """Return a separate outcome; always undo our own names before VHD detach."""
    report = {"format": "ifw-owned-fat-provider-v1", "status": "preparing", "cleanup_errors": []}
    mount = None
    probe = None
    created = False
    baseline = None
    quiescent = True
    try:
        report["recovery_receipt_sha256"] = require_recovery(recovery)
        try:
            report["capacity_before"] = validate_volume()
        except Exception as error:
            raise Unavailable("owned recovered volume identity unavailable: " + str(error)) from error
        baseline = volume_files(Path(volume))
        report["volume_files_before"] = baseline
        require_no_mount_paths(api, volume)
        mount = Mount(api, directory, volume)
        mount.create()
        validate_volume()
        nonce = uuid.uuid4().hex
        name = "ifw-provider-" + nonce
        probe = Path(volume) / name
        probe.mkdir(exist_ok=False)
        created = True
        with (probe / "original.txt").open("xb") as stream:
            stream.write(CONTENTS)
            stream.flush()
            os.fsync(stream.fileno())
        mount.verify()
        root = mount.probe_root(name)
        child_env = dict(env, IFW_STORAGE_PROVIDER_ROOT=str(root), IFW_STORAGE_PROVIDER_NONCE=nonce)
        report["child"] = run_child([str(executable), str(root), nonce], child_env, directory)
        report["observation"] = validate_observation(report["child"])
        report["status"] = "passed"
    except Exception as error:
        quiescent = not isinstance(error, ChildNotQuiescent)
        report["status"] = "unavailable" if isinstance(error, Unavailable) else "failed"
        report["error"] = str(error)
    finally:
        try:
            if created:
                if not quiescent:
                    raise ValueError("owned FAT names retained because child termination is unconfirmed")
                validate_volume()
                children = list(probe.iterdir())
                if any(path.name not in ("original.txt", "renamed.txt") or not path.is_file()
                       or path.read_bytes() != CONTENTS for path in children):
                    raise ValueError("refuse cleanup of an unexpected provider entry")
                for path in children:
                    path.unlink()
                probe.rmdir()
                report["probe_removed"] = not probe.exists()
                if not report["probe_removed"]:
                    raise ValueError("provider directory remains")
        except Exception as error:
            report["cleanup_errors"].append("owned FAT names: " + str(error))
        if mount is not None:
            try:
                report["cleanup_errors"].extend(mount.close() if quiescent else mount.close(remove=False))
            except Exception as error:
                report["cleanup_errors"].append("owned mount cleanup: " + str(error))
            report["mount"] = mount.receipt
        try:
            if baseline is not None:
                require_no_mount_paths(api, volume)
                report["volume_mount_paths_empty"] = True
                report["capacity_after"] = validate_volume()
                report["volume_files_after"] = volume_files(Path(volume))
                if report["volume_files_after"] != baseline or report["capacity_after"] != report["capacity_before"]:
                    raise ValueError("recovered volume files or capacity changed after provider cleanup")
        except Exception as error:
            report["cleanup_errors"].append("recovered volume readback: " + str(error))
        if report["cleanup_errors"]:
            report["status"] = "failed"
    return report
