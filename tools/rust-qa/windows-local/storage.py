"""Run a native storage compiler archive and the shipping C# store on the local Windows x64 guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

QA = Path(__file__).resolve().parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA / 'storage'))
sys.path.insert(0, str(QA))
from evidence import relative_member, sha256, verify_fixture, write_json
from realtime.guest import verify_host, verify_sources

TARGET = 'x86_64-pc-windows-msvc'
EXE = 'ifw-sqlite-assessment.exe'
DLL = 'dotnet/StorageReadback.dll'
DOTNET = '21a46f1e5235cf4e844b9de5429f0e198b9c97a41f0503a66442f1d639ca3ee6'


def unpack(archive, expected, revision, fixtures, scratch):
    inputs = json.loads((QA / 'storage/inputs.json').read_bytes())
    with archive.open('rb') as original:
        if not re.fullmatch('[0-9a-f]{64}', expected) or hashlib.file_digest(original, 'sha256').hexdigest() != expected:
            raise ValueError('The compiler archive differs from the original Actions digest')
        with ZipFile(original) as kit:
            index = json.loads(kit.read('storage-build.json'))
            files = index['files']
            names = [i.filename for i in kit.infolist() if not i.is_dir()]
            if (index['revision'] != revision or index['target'] != TARGET or not index['compilerRun'].isdecimal()
                    or index['fixtureManifestSha256'] != sha256(fixtures / 'manifest.json')
                    or index['lockSha256'] != sha256(QA / 'storage/Cargo.lock')
                    or sorted(names) != sorted([*files, 'storage-build.json'])
                    or files[EXE] != index['rustExecutableSha256'] or files[DLL] != index['csharpAssemblySha256']):
                raise ValueError('Native compiler or test corpus identity differs')
            for name, checksum in files.items():
                path = scratch / relative_member(name)
                if (path == scratch or not path.resolve().is_relative_to(scratch)
                        or name != EXE and not name.startswith(('compiler/', 'dotnet/'))):
                    raise ValueError('Unexpected native compiler output')
                path.parent.mkdir(parents=True, exist_ok=True)
                with kit.open(name) as src, path.open('xb') as dest:
                    shutil.copyfileobj(src, dest)
                if sha256(path) != checksum:
                    raise ValueError('Compiler member digest mismatch: ' + name)
            verify_sources(ROOT, json.loads(kit.read('compiler/first-party-source-hashes.json')))
            if json.loads(kit.read('compiler/native-graph.json')) != inputs['target_graphs'][TARGET]:
                raise ValueError('The Windows compiler graph differs from the selected profile')
    return index, inputs


def native_results(databases, inputs):
    rust = json.loads((databases / 'result.json').read_bytes())
    csharp = json.loads((databases / 'csharp-readback.json').read_bytes())
    journal = rust['FinalizedRollbackJournal']
    actual = {p.name: sha256(p) for p in (databases / 'newer-with-finalized-journal').iterdir() if p.is_file()}
    if (actual.keys() != {'state.db', 'state.db-journal'} or journal['RejectedVersion'] != 99
            or journal['SourceBefore'] != actual or journal['SourceAfter'] != actual):
        raise ValueError('The refused schema or finalized rollback journal bytes differ')
    expected = [{'Case': name, 'Version': version, 'Value': version} for name, version in
                [('newer-with-index', 99), ('newer-without-index', 99), ('supported-without-index', 1)]]
    if (rust['Os'] != 'windows' or rust['Arch'] != 'x86_64' or rust['SQLiteSourceId'] != inputs['sqlite']['source_id']
            or csharp['OperatingSystem'] != 'windows' or csharp['Runtime'] != '10.0.12' or csharp['Assertions'] != 40
            or (csharp['OSArchitecture'], csharp['Architecture']) != ('X64', 'X64') or csharp['QuiescentWalPreflight'] != expected):
        raise ValueError('The guest did not return the native Rust and 40 C# comparisons including WAL readback')
    return rust, csharp


def run(archive, expected, output, dotnet):
    if os.environ.get('GITHUB_ACTIONS') or platform.node().casefold() != 'ifw-qa25':
        raise ValueError('Use the disposable local Windows x64 VM')
    verify_host()
    if output == ROOT / 'artifacts/rust' or not output.is_relative_to(ROOT / 'artifacts/rust'):
        raise ValueError('Choose a new local output below checkout artifacts/rust')
    if dotnet.name.lower() != 'dotnet.exe' or sha256(dotnet) != DOTNET:
        raise ValueError('The explicit runtime is not the reviewed 10.0.12 win-x64 host')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    fixtures = ROOT / 'rust/tests/fixtures/legacy/windows'
    verify_fixture(fixtures, 'windows')
    output.mkdir(parents=True, exist_ok=False)
    databases = output / 'databases'
    with TemporaryDirectory(dir=output) as tmp:
        area = Path(tmp)
        build, inputs = unpack(archive, expected, revision, fixtures, area)
        machine = runpy.run_path(str(QA / 'windows-performance/build.py'))['pe_machine']
        if machine(area / EXE) != 0x8664 or machine(dotnet) != 0x8664:
            raise ValueError('Both programs require native AMD64 PE images')
        env = {k: v for k, v in os.environ.items() if k.upper() in
               {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PROCESSOR_ARCHITECTURE'}}
        env.update(PATH=str(dotnet.parent) + os.pathsep + str(Path(env['SYSTEMROOT']) / 'System32'),
                   TEMP=tmp, TMP=tmp, DOTNET_ROOT=str(dotnet.parent), DOTNET_MULTILEVEL_LOOKUP='0',
                   DOTNET_CLI_HOME=tmp, DOTNET_CLI_TELEMETRY_OPTOUT='1', IFW_ORACLE_EXPECT_ARCH='x64')
        for label, command in [('rust', [area / EXE, fixtures, databases]), ('csharp', [dotnet, area / DLL, databases])]:
            with (output / (label + '.log')).open('xb') as log:
                subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    rust, csharp = native_results(databases, inputs)
    verify_fixture(fixtures, 'windows')
    write_json(output / 'guest.json', {'revision': revision, 'compilerRun': build['compilerRun'], 'target': TARGET,
               'archiveSha256': expected, 'dotnetSha256': DOTNET, 'host': platform.node(), 'os': platform.platform(),
               'rust': rust, 'csharp': csharp, 'files': {p.relative_to(output).as_posix(): sha256(p)
                                                        for p in sorted(output.rglob('*')) if p.is_file()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('sha256', help='original Actions artifact digest')
    parser.add_argument('output', type=Path)
    parser.add_argument('--dotnet', required=True, type=Path, help='private original .NET 10.0.12 x64 runtime host')
    args = parser.parse_args()
    run(args.archive.resolve(strict=True), args.sha256.removeprefix('sha256:'), args.output.resolve(), args.dotnet.resolve(strict=True))
