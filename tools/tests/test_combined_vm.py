"""Check the compiler/guest split for the combined Windows x64 qualification."""
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
script = ROOT / "tools/rust-qa/windows-local/combined.py"
spec = importlib.util.spec_from_file_location("ifw_combined_vm", script)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)
import native


class CombinedGuestTests(unittest.TestCase):
    def test_x64_compiler_never_runs_subject_or_creates_a_test_root(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "out"
            out.mkdir()
            binary = base / "build" / vm.TARGET / "release" / vm.EXECUTABLE
            commands = []
            def compile_only(cmd, **kwargs):
                commands.append(cmd)
                if len(cmd) > 1 and cmd[1] == "build":
                    binary.parent.mkdir(parents=True)
                    binary.write_bytes(b"compiler output")
            win = SimpleNamespace(name="nt", environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"})
            with (patch.object(native, "os", win), patch.object(native.sys, "platform", "win32"),
                  patch.object(native.subprocess, "run", side_effect=compile_only),
                  patch.object(native.shutil, "which", return_value="dumpbin.exe"),
                  patch.object(native, "exercise", side_effect=AssertionError("Hosted execution"))):
                args = (vm.TARGET, base / "tools", base / "vendor", base / "build", out, {"PATH": "test"}, 1)
                with self.assertRaisesRegex(ValueError, "local Windows"):
                    native.run_native(*args)
                result = native.run_native(*args, vm_inputs=True)
            self.assertFalse((out / "synthetic-root").exists())
            self.assertNotIn("smokeSha256", result)
            self.assertEqual(result["binarySha256"], vm.sha256(out / vm.EXECUTABLE))
            self.assertEqual([c[1] for c in commands[1:]], ["build", "clippy", "/nologo"])

    def test_kit_rejects_a_native_result_changed_binary_or_missing_graph(self):
        revision = vm.subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        lock = "tools/rust-qa/combined-profile/Cargo.lock"
        digest = vm.sha256(ROOT / lock)
        files = {n: b"compiled fixture" for n in ("build.log", "clippy.log", "profile.json", "source-trees.json",
                 "inventory.json", "compiler-units.json", "linked-libraries.txt", vm.EXECUTABLE)}
        files.update({t + s: b"target graph" for t in vm.TARGETS for s in (".json", ".tree")})
        hashes = {k: sha256(v).hexdigest() for k, v in files.items()}
        receipt = dict(passed=True, revision=revision, sources={lock: digest}, lock=digest,
                       rustc=[f"host: {vm.TARGET}"], outputs=hashes,
                       compiler=dict(target=vm.TARGET, binarySha256=hashes[vm.EXECUTABLE]))
        for changes, contents, error in (({}, files, None), ({"native": {}}, files, "compiler-only"),
                ({}, {**files, vm.EXECUTABLE: b"changed"}, "Changed compiler output"),
                ({}, {k: v for k, v in files.items() if k != vm.TARGET + ".tree"}, "compiler-only")):
            with self.subTest(error=error), TemporaryDirectory() as d, BytesIO() as buf:
                with ZipFile(buf, "w") as z:
                    z.writestr("compiler.json", json.dumps({**receipt, **changes}))
                    for name, data in contents.items():
                        z.writestr(name, data)
                out = Path(d)
                with ZipFile(buf) as z, patch.object(vm, "source_witness", return_value=receipt["sources"]):
                    if error:
                        with self.assertRaisesRegex(ValueError, error):
                            vm.unpack(z, out, out / vm.EXECUTABLE, revision)
                    else:
                        self.assertEqual(vm.unpack(z, out, out / vm.EXECUTABLE, revision), receipt)


if __name__ == "__main__":
    unittest.main()
