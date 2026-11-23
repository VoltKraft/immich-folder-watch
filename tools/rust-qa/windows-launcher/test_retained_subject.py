"""Require a coherent paired build, source override and native compiler inputs for retained launch."""
import copy
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import observe
import retained_subject


class NativePairTests(unittest.TestCase):
    def test_real_pair_verifier_checks_both_pe_images_and_raw_compiler_source_archives(self):
        target = "aarch64-pc-windows-msvc"
        subjects = runpy.run_path(str(retained_subject.WARM / "inputs.py"), run_name="ifw_pair_test")["subjects"]
        sha = observe.recorder.sha
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            artifacts = root / "artifacts/rust"
            directory = artifacts / "windows-warm-window" / target
            cold = artifacts / "gui-build/release/native-gui-assessment.exe"
            warm = directory / "build/release/native-gui-assessment.exe"
            canonical = artifacts / "gui-native" / target / "build.json"
            for path in (cold, warm, canonical):
                path.parent.mkdir(parents=True)
            def write_pe(path, machine, suffix):
                header = bytearray(64)
                header[:2], header[60:64] = b"MZ", (64).to_bytes(4, "little")
                path.write_bytes(header + b"PE\x00\x00" + machine.to_bytes(2, "little") + suffix)
            write_pe(cold, 0xaa64, b"cold")
            write_pe(warm, 0xaa64, b"warm")
            canonical.write_text("baseline")
            archive, compiler, receipt = (directory / n for n in ("eframe-source.zip", "compiler.jsonl", "build.json"))
            archive.write_bytes(b"source")
            compiler.write_bytes(b"compiled")
            build = dict(target=target, revision="revision", baselineReceipt=sha(canonical), binary=sha(warm), baseline=sha(cold),
                         eframeSource={"archive": archive.name, "archiveSha256": sha(archive)},
                         variantInputs={name: sha(retained_subject.WARM / name) for name in subjects.__globals__["VARIANT_INPUTS"]},
                         compilerEvidence={"file": compiler.name, "sha256": sha(compiler),
                                           "application": {"target": "native-gui-assessment", "crateRoot": "src/main.rs",
                                                           "output": warm.name, "sha256": sha(warm)}})
            receipt.write_text(json.dumps(build))
            with (patch.dict(subjects.__globals__, ROOT=root), patch.object(observe.recorder, "hosted", return_value=True),
                  patch.object(subprocess, "check_output", return_value="revision"), patch.object(observe.recorder, "Win32") as api):
                api.return_value.machine.return_value = (0xaa64, 0xaa64)
                self.assertEqual(subjects(target)[1:3], (cold, warm))
                missing_patch = dict(build["variantInputs"])
                del missing_patch["candidate.patch"]
                receipt.write_text(json.dumps(build | {"variantInputs": missing_patch}))
                with self.assertRaisesRegex(ValueError, "build inputs"):
                    subjects(target)
                receipt.write_text(json.dumps(build))
                for path in (archive, compiler, canonical, warm, cold):
                    saved = path.read_bytes()
                    path.write_bytes(saved + b"altered")
                    with self.subTest(tampered=path), self.assertRaises(ValueError):
                        subjects(target)
                    path.write_bytes(saved)
                write_pe(warm, 0x8664, b"same-checkout")
                receipt.write_text(json.dumps(build | {"binary": sha(warm)}))
                with self.assertRaisesRegex(ValueError, "build inputs"):
                    subjects(target)
                build["binary"] = build["compilerEvidence"]["application"]["sha256"] = sha(warm)
                receipt.write_text(json.dumps(build))
                with self.assertRaisesRegex(ValueError, "same architecture"):
                    subjects(target)


class SubjectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.area = self.root / "warm"
        self.staged = self.area / "project/tools/rust-qa/gui"
        self.warm = self.area / "build/release/gui.exe"
        self.cold = self.root / "canonical/gui.exe"
        self.graph = self.cold.with_name("graph.json")
        self.record = self.area / "build.json"
        for path in (self.warm, self.cold, self.staged / "Cargo.lock", self.staged / "Cargo.toml",
                     self.staged / "src/main.rs", self.staged / "src/tray-icon.argb"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(path))
        sha = observe.recorder.sha
        target = "x86_64-pc-windows-msvc"
        packages, libraries, self.messages = [], {}, []
        for name, version, features in (("eframe", "0.37.0", ["accesskit"]), ("winit", "0.30.13", ["rwh_06"])):
            crate = "artifacts/retained/" + name
            unit = self.area / f"build/release/deps/lib{name}-123.rlib"
            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text("compiled " + name)
            manifest, source = crate + "/Cargo.toml", crate + "/src/lib.rs"
            packages.append(dict(name=name, version=version, archiveSha256=name + "-source", featureSets=[features]))
            libraries[name + "Unit"] = dict(manifest=manifest, crateRoot=source, features=features,
                                             outputs={unit.relative_to(self.area / "build").as_posix(): sha(unit)})
            self.messages.append(dict(reason="compiler-artifact", manifest_path=str(self.staged / manifest), features=features,
                                      target=dict(name=name, kind=["lib"], crate_types=["lib"], src_path=str(self.staged / source)),
                                      filenames=[str(unit)], executable=None))
        self.messages.append(dict(reason="build-finished", success=True))
        self.compiler_log = self.area / "compiler.jsonl"
        self.compiler_log.write_text("".join(json.dumps(row) + "\n" for row in self.messages))
        self.graph.write_text(json.dumps(dict(target=target, lockSha256="original-lock", packages=packages)))
        pins = dict(canonicalLockSha256="original-lock", retainedLockSha256=sha(self.staged / "Cargo.lock"),
                    retainedManifestSha256=sha(self.staged / "Cargo.toml"), archiveSha256="eframe-source")
        (self.area / "eframe-source.json").write_text(json.dumps(pins))
        winit_pins = dict(archiveSha256="winit-source")
        (self.area / "winit-source.json").write_text(json.dumps(winit_pins))
        fonts = {p.name: sha(p) for p in (observe.ROOT / "rust/assets/fonts").glob("*.ttf")}
        self.build = dict(baseline=sha(self.cold), binary=sha(self.warm), canonicalGraph=sha(self.graph),
                          canonicalLock="original-lock", lock=sha(self.staged / "Cargo.lock"), selectedFeatureRows=2,
                          variantInputs={"build.py": "paired"}, compilerInputs={p.name: sha(p) for p in (self.staged / "src").iterdir()},
                          eframeSource=dict(pins=pins, winitPins=winit_pins, archiveSha256="verified-archive"), **libraries,
                          compilerEvidence={"sha256": sha(self.compiler_log)}, baseFonts=fonts, fallbackFonts={"qa.ttf": "font"})
        self.canonical = dict(source="revision", binarySha256=sha(self.cold), graphSha256=sha(self.graph),
                              lockSha256="original-lock", fallbackFonts={"qa.ttf": {"sha256": "font"}})
        def subjects(_target, *, isolated_vm=False):
            paired = dict(target=target, revision="revision", buildReceipt=sha(self.record), baselineReceipt="canonical-receipt",
                          binary=sha(self.warm), baseline=sha(self.cold))
            return "verified native observer", self.cold, self.warm, self.area, paired
        loader = runpy.run_path
        (self.area / "compiler_units.py").write_bytes((retained_subject.WARM / "compiler_units.py").read_bytes())
        def load_module(path, run_name):
            return {"subjects": subjects} if Path(path) == self.area / "inputs.py" else loader(path, run_name=run_name)
        self.enterContext(patch.object(retained_subject, "WARM", self.area))
        self.enterContext(patch.object(retained_subject.runpy, "run_path", side_effect=load_module))
        self.target = target

    def select(self, record):
        self.record.write_text(json.dumps(record))
        return retained_subject.select(self.target, self.cold, self.canonical, self.graph, observe.recorder.sha)

    def test_selected_image_and_both_local_compiler_units_survive_staging(self):
        api, exe, evidence = self.select(self.build)
        self.assertEqual((api, exe), ("verified native observer", self.warm))
        self.assertEqual(evidence["eframeUnit"], self.build["eframeUnit"])
        self.assertEqual(evidence["winitUnit"], self.build["winitUnit"])
        self.assertEqual(evidence["compilerEvidence"], self.build["compilerEvidence"])
        self.assertEqual(evidence["baselineReceipt"], "canonical-receipt")
        self.assertNotEqual(evidence["binary"], evidence["baseline"])

    def test_crossed_locks_graph_sources_feature_sets_library_and_baseline_are_rejected(self):
        for key, new in (("lock", "other"), ("canonicalGraph", "other"), ("selectedFeatureRows", 3), ("fallbackFonts", {}),
                         ("compilerInputs", {}), ("binary", self.build["baseline"])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.select(self.build | {key: new})
        for library in ("eframeUnit", "winitUnit"):
            for key, new in (("manifest", "not-the-local-override"), ("features", ["other"]), ("outputs", {}),
                             ("outputs", {"../foreign.rlib": "other"})):
                record = copy.deepcopy(self.build)
                record[library][key] = new
                with self.subTest(library=library, key=key), self.assertRaises(ValueError):
                    self.select(record)
        (self.area / "build/release/deps/libwinit-123.rlib").write_text("replaced compiler output")
        with self.assertRaisesRegex(ValueError, "compiler output"):
            self.select(self.build)

    def test_registry_winit_in_compiler_log_fails_even_with_matching_local_receipt(self):
        self.messages[1]["manifest_path"] = str(self.root / "registry/winit/Cargo.toml")
        self.compiler_log.write_text("".join(json.dumps(row) + "\n" for row in self.messages))
        with self.assertRaisesRegex(ValueError, "winit"):
            self.select(self.build)


if __name__ == "__main__":
    unittest.main()
