"""Locate the signed Flatpak GL extension used by the native shipping launch trial."""

from hashlib import sha256
import json
from pathlib import Path
import platform
import sys

GL = 'org.freedesktop.Platform.GL.default'
PINS = {
    'x86_64': ('5aec1b8281d53c91bdac451eb577ec5331ca0e34d89cf0dcc8dba2360171eae6',
               '8802a8c0a93df4c521a62b9be924574c2c40bc8c03e48075387c795d308d781b'),
    'aarch64': ('ab6ebce8bf5a62d9393fca493a08c45fe669a8f73527bccec6ad3dbf62748b41',
                '8cf48fb1d21752b9f8a16fb6639b1c5db5788059573ee6753718f5aaaa16e0f4'),
}


def pinned_extension():
    from runtime_pin import BRANCH

    arch = platform.machine()
    commit, metadata = PINS[arch]
    return {'ref': f'runtime/{GL}/{arch}/{BRANCH}', 'commit': commit, 'metadata_sha256': metadata}


def hosted_work(hosted_platform):
    from runtime_pin import deployment, runner_temp

    # Resolve through the Platform validator before accessing its sibling deployment.
    path, _ = deployment(hosted_platform)
    temp = runner_temp()
    return temp / path.relative_to(temp).parts[0]


def graphics_deployment(hosted_platform):
    """Return the native deployment and its verified metadata for the offline namespace."""
    pin = pinned_extension()
    work = hosted_work(hosted_platform) if hosted_platform is not None else None
    installation = work / 'flatpak' if work else Path('/var/lib/flatpak')
    path = installation / pin['ref'] / pin['commit']
    metadata = path / 'metadata'
    files = path / 'files'
    if (path.resolve(strict=True) != path or files.is_symlink() or not files.is_dir()
            or metadata.is_symlink() or not metadata.is_file()
            or sha256(metadata.read_bytes()).hexdigest() != pin['metadata_sha256']):
        raise ValueError('The native Flatpak GL deployment differs from its source pins')
    if work:
        receipt = json.loads((work / 'verified-graphics.json').read_bytes())
        signature = (work / 'graphics-signature.txt').read_bytes()
        if (any(receipt[key] != expected for key, expected in pin.items())
                or receipt['gpg_verify'] is not True or receipt['gpg_verify_summary'] is not True
                or receipt['signature_sha256'] != sha256(signature).hexdigest()):
            raise ValueError('The private GL deployment differs from its Flathub signature receipt')
        return path, {**pin, 'acquisition': receipt}
    return path, pin


def install_hosted_graphics(hosted_platform):
    """Install the signed native GL extension alongside its verified Platform."""
    from hosted_runtime import install_signed_ref

    work = hosted_work(hosted_platform)
    pin = pinned_extension()
    install_signed_ref(work, pin['ref'], pin['commit'], 'graphics-signature.txt', 'verified-graphics.json')
    return graphics_deployment(hosted_platform)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Pass the native hosted Platform deployment')
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'tools/rust-qa/portal-dialog'))
    install_hosted_graphics(Path(sys.argv[1]))
