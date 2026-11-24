"""Exercise the source-identity differences allowed in the full-view GDI comparison."""
import copy
import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest

import gdi_build


class CompilerPairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stream = Path(self.temp.name, "compiler.jsonl")
        self.root = PureWindowsPath("D:/qa/gdi/project/tools/rust-qa/gui")
        binary = "D:/qa/gdi/build/release/native-gui-assessment.exe"
        self.app = dict(reason="compiler-artifact", package_id="path+file:///D:/qa/gdi/project/tools/rust-qa/gui#native-gui-assessment@0.0.0",
                        manifest_path=str(self.root / "Cargo.toml"), features=[], filenames=[binary], executable=binary,
                        target=dict(name="native-gui-assessment", kind=["bin"], src_path=str(self.root / "src/main.rs")))
        library = self.root / gdi_build.PRESENTER
        self.lib = dict(reason="compiler-artifact", package_id="path+file:///" + library.as_posix() + "#0.37.0",
                        manifest_path=str(library / "Cargo.toml"), features=["winit"],
                        target=dict(name="egui_wgpu", kind=["lib"], src_path=str(library / "src/lib.rs")))

    def read(self, app, lib, *, gdi):
        rows = [app, lib, {"reason": "build-finished", "success": True}]
        self.stream.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        return gdi_build.compilation(self.stream, gdi=gdi)[-1]

    def test_staged_renderer_and_paired_registry_build_keep_the_same_feature_signature(self):
        selected = self.read(self.app, self.lib, gdi=True)
        original = copy.deepcopy(self.lib)
        original.update(package_id="registry+https://github.com/rust-lang/crates.io-index#egui-wgpu@0.37.0",
                        manifest_path="C:/cache/egui-wgpu-0.37.0/Cargo.toml")
        self.assertEqual(self.read(self.app, original, gdi=False), selected)
        with self.assertRaises(ValueError):
            self.read(self.app, original, gdi=True)
        original["features"].append("unexpected-feature")
        self.assertNotEqual(self.read(self.app, original, gdi=False), selected)

    def test_incorrect_local_renderer_manifest_is_refused(self):
        with self.assertRaises(ValueError):
            self.read(self.app, {**self.lib, "manifest_path": "D:/qa/other/Cargo.toml"}, gdi=True)

    def test_wrong_gui_entrypoint_is_refused(self):
        target = {**self.app["target"], "src_path": "D:/qa/other/src/main.rs"}
        with self.assertRaises(ValueError):
            self.read({**self.app, "target": target}, self.lib, gdi=True)
