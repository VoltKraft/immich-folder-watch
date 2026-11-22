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
                         eframeSource={"archive": archive.name, "archiveSha256": sha(archive)}, variantInputs={},
                         compilerEvidence={"file": compiler.name, "sha256": sha(compiler)})
            receipt.write_text(json.dumps(build))
            with (patch.dict(subjects.__globals__, ROOT=root), patch.object(observe.recorder, "hosted", return_value=True),
                  patch.object(subprocess, "check_output", return_value="revision"), patch.object(observe.recorder, "Win32") as api):
                api.return_value.machine.return_value = (0xaa64, 0xaa64)
                self.assertEqual(subjects(target)[1:3], (cold, warm))
                for path in (archive, compiler, canonical, warm, cold):
                    saved = path.read_bytes()
                    path.write_bytes(saved + b"altered")
                    with self.subTest(tampered=path), self.assertRaises(ValueError):
                        subjects(target)
                    path.write_bytes(saved)
                write_pe(warm, 0x8664, b"same-checkout")
                receipt.write_text(json.dumps(build | {"binary": sha(warm)}))
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
        self.unit = self.area / "build/release/deps/libeframe-123.rlib"
        for path in (self.warm, self.cold, self.unit, self.staged / "Cargo.lock", self.staged / "Cargo.toml",
                     self.staged / "src/main.rs", self.staged / "src/tray-icon.argb"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(path))
        sha = observe.recorder.sha
        target = "x86_64-pc-windows-msvc"
        package = dict(name="eframe", version="0.37.0", archiveSha256="published-source", featureSets=[["accesskit"]])
        self.graph.write_text(json.dumps(dict(target=target, lockSha256="original-lock", packages=[package])))
        pins = dict(canonicalLockSha256="original-lock", retainedLockSha256=sha(self.staged / "Cargo.lock"),
                    retainedManifestSha256=sha(self.staged / "Cargo.toml"), archiveSha256="published-source")
        (self.area / "eframe-source.json").write_text(json.dumps(pins))
        compiler = dict(manifest="artifacts/retained/eframe/Cargo.toml", crateRoot="artifacts/retained/eframe/src/lib.rs",
                        features=["accesskit"], outputs={self.unit.relative_to(self.area / "build").as_posix(): sha(self.unit)})
        fonts = {p.name: sha(p) for p in (observe.ROOT / "rust/assets/fonts").glob("*.ttf")}
        self.build = dict(baseline=sha(self.cold), binary=sha(self.warm), canonicalGraph=sha(self.graph),
                          canonicalLock="original-lock", lock=sha(self.staged / "Cargo.lock"), selectedFeatureRows=1,
                          variantInputs={"build.py": "paired"}, compilerInputs={p.name: sha(p) for p in (self.staged / "src").iterdir()},
                          eframeSource=dict(pins=pins, archiveSha256="verified-archive"), eframeUnit=compiler,
                          compilerEvidence={"sha256": "paired-compiler-log"}, baseFonts=fonts, fallbackFonts={"qa.ttf": "font"})
        self.canonical = dict(source="revision", binarySha256=sha(self.cold), graphSha256=sha(self.graph),
                              lockSha256="original-lock", fallbackFonts={"qa.ttf": {"sha256": "font"}})
        def subjects(_target):
            paired = dict(target=target, revision="revision", buildReceipt=sha(self.record), baselineReceipt="canonical-receipt",
                          binary=sha(self.warm), baseline=sha(self.cold))
            return "verified native observer", self.cold, self.warm, self.area, paired
        self.enterContext(patch.object(retained_subject, "WARM", self.area))
        self.loader = self.enterContext(patch.object(retained_subject.runpy, "run_path", return_value={"subjects": subjects}))
        self.target = target

    def select(self, record):
        self.record.write_text(json.dumps(record))
        return retained_subject.select(self.target, self.cold, self.canonical, self.graph, observe.recorder.sha)

    def test_exact_selected_image_local_eframe_and_compiler_evidence_survive_staging(self):
        api, exe, evidence = self.select(self.build)
        self.loader.assert_called_once_with(str(self.area / "inputs.py"), run_name="ifw_launcher_retained_inputs")
        self.assertEqual((api, exe), ("verified native observer", self.warm))
        self.assertEqual(evidence["eframeUnit"], self.build["eframeUnit"])
        self.assertEqual(evidence["compilerEvidence"], self.build["compilerEvidence"])
        self.assertEqual(evidence["baselineReceipt"], "canonical-receipt")
        self.assertNotEqual(evidence["binary"], evidence["baseline"])

    def test_crossed_locks_graph_sources_feature_sets_library_and_baseline_are_rejected(self):
        for key, new in (("lock", "other"), ("canonicalGraph", "other"), ("selectedFeatureRows", 2), ("fallbackFonts", {}),
                         ("compilerInputs", {}), ("binary", self.build["baseline"])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.select(self.build | {key: new})
        for key, new in (("manifest", "not-the-local-override"), ("features", ["other"]), ("outputs", {}),
                         ("outputs", {"../foreign.rlib": "other"})):
            record = copy.deepcopy(self.build)
            record["eframeUnit"][key] = new
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.select(record)
        self.unit.write_text("replaced compiler output")
        with self.assertRaisesRegex(ValueError, "compiler output"):
            self.select(self.build)


if __name__ == "__main__":
    unittest.main()
