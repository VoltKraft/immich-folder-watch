"""Observe the real Ubuntu Meson launcher, its interpreter and the selected package in the compiler namespace."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def file_identity(path):
    value = Path(path)
    with value.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(value), "resolved": str(value.resolve(strict=True)), "sha256": digest}


def observe():
    from mesonbuild import coredata, mesonmain

    base = Path("/usr/lib/python3/dist-packages/mesonbuild")
    if (sys.prefix, sys.exec_prefix) != ("/usr", "/usr") or not sys.flags.no_user_site:
        raise ValueError("The Ubuntu compiler interpreter did not select the merged /usr prefix")
    if Path(mesonmain.__file__) != base / "mesonmain.py" or Path(coredata.__file__) != base / "coredata.py":
        raise ValueError("Meson imported modules outside the Ubuntu distribution package")
    cli = subprocess.check_output(["/usr/bin/meson", "--version"], text=True, timeout=15).strip()
    if cli != coredata.version:
        raise ValueError("Meson's executable and imported module disagree about their version")
    files = {k: file_identity(v) for k, v in (("python", sys.executable), ("launcher", "/usr/bin/meson"),
                                               ("module", mesonmain.__file__), ("core", coredata.__file__))}
    executable = os.readlink("/proc/self/exe")
    if files["python"]["resolved"] != executable:
        raise ValueError("The reported Ubuntu Python differs from the running executable")
    return dict(prefix=sys.prefix, execPrefix=sys.exec_prefix, pythonVersion=sys.version,
                executable=executable, searchPath=sys.path, mesonVersion=cli, files=files)


if __name__ == "__main__":
    print(json.dumps(observe(), indent=2))
