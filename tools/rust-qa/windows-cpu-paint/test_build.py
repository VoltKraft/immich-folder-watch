"""Check the two native Cargo output layouts and reject unrelated changes to the paired build."""
from collections import Counter
from pathlib import PureWindowsPath
import unittest

import cpu_build as build


class NativeBuildTests(unittest.TestCase):
    def setUp(self):
        self.gui = PureWindowsPath("C:/qa/project/tools/rust-qa/gui")
        self.exe = PureWindowsPath("C:/qa/build/release/native-gui-assessment.exe")

    def units(self, separate):
        result = []
        for name, (crate, kind, flags) in build.LIBS.items():
            code = "59eb10d0bc331c77"
            parent = self.exe.parent / "deps" if not separate else self.exe.parent / "build" / name / code / "out"
            prefix = ("" if kind == "proc-macro" else "lib") + crate + "-" + code
            extensions = [".dll", ".dll.lib", ".dll.exp", ".pdb"] if kind == "proc-macro" else [".rlib", ".rmeta"]
            path = self.gui / build.LOCAL[name]
            result.append(dict(manifest_path=str(path / "Cargo.toml"), target=dict(name=crate, kind=[kind], src_path=str(path / "src/lib.rs")),
                               filenames=[str(parent / (prefix + s)) for s in extensions], features=list(flags)))
        return result

    def test_native_libraries_follow_the_compiler_in_both_release_layouts(self):
        for separate in (True, False):
            units = self.units(separate)
            self.assertEqual(set(build.library_units(self.gui, units, self.exe)), set(build.LIBS))
            for original, replacement in (("release", "debug"), ("59eb10d0bc331c77.", "bad."), (".rlib", ".dll")):
                bad = self.units(separate)
                bad[0]["filenames"][0] = bad[0]["filenames"][0].replace(original, replacement)
                with self.assertRaises(ValueError):
                    build.library_units(self.gui, bad, self.exe)

    def test_only_the_three_audited_libraries_and_the_reviewed_syn_feature_can_change(self):
        baseline = Counter({("syn", "2.0.119", "syn", ("lib",), ("full",)): 1})
        new = Counter({("syn", "2.0.119", "syn", ("lib",), ("extra-traits", "full")): 1})
        new.update({(n, build.PINS[n]["version"], crate, (kind,), flags): 1 for n, (crate, kind, flags) in build.LIBS.items()})
        before = [("syn", "2.0.119", ("full",))]
        after = [(n, v, f) for n, v, _, _, f in new]
        build.check_features(before, after)
        build.compare_units(baseline, new)
        for bad in (Counter({("syn", "2.0.119", "syn", ("lib",), ("extra-traits", "full")): 1}),
                    Counter({("egui", "0.37.0", "egui", ("lib",), ("default_fonts",)): 1})):
            with self.assertRaises(ValueError):
                build.compare_units(baseline, new + bad)
        with self.assertRaises(ValueError):
            build.check_features(before, before + [row for row in after if row[0] != "syn"])


if __name__ == "__main__":
    unittest.main()
