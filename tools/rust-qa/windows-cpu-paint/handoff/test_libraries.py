"""Replay the promoted Windows rlib and the example's compiler-unit contract."""
import copy
import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from zipfile import ZipFile

from fixture_build import archived_renderer, compiler_examples, library_hashes

GUI = PureWindowsPath("D:/private/project/tools/rust-qa/gui")
RELEASE = PureWindowsPath("D:/private/build/release")
APP_ID = "path+file:///D:/private/project/tools/rust-qa/gui#native-gui-assessment@0.0.0"
PROFILE = dict(opt_level="3", debuginfo=0, debug_assertions=False, overflow_checks=False, test=False)
PROMOTED = RELEASE / "libnative_gui_assessment.rlib"
OUTPUT = RELEASE / "build/native-gui-assessment/0123456789abcdef/out/libnative_gui_assessment-0123456789abcdef"
COMPILED = OUTPUT.with_suffix(".rlib")
METADATA = OUTPUT.with_suffix(".rmeta")


def unit(name, kind, source, outputs, *, fresh=False):
    binary = kind in ("bin", "example")
    return dict(reason="compiler-artifact", package_id=APP_ID, manifest_path=str(GUI / "Cargo.toml"),
                target=dict(name=name, kind=[kind], crate_types=["bin" if binary else "lib"], src_path=str(GUI / source)),
                features=[], profile=PROFILE, fresh=fresh, filenames=[str(p) for p in outputs],
                executable=str(outputs[0]) if binary else None)


def write_stream(path, units):
    rows = units + [dict(reason="build-finished", success=True)]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class NativeLibraryReceipt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.area = Path(self.tmp.name)
        self.base = self.area / "cpu.jsonl"
        self.example = self.area / "example.jsonl"
        self.app = unit("native-gui-assessment", "bin", "src/main.rs", [RELEASE / "native-gui-assessment.exe"])
        self.original = unit("native_gui_assessment", "lib", "src/lib.rs", [PROMOTED, METADATA])
        self.renderer = unit("egui_wgpu", "lib", "artifacts/gdi/egui-wgpu/src/lib.rs",
                             [RELEASE / "deps/libegui_wgpu-1234567890abcdef.rlib"])
        self.renderer.update(manifest_path=str(GUI / "artifacts/gdi/egui-wgpu/Cargo.toml"), features=["capture", "winit"],
                             package_id="path+file:///D:/private/project/tools/rust-qa/gui/artifacts/gdi/egui-wgpu#0.37.0")
        self.linked = dict(self.original, fresh=True, filenames=[str(COMPILED), str(METADATA)])
        self.ordinary = [self.original, self.renderer, self.app]
        self.rows = [self.linked, dict(self.renderer, fresh=True),
                     unit("texture_handoff", "example", "examples/texture_handoff/main.rs", [RELEASE / "examples/texture_handoff.exe"])]
        write_stream(self.base, self.ordinary)

    def test_compiler_can_name_the_same_application_library_using_either_output(self):
        for path in (COMPILED, PROMOTED):
            with self.subTest(path=path):
                self.rows[0]["filenames"] = [str(path), str(METADATA)]
                write_stream(self.example, self.rows)
                self.assertEqual(compiler_examples(self.base, self.example), 2)

    def test_compiler_can_report_the_exact_same_deps_outputs_on_both_builds(self):
        compiled = RELEASE / "deps" / COMPILED.name
        metadata = RELEASE / "deps" / METADATA.name
        outputs = [str(compiled), str(metadata)]
        self.original["filenames"] = self.linked["filenames"] = outputs
        write_stream(self.base, self.ordinary)
        write_stream(self.example, self.rows)
        self.assertEqual(compiler_examples(self.base, self.example), 2)

    def test_refuses_other_library_paths_metadata_and_compilation_units(self):
        changes = [
            (0, dict(filenames=[str(COMPILED.parent / "other.rlib"), str(METADATA)])),
            (0, dict(filenames=[str(COMPILED), str(METADATA.with_name("other.rmeta"))])),
            (0, dict(package_id=self.renderer["package_id"])),
            (0, dict(profile=dict(PROFILE, opt_level="0"))),
            (0, dict(features=["unrelated"])),
            (0, dict(fresh=False)),
            (1, dict(filenames=[str(PROMOTED)])),
            (1, dict(fresh=False)),
            (2, dict(features=["unrelated"])),
            (2, dict(fresh=True)),
        ]
        for index, fields in changes:
            rows = copy.deepcopy(self.rows)
            rows[index].update(fields)
            write_stream(self.example, rows)
            with self.subTest(index=index, fields=fields), self.assertRaises(ValueError):
                compiler_examples(self.base, self.example)
        for rows in (self.rows[1:], self.rows + [self.rows[1]]):
            write_stream(self.example, rows)
            with self.assertRaises(ValueError):
                compiler_examples(self.base, self.example)

    def test_refuses_promotion_from_an_unrelated_output_directory(self):
        other = METADATA.with_name("libnative_gui_assessment-1111111111111111.rmeta")
        self.original["filenames"] = [str(PROMOTED), str(other)]
        self.linked["filenames"] = [str(other.with_suffix(".rlib")), str(other)]
        write_stream(self.base, self.ordinary)
        write_stream(self.example, self.rows)
        with self.assertRaises(ValueError):
            compiler_examples(self.base, self.example)

    def test_distinct_library_bytes_or_missing_metadata_fail(self):
        paths = {name: name for name in ("original", "compiled", "metadata", "presenter", "presenterMetadata")}
        library = b"!<arch>\nfixture"
        members = dict(original=library, compiled=library, metadata=b"gui metadata",
                       presenter=library + b"wgpu", presenterMetadata=b"wgpu metadata")
        hashes = library_hashes(members, paths)
        self.assertEqual(hashes["original"], hashes["compiled"])
        self.assertNotEqual(hashes["presenter"], hashes["compiled"])
        for key in ("compiled", "presenter", "metadata", "presenterMetadata"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                library_hashes(dict(members, **{key: b""}), paths)
        with self.assertRaises(ValueError):
            library_hashes(dict(members, compiled=library + b"x"), paths)

    def test_compiled_renderer_matches_original_archive_before_and_after_linking(self):
        name = "deps/libegui_software_backend-1234567890abcdef.rlib"
        native = self.area / "build/release" / name
        native.parent.mkdir(parents=True)
        native.write_bytes(b"!<arch>\noriginal")
        with ZipFile(self.area / "cpu-libraries.zip", "w") as archive:
            archive.writestr(name, native.read_bytes())
        self.assertEqual(archived_renderer(self.area, [name], compare_live=True), archived_renderer(self.area, [name]))
        native.write_bytes(b"!<arch>\nchanged")
        with self.assertRaises(ValueError):
            archived_renderer(self.area, [name], compare_live=True)
        with self.assertRaises(ValueError):
            archived_renderer(self.area, [])
