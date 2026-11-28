"""Start one memory-limited local Windows test guest, including daemonized QEMU."""
import fcntl
import os
from pathlib import Path
import re
import subprocess


MAX_MIB = 3072
SLOT = Path.home() / ".local/share/ifw-qa/server2025-x64/guest-slot.lock"


def validate(args):
    if not args or Path(args[0]).name != "qemu-system-x86_64":
        raise ValueError("Expected the local Windows x64 QEMU launcher")
    if args.count("-m") != 1:
        raise ValueError("Expected exactly one explicit -m with a fixed RAM size")
    index = args.index("-m") + 1
    size = re.fullmatch(r"([1-9][0-9]*)([MG]?)", args[index]) if index < len(args) else None
    if not size or int(size[1]) * (1024 if size[2] == "G" else 1) > MAX_MIB:
        raise ValueError(f"The local Windows guest requires a fixed -m of at most {MAX_MIB} MiB")

    # These local launchers configure one RAM bank from the command line. Leave
    # ordinary display, storage, CPU and network arguments to QEMU.
    for i, arg in enumerate(args[1:], 1):
        if not arg.startswith("-"):
            continue
        option = "-" + arg.lstrip("-")
        value = args[i + 1] if i + 1 < len(args) else ""
        if arg == "--m" or option in {"-readconfig", "-mem-path", "-mem-prealloc"}:
            raise ValueError(f"Separate RAM configuration is unavailable with {arg}")
        if option in {"-machine", "-M", "-object", "-device", "-numa", "-global", "-set"}:
            if re.search(r'\b(memory-backend|memdev|pc-dimm|nvdimm|virtio-mem|virtio-pmem|'
                         r'ivshmem|cxl-type3|sgx-epc|memory\.(size|max-size|slots))\b', value):
                raise ValueError(f"Separate guest RAM settings in {arg}")
            if re.search(r'(?:^|[,\s{"])(?:memory|mem|slots|maxmem)"?\s*[:=]', value):
                raise ValueError(f"Separate guest RAM settings in {arg}")
        if option == "-add-fd" and re.search(r'(?:^|,)set=0(?:,|$)', value):
            raise ValueError("QEMU FD set 0 is reserved for the local guest slot")


def _run(qemu_args, *, cwd, check, slot):
    args = [os.fspath(value) for value in qemu_args]
    validate(args)
    # Keep one stable inode in the private VM directory across all starts. QEMU
    # duplicates this locked open file description in its fd set before daemonizing.
    fd = os.open(slot, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another local Windows test guest holds the VM slot") from exc
        return subprocess.run([*args, "-add-fd", f"fd={fd},set=0,opaque=ifw-guest-slot"],
                              cwd=cwd, check=check, pass_fds=(fd,))
    finally:
        # LOCK_UN would unlock the daemon's copy too. Closing only the launcher's
        # descriptor lets the kernel release the slot when the final owner exits.
        os.close(fd)


def run(qemu_args, *, cwd, check=True):
    """Run QEMU under the shared per-user guest slot, preserving subprocess.run's result."""
    return _run(qemu_args, cwd=cwd, check=check, slot=SLOT)
