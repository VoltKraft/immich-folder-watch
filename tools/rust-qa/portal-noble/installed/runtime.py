"""Export the signed freedesktop test runtime for the offline guest."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from vm import AREA, HERE, sha
sys.path.insert(0, str(HERE.parents[1] / "portal-dialog"))
from runtime_pin import BRANCH, COMMITS, PLATFORM


def export():
    ref = f"runtime/{PLATFORM}/x86_64/{BRANCH}"
    pinned = COMMITS["x86_64"]
    # This is the system's public runtime repository. All writes target the new test directory.
    installed = Path("/var/lib/flatpak/repo")
    work = Path(tempfile.mkdtemp(prefix="runtime-", dir=AREA))
    print(work, flush=True)
    repo = work / "repo"
    env = {"PATH": os.defpath + ":/usr/bin", "HOME": str(work), "LC_ALL": "C", "XDG_CACHE_HOME": str(work / "cache")}
    def ostree(*args):
        return subprocess.check_output(["ostree", "--repo=" + str(repo), *args], env=env, text=True)
    ostree("init", "--mode=bare-user-only")
    ostree("remote", "add", "--gpg-import=" + str(installed / "flathub.trustedkeys.gpg"),
           "--set=gpg-verify=true", "--set=gpg-verify-summary=true", "flathub", "https://dl.flathub.org/repo/")
    ostree("pull", "--disable-static-deltas", "--localcache-repo=" + str(installed), "flathub", ref + "@" + pinned)
    if ostree("rev-parse", "flathub:" + ref).strip() != pinned:
        raise RuntimeError("Flathub's original runtime commit differs from the reviewed pin")
    signature = ostree("show", "--gpg-verify-remote=flathub", pinned)
    if "Good signature from " not in signature:
        raise RuntimeError("The original runtime signature did not verify")
    ostree("refs", "--create=" + ref, pinned)
    bundle = work / "platform.flatpak"
    subprocess.run(["flatpak", "build-bundle", "--runtime", "--arch=x86_64", repo, bundle, PLATFORM, BRANCH],
                   env=env, check=True)
    (work / "signature.txt").write_text(signature)
    (work / "runtime.json").write_text(json.dumps(dict(ref=ref, commit=pinned, sha256=sha(bundle)), indent=2) + "\n")


if __name__ == "__main__":
    export()
