"""Verify reused native dependency inputs and build the isolated application offline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tomllib
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / 'artifacts/rust'
OUT = ART / 'portal-dialog'


def digest(path):
    with path.open('rb') as data:
        return hashlib.file_digest(data, 'sha256').hexdigest()


def checked_dependencies(path):
    return {(p['name'],
        p['version']): p['checksum'] for p in tomllib.loads(path.read_text())['package'] if 'source' in p}


def build(mode, jobs):
    target = f'{platform.machine()}-unknown-linux-gnu'
    toolchain = ART / 'toolchain'
    info = subprocess.check_output([sys.executable, ROOT / 'tools/rust-qa/check-toolchain.py', target, '--rustc',
        toolchain / 'bin/rustc'], text=True)
    sys.path.insert(0, str(ROOT / 'tools/rust-qa/linux-services'))
    from native import checked_sources, gui_reference
    graph = checked_dependencies(HERE / 'Cargo.lock')
    existing = checked_dependencies(gui_reference() / 'Cargo.lock')
    if any((existing.get(p) != sha for p, sha in graph.items())):
        raise ValueError('A locked archive is absent from the reviewed GUI graph')
    output = OUT / 'build'
    output.mkdir(parents=True, exist_ok=True)
    cmd = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv', '--ro-bind', '/usr',
        '/usr', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/home/fixture', '--dir', '/cargo',
        '--ro-bind', str(ART / 'assessment-cache/registry'), '/cargo/registry', '--ro-bind', str(toolchain),
        '/toolchain', '--ro-bind', str(HERE), '/project/tools/rust-qa/portal-dialog', '--ro-bind',
        str(ROOT / 'tools/rust-qa/gui'), '/project/tools/rust-qa/gui', '--ro-bind', str(ROOT / 'rust'),
        '/project/rust', '--bind', str(output), '/build']
    for name in ('bin', 'lib', 'lib64'):
        path = Path('/') / name
        if path.is_symlink():
            cmd += ['--symlink', str(path.readlink()), str(path)]
        elif path.is_dir():
            cmd += ['--ro-bind', str(path), str(path)]
    for path in ('/etc/alternatives', '/etc/ld.so.cache'):
        if Path(path).exists():
            cmd += ['--ro-bind', path, path]
    cmd += ['--setenv', 'PATH', '/toolchain/bin:/usr/bin', '--setenv', 'HOME', '/home/fixture', '--setenv',
        'CARGO_HOME', '/cargo', '--setenv', 'CARGO_TARGET_DIR', '/build', '--chdir',
        '/project/tools/rust-qa/portal-dialog', '--', '/toolchain/bin/cargo']
    records = checked_sources(cmd, target, graph)
    flags = [mode, '--frozen', '--jobs', str(jobs)]
    if mode == 'clippy':
        flags += ['--all-targets', '--', '-D', 'warnings']
    elif mode == 'build':
        flags += ['--release']
    subprocess.run([*cmd, *flags], check=True)
    if mode != 'build':
        return
    safe = ROOT / 'rust/crates/safe-fs'
    src = [HERE / 'Cargo.toml', HERE / 'Cargo.lock', HERE / 'build.py', *sorted((HERE / 'src').glob('*.rs')),
        safe / 'Cargo.toml', *sorted((safe / 'src').rglob('*.rs'))]
    report = {'compiler': info, 'locked_archives': len(graph), 'active_registry_inputs': records,
        'sources': {str(p.relative_to(ROOT)): digest(p) for p in src},
        'binary': digest(output / 'release/portal-dialog-assessment')}
    (OUT / 'build-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--fetch', dest='mode', action='store_const', const='fetch')
    modes.add_argument('--lint', dest='mode', action='store_const', const='clippy')
    modes.add_argument('--test', dest='mode', action='store_const', const='test')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.mode == 'fetch':
        sys.path.insert(0, str(HERE.parent))
        from gui import source_profile
        env = dict(os.environ, CARGO_HOME=str(ART / 'assessment-cache'))
        source_profile.CACHE.mkdir(parents=True, exist_ok=True)
        source_profile.fetch_replay_registry(env)
        subprocess.run(['cargo', 'fetch', '--locked', '--manifest-path', str(HERE / 'Cargo.toml')], env=env, check=True)
    else:
        build(args.mode or 'build', args.jobs)
