"""Boot the pinned Noble cloud image with a private overlay, read-only inputs and no network."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
AREA = ROOT / "artifacts/rust/portal-noble/installed"
IMAGE = AREA / "images/noble-amd64.qcow2"
IMAGE_SHA = "04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94"
IMAGE_SIGNER = "D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def authenticate_image():
    sums = IMAGE.parent / "SHA256SUMS"
    signature = sums.with_suffix(".gpg")
    keyring = ROOT / "artifacts/rust/gui-noble-native/root/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg"
    verification = subprocess.check_output(["gpgv", "--keyring", keyring, "--status-fd", "1", signature, sums],
                                           text=True)
    published = re.findall(r"^([a-f0-9]{64}) [ *]noble-server-cloudimg-amd64\.img$", sums.read_text(), re.MULTILINE)
    if (f"[GNUPG:] VALIDSIG {IMAGE_SIGNER} " not in verification or published != [IMAGE_SHA]
            or IMAGE.is_symlink() or IMAGE.stat().st_size != 621284352 or sha(IMAGE) != IMAGE_SHA):
        raise ValueError("The Noble base image differs from the signed Canonical release")
    return {"sha256": sha(sums), "signatureSha256": sha(signature), "fingerprint": IMAGE_SIGNER}


def run(stage, payload):
    if platform.machine() != "x86_64" or not Path("/dev/kvm").is_char_device():
        raise RuntimeError("Use the native x64 KVM test host")
    release = authenticate_image()
    area = Path(tempfile.mkdtemp(prefix=stage + "-", dir=AREA))
    print(area, flush=True)
    serial = uuid.uuid4().hex
    seed = area / "seed"
    seed.mkdir()
    (seed / "meta-data").write_text(f"instance-id: iid-{serial}\nlocal-hostname: ifw-portal-qa\n")
    (seed / "network-config").write_text("version: 2\nethernets: {}\n")
    (seed / "trial-id").write_text(serial + "\n")
    (seed / "user-data").write_text("""#cloud-config
users: []
ssh_pwauth: false
runcmd:
  - [ mkdir, -p, /mnt/ifw ]
  - [ mount, -o, ro, LABEL=cidata, /mnt/ifw ]
  - [ bash, /mnt/ifw/run.sh ]
power_state:
  mode: poweroff
  delay: now
  timeout: 60
""")
    shutil.copyfile(HERE / "guest.sh", seed / "run.sh")
    (seed / "stage").write_text(stage + "\n")
    iso = area / "inputs.iso"
    iso_cmd = ["xorriso", "-as", "mkisofs", "-quiet", "-V", "cidata", "-J", "-r", "-o", iso,
               "-graft-points", f"/={seed}"]
    if payload:
        iso_cmd.append(f"/payload={payload}")
    subprocess.run(iso_cmd, check=True)
    disk = area / "root.qcow2"
    evidence = area / "evidence.ext4"
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", IMAGE, disk, "20G"], check=True)
    with evidence.open("xb") as stream:
        stream.truncate(1024**3)
    subprocess.run(["mkfs.ext4", "-q", "-L", "IFWRESULT", evidence], check=True)
    with (area / "console.log").open("wb") as console:
        subprocess.run(["qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host", "-m", "4096",
                        "-smp", "4", "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
                        "-no-reboot", "-smbios", "type=1,product=IFW-Noble-Portal-QA,serial=" + serial,
                        "-drive", f"file={disk},format=qcow2,if=virtio", "-cdrom", iso,
                        "-drive", f"file={evidence},format=raw,if=virtio"], check=True,
                       stdin=subprocess.DEVNULL, stdout=console, stderr=subprocess.STDOUT, timeout=2400)
    # Read the guest file system offline. Only export fixed, regular outputs.
    names = ["exit", "guest.log", "dpkg-status", "boot-id", "arch", "trial-id"]
    trial_files = {"inventory": [], "package": ["candidate.deb", "build.log", "package-result.json", "build-evidence.tar"],
                   "lease-stock": ["stock.json", "lease-result.json"],
                   "lease": ["stock.json", "candidate.json", "restored.json", "lease-result.json"]}
    exported = []
    for name in names + trial_files[stage]:
        subprocess.run(["debugfs", "-R", f"dump /{name} {name}", evidence], cwd=area, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if (area / name).is_file():
            exported.append(name)
        elif name in names:
            raise RuntimeError(f"Missing guest {name}. See {area / 'console.log'}")
    if (area / "trial-id").read_text().strip() != serial or (area / "arch").read_text().strip() != "amd64":
        raise ValueError("Guest identity or architecture differs from the requested native trial")
    receipt = dict(stage=stage, image=IMAGE_SHA, imageRelease=release, seed=sha(iso), trial=serial,
                   outputs={name: sha(area/name) for name in exported})
    (area / "vm.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if (area / "exit").read_text().strip() != "0":
        raise RuntimeError(f"The guest trial failed. See {area / 'guest.log'}")
    if set(trial_files[stage]) - set(exported):
        raise RuntimeError(f"The guest exited successfully with missing {stage} evidence")
    if stage == "package":
        package = json.loads((area / "package-result.json").read_text())
        if (package["status"] != "native-packages-built" or package["architecture"] != "amd64"
                or package["packages"]["xdg-desktop-portal"]["sha256"] != sha(area / "candidate.deb")):
            raise RuntimeError("The exported binary differs from the guest build record")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["inventory", "package", "lease-stock", "lease"])
    parser.add_argument("--payload", type=Path)
    args = parser.parse_args()
    if (args.stage != "inventory") != bool(args.payload):
        parser.error("Both package and lease trials need a prepared payload")
    run(args.stage, args.payload.resolve(strict=True) if args.payload else None)
