"""Exercise the private renderer's actual CPU implementation without opening a desktop."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import tomllib
import unittest

from upstream import prepare


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QA = HERE.parent
PKG = "artifacts/gdi/egui-wgpu/src/"


class RendererControls(unittest.TestCase):
    def test_renderer_sources_and_ordinary_queue_boundary(self):
        pins = json.loads((HERE / "renderer-inputs.json").read_bytes())
        patch = (HERE / "cpu-paint.patch").read_bytes()
        self.assertEqual(sha256(patch).hexdigest(), pins["patchSha256"])
        self.assertEqual(set(pins["files"]), {PKG + "winit.rs"})
        self.assertEqual(set(pins["copies"]), {PKG + n for n in ("cpu_present.rs", "cpu_raster.rs", "dib_layout.rs")})
        for path, item in pins["copies"].items():
            self.assertEqual(Path(item["source"]).name, Path(path).name)
            self.assertEqual(sha256((HERE / item["source"]).read_bytes()).hexdigest(), item["sha256"])
        cached = ROOT / "artifacts/rust/assessment-cache/registry/src"
        original, = cached.glob("*/egui-wgpu-0.37.0/src/winit.rs")
        with TemporaryDirectory() as directory:
            target = Path(directory)
            entry = target / PKG / "winit.rs"
            entry.parent.mkdir(parents=True)
            shutil.copyfile(original, entry)
            subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero", "--whitespace=error", "-"],
                           cwd=target, input=patch, check=True)
            self.assertEqual([sha256(p.read_bytes()).hexdigest() for p in (original, entry)], pins["files"][PKG + "winit.rs"])
            route = entry.read_text(encoding="utf-8").split("pub fn paint_and_update_textures(", 1)[1]
            self.assertLess(route.index("cpu.paint("), route.index("cpu.finish("))
            self.assertLess(route.index("return 0.0;"), route.index("self.cpu.fallback(reason)"))
            self.assertLess(route.index("self.cpu.fallback(reason)"), route.index("get_current_texture()"))
            presenter = (HERE / "cpu_present.rs").read_text(encoding="utf-8")
            self.assertNotIn("IFW_QA_CPU_PAINT", presenter)
            self.assertIn("info.backend == wgpu::Backend::Dx12", presenter)
            self.assertIn("info.device_type == wgpu::DeviceType::Cpu", presenter)
            self.assertIn('info.name == "Microsoft Basic Render Driver"', presenter)
            self.assertIn("Self::Wgpu => {}", presenter)
            finish = presenter.split("pub(super) fn finish(", 1)[1].split("fn complete_screenshots", 1)[0]
            self.assertEqual(finish.count("let mut renderer = state.renderer.write();"), 2)
            self.assertLess(finish.index("renderer.update_texture("), finish.index("state.queue.submit([])"))
            self.assertLess(finish.index("state.queue.submit([])"), finish.rindex("state.renderer.write()"))
            self.assertLess(finish.index("renderer.free_texture("), finish.index("self.complete_screenshots("))
            self.assertNotIn("get_current_texture", finish)

    def test_real_raster_pixels_deltas_and_input_limits(self):
        sources = prepare(ROOT / "artifacts/rust/cpu-paint-cache").sources
        gui = QA / "gui"
        text = gui / "artifacts/text"
        libs = {"egui": text / "egui", "epaint": text / "epaint", "unicode-bidi": text / "unicode-bidi",
                "constify": sources["constify"], "strength_reduce": sources["strength_reduce"]}
        quote = lambda p: json.dumps(p.resolve().as_posix())
        with TemporaryDirectory() as directory:
            project = Path(directory)
            manifest = ('[package]\nname="ifw-cpu-raster-controls"\nversion="0.0.0"\nedition="2024"\n'
                        '[lib]\npath="lib.rs"\n[workspace]\nresolver="3"\n'
                        '[dependencies]\negui = { version="=0.37.0", default-features=false }\n'
                        'cpu_painter = {package="hdrshot-egui-backend", version="=0.2.0", path='
                        + quote(sources["hdrshot-egui-backend"]) + '}\n[patch.crates-io]\n')
            manifest += "".join(name + " = {path=" + quote(path) + "}\n" for name, path in libs.items())
            (project / "Cargo.toml").write_text(manifest, encoding="utf-8")
            (project / "lib.rs").write_text("mod cpu_raster;\n", encoding="ascii")
            shutil.copyfile(HERE / "cpu_raster.rs", project / "cpu_raster.rs")
            shutil.copyfile(gui / "Cargo.lock", project / "Cargo.lock")
            env = dict(os.environ, CARGO_HOME=str(ROOT / "artifacts/rust/assessment-cache"),
                       CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(project / "target"),
                       PATH=str(ROOT / "artifacts/rust/toolchain/bin") + os.pathsep + os.environ["PATH"])
            subprocess.run(["cargo", "metadata", "--offline", "--format-version", "1"], env=env, cwd=project,
                           check=True, stdout=subprocess.DEVNULL)
            def versions(lock):
                return {(p["name"], p["version"]) for p in tomllib.loads(lock.read_text(encoding="utf-8"))["package"]}
            added = versions(project / "Cargo.lock") - versions(gui / "Cargo.lock")
            self.assertEqual(added, {("ifw-cpu-raster-controls", "0.0.0"), ("hdrshot-egui-backend", "0.2.0"),
                                     ("constify", "0.0.1"), ("strength_reduce", "0.2.4")})
            subprocess.run(["cargo", "test", "--offline", "--locked", "--lib", "--quiet"], env=env, cwd=project, check=True)


if __name__ == "__main__":
    unittest.main()
