"""Regression tests for the private reduced-Avalonia package builder."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / 'build_reduced_avalonia.py'
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location('build_reduced_avalonia', MODULE_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReducedAvaloniaBuildTests(unittest.TestCase):
    def test_assembly_metadata_ignores_enclosing_git_history(self):
        manifest = json.loads(builder.MANIFEST.read_text())
        sdk = {'sdk': {'version': manifest['sdkVersion'], 'rollForward': 'disable'}}
        executable = 'dotnet.exe' if os.name == 'nt' else 'dotnet'
        local_sdk = builder.ROOT / '.build-cache' / f"sdk-{sdk['sdk']['version']}" / executable
        dotnet = shutil.which('dotnet') or (str(local_sdk) if local_sdk.exists() else None)
        if not dotnet or not shutil.which('git'):
            self.skipTest('The pinned .NET SDK and Git are required for the metadata regression test')
        manifest = json.loads(builder.MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'global.json').write_text(json.dumps(sdk))
            source = root / 'source'
            (source / 'build').mkdir(parents=True)
            (source / 'build/AvaloniaPublicKey.props').write_text('<Project/>')
            upstream_project = source / 'src/Avalonia.Controls/Avalonia.Controls.csproj'
            upstream_project.parent.mkdir(parents=True)
            upstream_project.write_text('<Project/>')
            project = builder.write_project(root, source, root / 'packages',
                                            'Avalonia.Controls', manifest)

            def metadata_version():
                result = subprocess.check_output(
                    [dotnet, 'msbuild', str(project), '-target:GetAssemblyAttributes',
                     '-getItem:AssemblyAttribute', '-nologo'], cwd=root, text=True)
                attributes = json.loads(result)['Items']['AssemblyAttribute']
                return next(attribute['_Parameter1'] for attribute in attributes
                            if attribute['Identity'] == 'System.Reflection.AssemblyInformationalVersionAttribute')

            versions = [metadata_version()]
            subprocess.run(['git', 'init', str(root)], check=True, capture_output=True)
            for message in ('first unrelated application commit', 'second unrelated application commit'):
                subprocess.run(['git', '-C', str(root), '-c', 'user.name=Build regression test',
                                '-c', 'user.email=build-test@example.invalid', '-c', 'commit.gpgsign=false',
                                '-c', f'core.hooksPath={root / "empty-hooks"}', 'commit', '--allow-empty',
                                '-m', message], check=True, capture_output=True)
                versions.append(metadata_version())
            expected = f"{manifest['upstreamVersion']}+{manifest['upstreamCommit']}"
            self.assertEqual(versions, [expected, expected, expected])

    def test_corrupted_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.nupkg'
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                builder.verify(path, '0' * 128)

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'input.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('../escape', b'payload')
            with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
                builder.extract_zip(path, root / 'output')
            self.assertFalse((root / 'escape').exists())

    def test_tar_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'input.tar'
            with tarfile.open(path, 'w') as archive:
                item = tarfile.TarInfo('escape')
                item.type = tarfile.SYMTYPE
                item.linkname = '../outside'
                archive.addfile(item)
            with self.assertRaisesRegex(ValueError, 'Unsupported archive entry'):
                builder.extract_tar(path, root / 'output')

    def test_manifest_covers_complete_components_and_unlabelled_derivative(self):
        removal = json.loads(builder.REMOVALS.read_text())['removedSources']
        self.assertIn('src/Avalonia.Controls/LayoutTransformControl.cs', removal)
        self.assertIn('src/Avalonia.Controls/CalendarDatePicker/CalendarDatePicker.Properties.cs', removal)
        self.assertIn('src/Avalonia.Themes.Fluent/Controls/DateTimePickerShared.xaml', removal)
        self.assertEqual(len(removal), len(set(removal)))

    def test_reduction_removes_sources_imports_and_adapts_popup_wrappers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            removed = 'src/Avalonia.Themes.Fluent/Controls/Calendar.xaml'
            for theme in ('Fluent', 'Simple'):
                controls = root / f'src/Avalonia.Themes.{theme}/Controls'
                controls.mkdir(parents=True)
                (controls / f'{theme}Controls.xaml').write_text(
                    '<ResourceInclude Source="/Calendar.xaml"/>\n'
                    '<ResourceInclude Source="/Button.xaml"/>')
            (root / removed).write_text('Microsoft Public License')
            fluent = root / 'src/Avalonia.Themes.Fluent/Controls'
            for name in ('PopupRoot', 'OverlayPopupHost'):
                (fluent / f'{name}.xaml').write_text(
                    '<LayoutTransformControl LayoutTransform="{TemplateBinding Transform}"></LayoutTransformControl>')
            builder.reduce_sources(root, {'removedSources': [removed]})
            self.assertFalse((root / removed).exists())
            self.assertNotIn('Calendar.xaml', (fluent / 'FluentControls.xaml').read_text())
            self.assertIn('Button.xaml', (fluent / 'FluentControls.xaml').read_text())
            self.assertEqual((fluent / 'PopupRoot.xaml').read_text(),
                             '<Decorator RenderTransform="{TemplateBinding Transform}"></Decorator>')

    def test_package_replaces_compile_and_runtime_assemblies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output'
            binary = root / 'Avalonia.Controls/bin/Release/net10.0'
            binary.mkdir(parents=True)
            (binary / 'Avalonia.Controls.dll').write_bytes(b'reduced')
            (binary / 'Avalonia.Controls.xml').write_bytes(b'reduced-docs')
            source = root / 'source'
            source.mkdir()
            (source / 'licence.md').write_text('upstream license')
            (source / 'NOTICE.md').write_text('upstream notice')
            original = root / 'original.nupkg'
            with zipfile.ZipFile(original, 'w') as archive:
                archive.writestr('Avalonia.nuspec', '''<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"><metadata><version>12.1.6</version><description>original</description><dependencies><group targetFramework="net10.0"/><group targetFramework="net8.0"/></dependencies></metadata></package>''')
                archive.writestr('.signature.p7s', b'original-signature')
                for target in ('lib/net10.0', 'ref/net10.0', 'lib/net8.0', 'ref/net8.0'):
                    archive.writestr(target + '/Avalonia.Controls.dll', b'original')
                archive.writestr('lib/net10.0/Avalonia.Controls.xml', b'original-docs')
                archive.writestr('lib/net10.0/Avalonia.Base.dll', b'unchanged')
            provenance = {'assemblies': {'Avalonia.Controls.dll': 'hash'}}
            result = builder.create_package(original, output, root, source, 'Avalonia',
                                            {'packageVersion': '12.1.6.1'}, provenance)
            with zipfile.ZipFile(result) as archive:
                self.assertEqual(archive.read('lib/net10.0/Avalonia.Controls.dll'), b'reduced')
                self.assertEqual(archive.read('ref/net10.0/Avalonia.Controls.dll'), b'reduced')
                self.assertEqual(archive.read('lib/net10.0/Avalonia.Base.dll'), b'unchanged')
                self.assertFalse(any('net8.0' in p for p in archive.namelist()))
                self.assertNotIn('.signature.p7s', archive.namelist())
                self.assertEqual(json.loads(archive.read('reduced-avalonia.json')), provenance)
                self.assertEqual(archive.read('UPSTREAM-NOTICE.md'), b'upstream notice')


if __name__ == '__main__':
    unittest.main()
