"""Run the portable DIB controls with the selected Rust compiler."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest
from hashlib import sha256

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class RendererControls(unittest.TestCase):
    def test_checked_in_sources_match_the_offline_patch_inputs(self):
        pins = json.loads((HERE / "renderer-inputs.json").read_bytes())
        self.assertEqual(sha256((HERE / "offscreen.patch").read_bytes()).hexdigest(), pins["patchSha256"])
        self.assertEqual(set(pins["files"]), {"artifacts/gdi/egui-wgpu/src/winit.rs"})
        self.assertEqual({row["source"] for row in pins["copies"].values()}, {"dib_layout.rs", "gdi_present.rs"})
        for dest, row in pins["copies"].items():
            self.assertEqual(dest, "artifacts/gdi/egui-wgpu/src/" + row["source"])
            self.assertEqual(sha256((HERE / row["source"]).read_bytes()).hexdigest(), row["sha256"])

    def test_portable_bitmap_layout_channel_order_and_draw_results(self):
        local = ROOT / "artifacts/rust/toolchain/bin"
        compiler = shutil.which("rustc", path=str(local)) or shutil.which("rustc")
        self.assertIsNotNone(compiler, "The Rust compiler is required by the GDI layout controls")
        with TemporaryDirectory() as directory:
            output = Path(directory)
            shutil.copyfile(HERE / "dib_layout.rs", output / "dib_layout.rs")
            (output / "main.rs").write_text("mod dib_layout;\n", encoding="ascii")
            exe = output / "controls.exe"
            subprocess.run([compiler, "--edition=2024", "--test", "-Dwarnings", "main.rs", "-o", str(exe)],
                           cwd=output, check=True)
            subprocess.run([str(exe)], cwd=output, check=True)


if __name__ == "__main__":
    unittest.main()
