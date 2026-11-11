"""Exercise the restore hook with MSBuild without downloading packages."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DOTNET = shutil.which("dotnet")


@unittest.skipUnless(DOTNET, "The .NET SDK is required for MSBuild hook tests")
class RestoreHookTests(unittest.TestCase):
    def run_hook(self, project_name, prepared=False):
        with tempfile.TemporaryDirectory(prefix="ifw restore hook ") as temporary:
            root = Path(temporary)
            shutil.copyfile(ROOT / "Directory.Build.targets", root / "Directory.Build.targets")
            (root / "tools").mkdir()
            (root / "tools/prepare_reduced_avalonia.py").write_text(
                "import pathlib, sys\n"
                "assert '--if-needed' in sys.argv\n"
                "assert pathlib.Path(sys.argv[sys.argv.index('--source-root')+1]).is_dir()\n"
                "pathlib.Path('called').write_text('prepared')\n", encoding="utf-8")
            project = root / (project_name + ".proj")
            project.write_text(
                '<Project><Import Project="Directory.Build.targets" />'
                '<Target Name="CollectPackageReferences">'
                '<Error Condition="\'$(MSBuildProjectName)\' == \'ImmichFolderWatch.App.Linux\' '
                'and \'$(ReducedAvaloniaPrepared)\' != \'true\' and !Exists(\'called\')" '
                'Text="Bootstrap must precede package collection" />'
                '</Target></Project>', encoding="utf-8")
            command = [DOTNET, "msbuild", str(project), "-t:CollectPackageReferences", "-nologo"]
            if prepared:
                command.append("-p:ReducedAvaloniaPrepared=true")
            subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
            return (root / "called").exists()

    def test_linux_app_bootstraps_before_package_collection_with_spaced_path(self):
        self.assertTrue(self.run_hook("ImmichFolderWatch.App.Linux"))

    def test_unrelated_projects_do_not_execute_bootstrap(self):
        self.assertFalse(self.run_hook("ImmichFolderWatch.Core"))

    def test_isolated_prepared_feed_can_skip_default_feed_preparation(self):
        self.assertFalse(self.run_hook("ImmichFolderWatch.App.Linux", prepared=True))


if __name__ == "__main__":
    unittest.main()
