"""Stage the original Plasma pair and reproduce its missing Vulkan counter for the native budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[2]
ART = ROOT / 'artifacts/rust'
SOURCE = '9487dbe51a55da56f71e59611bb1e78a501e371f'
# The original archive endpoint returns the uploaded ZIP unchanged.
ARCHIVES = {
    'x86_64-unknown-linux-gnu': (15251410283, '34f94681826182e1656b614b99abfaad01c61d6821867eb54e019be514c692cd'),
    'aarch64-unknown-linux-gnu': (15251093019, 'd508aa5b89f6acc1091e7947bf144593dc0ca2880e99a7a12abba237c557cd2c'),
}
INPUTS = ['rust/assets/fonts', 'rust/audit', 'rust/toolchain-inputs.json', 'rust/crates/desktop-lifecycle', 'rust/crates/safe-fs',
          'rust/Cargo.toml', 'tools/rust-qa/gui/Cargo.toml', 'tools/rust-qa/gui/Cargo.lock', 'tools/rust-qa/gui/src',
          'tools/rust-qa/gui/build.py', 'tools/rust-qa/gui/source_profile.py', 'tools/rust-qa/performance/worker',
          'tools/rust-qa/performance/present.rs', 'tools/rust-qa/performance/build_worker.py', 'tools/rust-qa/yaml/inputs.json']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(artifact, target, checksum, archive):
    url = f'repos/VoltKraft/immich-folder-watch/actions/artifacts/{artifact}'
    result = subprocess.run(['gh', 'api', url], capture_output=True)
    if result.returncode and b'HTTP 404' in result.stderr:
        return False
    result.check_returncode()
    receipt = json.loads(result.stdout)
    if receipt['expired']:
        return False
    if (receipt['digest'] != 'sha256:' + checksum or receipt['id'] != artifact or receipt['workflow_run']['id'] != 46114279356
            or receipt['workflow_run']['head_sha'] != SOURCE or receipt['name'] != f'rust-plasma-{target}-{SOURCE}'):
        raise ValueError('Original Plasma Actions metadata differs')
    # Current gh requires explicit permission to preserve control bytes in raw binary output.
    optional = ['--allow-escape-sequences'] if b'--allow-escape-sequences' in subprocess.check_output(['gh', 'api', '--help']) else []
    with archive.open('xb') as output:
        subprocess.run(['gh', 'api', *optional, url + '/zip'], stdout=output, check=True)
    return True


def stage(archive, checksum, target, output):
    if sha(archive) != checksum:
        raise ValueError('Original Actions ZIP digest differs')
    with ZipFile(archive) as z:
        base = 'performance/subjects/plasma-native/'
        gui = json.loads(z.read(base + 'native-gui-assessment.inputs.json'))
        pair = json.loads(z.read(base + 'worker.inputs.json'))
        build = json.loads(z.read(f'gui-native/{target}/build.json'))
        if (build['source'] != SOURCE or build['target'] != target or gui['target'] != target
                or not build['binarySha256'] == pair['gui_sha256'] == gui['binary_sha256']):
            raise ValueError('Original GUI and worker compiler receipts disagree')
        for sources in (gui['sources'], pair['sources'], build['compilerSources']):
            for path, digest in sources.items():
                if sha(ROOT / path) != digest:
                    raise ValueError('Current compiler input differs from original receipt: ' + path)
        for name, expected in [('native-gui-assessment', gui['binary_sha256']), ('ifw-performance-worker', pair['worker_sha256'])]:
            data = z.read(base + name)
            machine = {'x86_64-unknown-linux-gnu': 62, 'aarch64-unknown-linux-gnu': 183}[target]
            if (hashlib.sha256(data).hexdigest() != expected or data[:7] != b'\x7fELF\x02\x01\x01'
                    or int.from_bytes(data[18:20], 'little') != machine):
                raise ValueError('Original executable digest or ELF machine differs: ' + name)
            (output / name).write_bytes(data)
            (output / name).chmod(0o755)
        for name in ('native-gui-assessment.inputs.json', 'worker.inputs.json'):
            (output / name).write_bytes(z.read(base + name))
    return pair['observer_sha256']


def observer(output, expected):
    # Re-run the same rustc command and source location used in build_worker.py. The original
    # native receipt pins the output too, so a different build can never silently enter this pair.
    directory = output / 'observer'
    directory.mkdir()
    counter = directory / 'libvulkan.so.1'
    subprocess.run([ART / 'toolchain/bin/rustc', '--edition', '2024', '--crate-type', 'cdylib', '-O', '-D', 'warnings',
                    '-Clink-arg=-Wl,-z,nodelete', '-Clink-arg=-Wl,-soname,libvulkan.so.1', '../present.rs', '-o', counter],
                   cwd=HERE / 'worker', check=True)
    return sha(counter) == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=ARCHIVES)
    args = parser.parse_args()
    if args.target != platform.machine() + '-unknown-linux-gnu':
        parser.error('Use the matching native runner')
    area = ART / 'performance'
    area.mkdir(parents=True, exist_ok=True)
    output = area / 'subjects/budget-native'
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact, checksum = ARCHIVES[args.target]
    source = subprocess.run(['git', 'diff', '--quiet', SOURCE, 'HEAD', '--', *INPUTS], cwd=ROOT)
    if source.returncode not in (0, 1):
        source.check_returncode()
    origin = 'rebuild'
    revision = os.environ['GITHUB_SHA']
    with tempfile.TemporaryDirectory(dir=area) as tmp:
        archive = Path(tmp) / 'plasma.zip'
        if source.returncode == 0 and download(artifact, args.target, checksum, archive):
            subject = Path(tmp) / 'subject'
            subject.mkdir()
            expected = stage(archive, checksum, args.target, subject)
            if observer(subject, expected):
                subject.rename(output)
                origin, revision = 'original-archive', SOURCE
            else:
                print('The local frame counter differs from the older compiler receipt; building a fresh complete pair.')
    provenance = {'mode': origin, 'target': args.target, 'measurementRevision': os.environ['GITHUB_SHA'], 'sourceRevision': revision}
    if origin == 'original-archive':
        provenance.update(artifactId=artifact, archiveSha256=checksum, runId=46114279356, frameCounterSha256=expected)
    (area / 'budget-input.json').write_text(json.dumps(provenance, indent=2) + '\n')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        print('mode=' + origin, 'revision=' + revision, sep='\n', file=stream)


if __name__ == '__main__':
    main()
