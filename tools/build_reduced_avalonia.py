#!/usr/bin/env python3
"""Build the repository's reduced Avalonia packages from verified local inputs.

This tool never accesses the network. It requires the repository-pinned .NET SDK,
three official NuGet archives and the pinned upstream source archive. It builds
only Controls and Fluent for net10.0, then replaces every corresponding assembly
and reference assembly in private, distinctly versioned packages. Other upstream
assemblies and notices remain intact. Generated packages are not for publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

from audit_reduced_avalonia import audit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'packaging/avalonia-reduced/inputs.json'
REMOVALS = ROOT / 'packaging/avalonia-reduced/removals.json'


def digest(path: Path, algorithm: str = 'sha512') -> str:
    """Hash complete input bytes before extraction or execution."""
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def verify(path: Path, expected: str) -> None:
    if digest(path) != expected:
        raise ValueError(f'Pinned input hash mismatch: {path}')


def extract_zip(path: Path, target: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            dest = target / item.filename
            if not dest.resolve().is_relative_to(target.resolve()):
                raise ValueError(f'Unsafe archive path: {item.filename}')
        archive.extractall(target)


def extract_tar(path: Path, target: Path) -> None:
    """Extract regular files only, including on Python 3.11 before data filters."""
    with tarfile.open(path) as archive:
        for item in archive:
            dest = target / item.name
            if not dest.resolve().is_relative_to(target.resolve()):
                raise ValueError(f'Unsafe archive path: {item.name}')
            if item.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(item)
                assert stream is not None
                with stream, dest.open('wb') as output:
                    shutil.copyfileobj(stream, output)
            else:
                raise ValueError(f'Unsupported archive entry: {item.name}')


def reduce_sources(source: Path, removal: dict) -> None:
    for relative in removal['removedSources']:
        (source / relative).unlink()
    removed_names = {Path(p).name for p in removal['removedSources'] if p.endswith('.xaml')}
    for theme in ('Fluent', 'Simple'):
        path = source / f'src/Avalonia.Themes.{theme}/Controls/{theme}Controls.xaml'
        text = path.read_text(encoding='utf-8-sig')
        text = '\n'.join(line for line in text.split('\n')
                         if not any(f'/{name}"' in line for name in removed_names))
        path.write_text(text, encoding='utf-8', newline='\n')
    for name in ('PopupRoot', 'OverlayPopupHost'):
        path = source / f'src/Avalonia.Themes.Fluent/Controls/{name}.xaml'
        text = path.read_text(encoding='utf-8-sig')
        text = text.replace('LayoutTransformControl', 'Decorator')
        text = text.replace('LayoutTransform="', 'RenderTransform="')
        path.write_text(text, encoding='utf-8', newline='\n')
    for path in (source / 'src').rglob('*'):
        if path.suffix in ('.cs', '.xaml'):
            text = path.read_text(encoding='utf-8-sig')
            if 'Microsoft Public License' in text or 'MS-PL' in text:
                raise ValueError(f'Unexpected MS-PL source remains: {path}')


def write_project(work: Path, source: Path, packages: Path, name: str, manifest: dict) -> Path:
    directory = work / name
    directory.mkdir()
    official = packages / 'Avalonia'
    references = list((official / 'lib/net10.0').glob('*.dll'))
    references = [p for p in references if p.stem != 'Avalonia.Controls']
    references.append(packages / 'Avalonia.Remote.Protocol/lib/net10.0/Avalonia.Remote.Protocol.dll')
    extra = ''
    if name == 'Avalonia.Themes.Fluent':
        references.append(work / 'Avalonia.Controls/bin/Release/net10.0/Avalonia.Controls.dll')
        extra = f'''<ItemGroup><AvaloniaResource Include="{escape(str(source))}/src/{name}/**/*.xaml"><Link>%(RecursiveDir)%(Filename)%(Extension)</Link></AvaloniaResource></ItemGroup>
<Import Project="{escape(str(official))}/build/Avalonia.props"/>
<Import Project="{escape(str(official))}/build/Avalonia.targets"/>'''
    refs = '\n'.join(f'<Reference Include="{p.stem}"><HintPath>{escape(str(p))}</HintPath><Private>false</Private></Reference>' for p in references)
    upstream_project = ET.parse(source / f'src/{name}/{name}.csproj')
    friends = ''.join(ET.tostring(item, encoding='unicode') for item in upstream_project.findall("ItemGroup[@Label='InternalsVisibleTo']"))
    # Explicit empty boundaries prevent inheriting this application's build props.
    for file in ('Directory.Build.props', 'Directory.Build.targets'):
        (directory / file).write_text('<Project/>\n', encoding='utf-8')
    # The SDK otherwise discovers the enclosing application Git repository and
    # appends its HEAD to assembly metadata, changing identical upstream builds.
    upstream_version = escape(manifest['upstreamVersion'])
    upstream_commit = escape(manifest['upstreamCommit'])
    project = directory / f'{name}.csproj'
    project.write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup>
<TargetFramework>net10.0</TargetFramework><AssemblyName>{name}</AssemblyName><RootNamespace>{name}</RootNamespace>
<ImportDirectoryBuildProps>false</ImportDirectoryBuildProps><ImportDirectoryBuildTargets>false</ImportDirectoryBuildTargets><EnableDefaultCompileItems>false</EnableDefaultCompileItems><Nullable>enable</Nullable><Version>{upstream_version}</Version><SourceRevisionId>{upstream_commit}</SourceRevisionId><IncludeSourceRevisionInInformationalVersion>false</IncludeSourceRevisionInInformationalVersion><InformationalVersion>{upstream_version}+{upstream_commit}</InformationalVersion><LangVersion>14.0</LangVersion>
<EnableNETAnalyzers>false</EnableNETAnalyzers><GenerateDocumentationFile>true</GenerateDocumentationFile><NoWarn>CS1591</NoWarn>
<SignAssembly>true</SignAssembly><DelaySign>true</DelaySign><AssemblyOriginatorKeyFile>{escape(str(source))}/build/avalonia.snk</AssemblyOriginatorKeyFile>
<PathMap>{escape(str(work))}=/_/avalonia-reduced</PathMap><Deterministic>true</Deterministic><DebugType>none</DebugType><DebugSymbols>false</DebugSymbols><NuGetAudit>false</NuGetAudit>
<CreateHardLinksForCopyAdditionalFilesIfPossible>false</CreateHardLinksForCopyAdditionalFilesIfPossible><CreateHardLinksForCopyFilesToOutputDirectoryIfPossible>false</CreateHardLinksForCopyFilesToOutputDirectoryIfPossible><CreateHardLinksForCopyLocalIfPossible>false</CreateHardLinksForCopyLocalIfPossible>
</PropertyGroup>
<Import Project="{escape(str(source))}/build/AvaloniaPublicKey.props"/>
<ItemGroup><Compile Include="{escape(str(source))}/src/{name}/**/*.cs" Exclude="{escape(str(source))}/src/{name}/obj/**/*.cs;{escape(str(source))}/src/{name}/bin/**/*.cs"/>{refs}</ItemGroup>{friends}{extra}
</Project>''', encoding='utf-8', newline='\n')
    return project


def create_package(original: Path, output: Path, work: Path, source: Path,
                   name: str, manifest: dict, provenance: dict) -> Path:
    namespace = 'http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd'
    ET.register_namespace('', namespace)
    entries: dict[str, bytes] = {}
    assembly = 'Avalonia.Controls' if name == 'Avalonia' else name
    build_output = work / assembly / 'bin/Release/net10.0'
    with zipfile.ZipFile(original) as archive:
        for item in archive.infolist():
            path = item.filename
            if item.is_dir() or path == '.signature.p7s' or path.startswith(('lib/net8.0/', 'ref/net8.0/')):
                continue
            data = archive.read(item)
            if path.endswith('.nuspec'):
                tree = ET.fromstring(data)
                metadata = tree.find(f'{{{namespace}}}metadata')
                assert metadata is not None
                metadata.find(f'{{{namespace}}}version').text = manifest['packageVersion']
                metadata.find(f'{{{namespace}}}description').text = (
                    'Private Immich Folder Watch reduced build of Avalonia. MS-PL components and Silverlight-derived layout transform removed. '
                    'Modified popup templates support ordinary application popups; transformed layout bounds are not preserved. '
                    'net10.0 only. See reduced-avalonia.json for source provenance and exclusions.')
                dependencies = metadata.find(f'{{{namespace}}}dependencies')
                if dependencies is not None:
                    for group in list(dependencies):
                        if group.get('targetFramework') != 'net10.0':
                            dependencies.remove(group)
                        else:
                            for dep in group:
                                if dep.get('id') == 'Avalonia':
                                    dep.set('version', f"[{manifest['packageVersion']}]")
                data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
            elif path == '[Content_Types].xml':
                types = ET.fromstring(data)
                content_ns = 'http://schemas.openxmlformats.org/package/2006/content-types'
                existing = {entry.get('Extension') for entry in types}
                for extension, content_type in [('json', 'application/json'), ('md', 'text/markdown')]:
                    if extension not in existing:
                        ET.SubElement(types, f'{{{content_ns}}}Default',
                                      Extension=extension, ContentType=content_type)
                data = ET.tostring(types, encoding='utf-8', xml_declaration=True)
            elif path.endswith('/AvaloniaVersion.props'):
                data = data.replace(b'12.1.6', manifest['packageVersion'].encode())
            elif Path(path).stem == assembly and path.startswith(('lib/', 'ref/')):
                # Full reduced DLL is also a safe reference assembly: no removed
                # types are retained in the compile-time surface.
                replacement = build_output / Path(path).name
                if not replacement.exists():
                    raise ValueError(f'No rebuilt replacement for {path}')
                data = replacement.read_bytes()
            entries[path] = data
    entries['reduced-avalonia.json'] = (json.dumps(provenance, indent=2, sort_keys=True) + '\n').encode()
    entries['UPSTREAM-LICENSE.md'] = (source / 'licence.md').read_bytes()
    entries['UPSTREAM-NOTICE.md'] = (source / 'NOTICE.md').read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    result = output / f"{name.lower()}.{manifest['packageVersion']}.nupkg"
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, data in sorted(entries.items()):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return result


def build(source_archive: Path, upstream_packages: Path, output: Path,
          work: Path, dotnet: str) -> list[Path]:
    """Validate inputs and build packages; fail on stale/nonempty work directories."""
    manifest = json.loads(MANIFEST.read_text())
    removal = json.loads(REMOVALS.read_text())
    verify(source_archive, manifest['source']['sha512'])
    for package in manifest['packages']:
        verify(upstream_packages / package['filename'], package['sha512'])
    if work.exists() and any(work.iterdir()):
        raise ValueError(f'Work directory must be empty: {work}')
    work.mkdir(parents=True, exist_ok=True)
    sdk_settings = {'sdk': {'version': manifest['sdkVersion'], 'rollForward': 'disable', 'allowPrerelease': False}}
    (work / 'global.json').write_text(json.dumps(sdk_settings), encoding='utf-8')
    actual_sdk = subprocess.check_output([dotnet, '--version'], cwd=work, text=True).strip()
    if actual_sdk != sdk_settings['sdk']['version']:
        raise ValueError(f'Expected SDK {sdk_settings["sdk"]["version"]}, got {actual_sdk}')
    extract_tar(source_archive, work)
    source = work / f"Avalonia-{manifest['upstreamCommit']}"
    reduce_sources(source, removal)
    packages = work / 'upstream-packages'
    for package in manifest['packages']:
        extract_zip(upstream_packages / package['filename'], packages / package['id'])
    # There are no PackageReferences in the generated build projects. Explicitly
    # clear feeds and fallback folders to guarantee compilation needs no network.
    config = work / 'NuGet.Config'
    config.write_text('<configuration><packageSources><clear/></packageSources><fallbackPackageFolders><clear/></fallbackPackageFolders></configuration>', encoding='utf-8')
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    for name in ('Avalonia.Controls', 'Avalonia.Themes.Fluent'):
        project = write_project(work, source, packages, name, manifest)
        subprocess.run([dotnet, 'build', str(project), '-c', 'Release', '-m:1',
                        '--configfile', str(config), '-p:UseSharedCompilation=false'],
                       cwd=work, env=env, check=True)
    assemblies = {f'{name}.dll': digest(work / name / f'bin/Release/net10.0/{name}.dll', 'sha256')
                  for name in ('Avalonia.Controls', 'Avalonia.Themes.Fluent')}
    provenance = {'schemaVersion': 1, 'upstreamCommit': manifest['upstreamCommit'],
                  'packageVersion': manifest['packageVersion'], 'upstreamVersion': manifest['upstreamVersion'],
                  'sourceArchiveSha512': manifest['source']['sha512'], 'assemblies': assemblies,
                  'removedSources': removal['removedSources'], 'modifiedSources': removal['modifiedSources'],
                  'strongName': 'delay-signed; identity only, not an authenticity assertion',
                  'targetFramework': 'net10.0'}
    results = []
    for name in ('Avalonia', 'Avalonia.Themes.Fluent'):
        package = next(p for p in manifest['packages'] if p['id'] == name)
        results.append(create_package(upstream_packages / package['filename'], output,
                                      work, source, name, manifest, provenance))
    (output / 'reduced-avalonia.json').write_text(json.dumps(provenance, indent=2) + '\n')
    audit(results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', required=True, type=Path)
    parser.add_argument('--upstream-packages', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    for result in build(args.source_archive.resolve(), args.upstream_packages.resolve(),
                        args.output.resolve(), args.work_dir.resolve(), args.dotnet):
        print(f'{result}: sha512={digest(result)}')


if __name__ == '__main__':
    main()
