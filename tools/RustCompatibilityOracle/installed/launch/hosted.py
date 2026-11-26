"""Stage signed release and graphics inputs for the offline native Flatpak launch trial."""

from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def prepare(hosted_platform):
    sys.path.insert(0, str(ROOT / 'tools/rust-qa/portal-dialog'))
    from graphics import graphics_deployment, hosted_work, pinned_extension
    from hosted_runtime import install_signed_ref
    from run import COMMITS, SIGNATURES

    work = hosted_work(hosted_platform)
    pin = pinned_extension()
    install_signed_ref(work, pin['ref'], pin['commit'], 'graphics-signature.txt', 'verified-graphics.json')
    graphics, _ = graphics_deployment(hosted_platform)

    arch = platform.machine()
    target = {'aarch64': 'linux-arm64', 'x86_64': 'linux-x64'}[arch]
    installer = runpy.run_path(str(HERE.parent / 'run.py'))
    if installer['native_target']() != target:
        raise ValueError('The release asset must match the native Linux host')
    art = ROOT / 'artifacts/rust'
    packages = art / 'legacy-installer-inputs/v3.0.4'
    packages.mkdir(parents=True, exist_ok=True)
    signed = art / 'shipping-flatpak-launch/signature'
    signed.mkdir(parents=True, exist_ok=True)
    name = '3.0.4-arm64.commitmeta' if arch == 'aarch64' else '3.0.4.commitmeta'
    commit = COMMITS[arch]
    url = f'https://voltkraft.github.io/immich-folder-watch/repo/objects/{commit[:2]}/{commit[2:]}.commitmeta'
    with tempfile.TemporaryDirectory(prefix='shipping-', dir=packages) as directory:
        stage = Path(directory)
        package = installer['prepare_package'](target, stage, None)
        metadata = stage / name
        subprocess.run(['curl', '--disable', '--fail', '--silent', '--show-error', '--location',
                        '--proto', '=https', '--proto-redir', '=https', '--max-time', '45', '--max-filesize', '65536',
                        '--output', str(metadata), url], check=True)
        if sha256(metadata.read_bytes()).hexdigest() != SIGNATURES[arch]:
            raise ValueError('Detached signature metadata differs from the original release')
        # The clean hosted checkout supplies these two inputs to the subsequent offline trial.
        metadata.replace(signed / name)
        package.replace(packages / package.name)
    evidence = signed.parent / 'hosted-inputs'
    evidence.mkdir()
    for filename in ('signature.txt', 'verified.json', 'graphics-signature.txt', 'verified-graphics.json'):
        shutil.copyfile(work / filename, evidence / filename)
    shutil.copyfile(hosted_platform / 'metadata', evidence / 'platform.metadata')
    shutil.copyfile(graphics / 'metadata', evidence / 'graphics.metadata')
    shutil.copyfile(signed / name, evidence / name)
    for source in (Path(__file__), HERE / 'run.py', HERE / 'graphics.py', HERE.parent / 'run.py',
                   HERE.parent / 'release.json', ROOT / 'tools/rust-qa/portal-dialog/hosted_runtime.py',
                   ROOT / 'tools/rust-qa/portal-dialog/runtime_pin.py', ROOT / '.github/workflows/rust-legacy-install.yaml'):
        copy = evidence / 'source' / source.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, copy)
    receipt = {'target': target, 'revision': os.environ['GITHUB_SHA'], 'run': os.environ['GITHUB_RUN_ID'],
               'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'asset': installer['RELEASE']['assets'][target],
               'commit': commit, 'signatureUrl': url,
               'files': {p.relative_to(evidence).as_posix(): sha256(p.read_bytes()).hexdigest()
                         for p in sorted(evidence.rglob('*')) if p.is_file()}}
    (evidence / 'inputs.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Pass the native hosted Platform deployment')
    prepare(Path(sys.argv[1]))
