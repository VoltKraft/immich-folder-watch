"""Compare both combined winit import archives and notices to the pinned Microsoft revision."""
import hashlib
import tarfile

from sources import read, sha256

REVISION = "db06b51c2ebb743efb544d40e3064efa49f28d38"
ARCHIVES = ("x86_64_msvc", "aarch64_msvc")


def compare(upstream, vendor):
    archive_digest = sha256(upstream)
    if archive_digest != "892494b5b1e5f1f63b9cd229074c048f184b33c07d5dda87f015308261e44329":
        raise ValueError("Wrong source archive for the Microsoft import comparison")
    expected = {}
    for architecture in ARCHIVES:
        package = vendor / f"windows_{architecture}-0.52.6"
        vcs = read(package / ".cargo_vcs_info.json")
        if vcs != {"git": {"sha1": REVISION}, "path_in_vcs": f"crates/targets/{architecture}"}:
            raise ValueError(f"Unexpected source revision for {architecture}")
        for relative in ("lib/windows.0.52.0.lib", "license-mit", "license-apache-2.0"):
            name = f"crates/targets/{architecture}/{relative}" if relative.startswith("lib/") else relative
            digest = sha256(package / relative)
            if expected.setdefault(name, digest) != digest:
                raise ValueError("Microsoft package notices disagree")
    observed = {}
    with tarfile.open(upstream, "r|gz") as source:
        for member in source:
            prefix = "windows-rs-" + REVISION + "/"
            if not member.name.startswith(prefix):
                continue
            relative = member.name[len(prefix):]
            if relative in expected:
                if not member.isfile() or member.size > 8 * 1024 * 1024 or relative in observed:
                    raise ValueError("Unexpected upstream import or license member")
                with source.extractfile(member) as stream:
                    observed[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    if observed != expected:
        raise ValueError("Original Microsoft import bytes or notices differ from the combined inputs")
    return {"revision": REVISION, "sourceTarSha256": archive_digest, "upstreamMatches": observed}
