"""Portable source, budget and resident-page classification checks for the Windows comparison."""
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

import inputs
import measure
import residency
from scan_present import correlate

spec = importlib.util.spec_from_file_location("warm_builder", inputs.HERE / "build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WarmTests(unittest.TestCase):
    def test_compiler_reports_the_actual_local_binary_and_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            gui, exe = Path(tmp) / "gui", Path(tmp) / "native-gui-assessment.exe"
            exe.write_bytes(b"test executable")
            target = {"kind": ["bin"], "crate_types": ["bin"], "name": "native-gui-assessment",
                      "src_path": str(gui / "src/main.rs")}
            unit = {"reason": "compiler-artifact", "manifest_path": str(gui / "Cargo.toml"),
                    "target": target, "executable": str(exe), "filenames": [str(exe)]}
            library = {**unit, "target": {**target, "kind": ["lib"]}, "executable": None, "filenames": []}
            expected = {"target": target["name"], "crateRoot": "src/main.rs", "output": exe.name, "sha256": builder.sha(exe)}
            self.assertEqual(builder.application_artifact([library, unit], gui, exe), expected)
            for units in ([library], [unit, unit], [{**unit, "filenames": []}], [{**unit, "filenames": [str(exe)] * 2}],
                          [{**unit, "executable": None}], [{**unit, "executable": str(gui / exe.name)}],
                          [{**unit, "manifest_path": str(exe.parent / "Cargo.toml")}],
                          [{**unit, "target": {**target, "src_path": str(gui / "src/lib.rs")}}],
                          [{**unit, "target": {**target, "name": "other-binary"}}]):
                with self.subTest(units=units), self.assertRaises(ValueError):
                    builder.application_artifact(units, gui, exe)

    def test_all_compiled_features_and_source_identities_must_match_the_retained_graph(self):
        registry = "registry+https://github.com/rust-lang/crates.io-index"
        with tempfile.TemporaryDirectory() as temp:
            gui = Path(temp) / "project/tools/rust-qa/gui"
            gui.mkdir(parents=True)
            (gui / "Cargo.lock").write_text(
                f'[[package]]\nname="windows"\nversion="0.62.2"\nsource="{registry}"\n'
                '[[package]]\nname="eframe"\nversion="0.37.0"\n', encoding="utf-8")
            eframe = gui / builder.eframe_source.PACKAGE
            local = {"reason": "compiler-artifact", "package_id": "path+" + eframe.as_uri() + "#0.37.0",
                     "manifest_path": str(eframe / "Cargo.toml"), "features": ["wgpu_no_default_features"]}
            win = {"reason": "compiler-artifact", "package_id": registry + "#windows@0.62.2", "features": ["std"]}
            finished = {"reason": "build-finished", "success": True}
            selected = [("windows", "0.62.2", ("std",)), ("eframe", "0.37.0", ("wgpu_no_default_features",))]
            self.assertEqual(builder.compiler_graph([local, win, win, finished], gui, selected),
                             {"units": 3, "featureSets": 2, "packages": 2})
            for changed in ([], [local, finished], [local, win], [local, win, finished, finished],
                            [finished, local, win],
                            [local, win, {**finished, "success": False}],
                            [local, {**win, "features": []}, finished],
                            [local, {**win, "package_id": "path+file:///unreviewed#windows@0.62.2"}, finished],
                            [local, {**win, "package_id": registry + "#windows@0.62.1"}, finished],
                            [{**local, "manifest_path": str(gui / "Cargo.toml")}, win, finished]):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    builder.compiler_graph(changed, gui, selected)

    def test_timed_trial_requires_one_memory_usage_device_and_no_allocator_sampling(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "trial.log"
            device = ("GRAPHICS_MEMORY generation=1 hint=MemoryUsage\nGRAPHICS_READY generation=1\n"
                      "GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Mailbox, Fifo]\n"
                      "GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode=Mailbox latency=Some(1)\n")
            log.write_text(device)
            self.assertEqual(measure.measured_generation(log, "Mailbox")["memoryHint"], "MemoryUsage")
            for invalid in (device.replace("MemoryUsage", "Performance"), device + "GRAPHICS_READY generation=2\n",
                            device + "WGPU_ALLOCATOR unavailable\n"):
                log.write_text(invalid)
                with self.assertRaisesRegex(ValueError, "single warm MemoryUsage"):
                    measure.measured_generation(log, "Mailbox")
            for invalid in (device.replace("[Mailbox, Fifo]", "[Fifo]"), device.replace("Some(1)", "Some(2)"),
                            device.replace("mode=Mailbox", "mode=Fifo")):
                log.write_text(invalid)
                with self.assertRaisesRegex(ValueError, "supported presentation mode"):
                    measure.measured_generation(log, "Mailbox")

    def test_only_owned_non_tearing_presents_on_the_same_work_clock_can_supply_the_comparison(self):
        requests = [dict(action="reopen" if i % 2 == 0 else "close", issuedQpc=20 + 10 * i, responseQpc=25 + 10 * i)
                    for i in range(15)]
        inventory = dict(passes=[dict(firstFileQpc=10, lastFileQpc=200)], eligibleResponses=requests)
        # Every close overlaps one 4 ms present for 3 ms. Reopens share no present call.
        rows = [f"DXGI 42 7 0 0 {32 + 20 * i} {36 + 20 * i}" for i in range(7)]
        trace = "\n".join(["READY", "QPC 42 1000", *rows, "COMPLETE"])

        def read(text, mode="Mailbox"):
            return correlate(text, 42, 1000, [8, 205], inventory, mode)

        result = read(trace)
        self.assertEqual((result["successfulPresents"], result["presentP95Ms"]), (7, 4))
        self.assertEqual(result["actions"]["close"], dict(requests=7, requestsIntersectingPresent=7, longestPresentOverlapP95Ms=3))
        self.assertEqual(result["actions"]["reopen"]["requestsIntersectingPresent"], 0)
        self.assertEqual(read(trace.replace("42 7 0 0", "42 7 1 0"), "Fifo")["syncInterval"], 1)
        for invalid in (trace.replace("QPC 42", "QPC 7"), trace.replace("QPC 42 1000", "QPC 42 2000"),
                        trace.replace("DXGI 42", "DXGI 7"), trace.replace("42 7 0 0", "42 7 1 0"),
                        trace.replace("42 7 0 0", "42 7 0 512"), trace.replace("42 7 0 0", "42 7 0 1"),
                        trace.replace("32 36", "4 36"), trace.replace("COMPLETE", "TRACE_ERROR"),
                        "\n".join(["READY", "QPC 42 1000", *rows[:3], "COMPLETE"])):
            with self.assertRaises(ValueError):
                read(invalid)

    def test_staging_preserves_the_shared_inputs(self):
        if not (builder.GUI / "artifacts/text/egui").is_dir():
            self.skipTest("requires the reconstructed canonical GUI inputs")
        with tempfile.TemporaryDirectory() as temp:
            gui = builder.stage(Path(temp) / "stage")
            builder.eframe_source.verify_lock(gui, json.loads(builder.eframe_source.PINS.read_bytes()))
            for name in ("src/windows_worker.rs", "src/windows_tray.rs", "src/windows_tray_state.rs",
                         "src/windows_tray_shell.rs", "src/fonts.rs", "src/linux.rs", "src/tray-icon.argb"):
                self.assertEqual(builder.sha(builder.GUI / name), builder.sha(gui / name))
            self.assertEqual(builder.sha(gui / "src/loop_wake.rs"), builder.sha(builder.HERE / "loop_wake.rs"))
            self.assertEqual(builder.sha(gui / "src/windows_present.rs"), builder.sha(builder.HERE / "windows_present.rs"))
            for name, digest in builder.ORIGINALS.items():
                self.assertEqual(builder.sha(builder.GUI / "src" / name), digest)
                self.assertNotEqual(builder.sha(gui / "src" / name), digest)

    def test_retained_source_archive_replays_identically_and_preserves_original_notices(self):
        if not (builder.GUI / "artifacts/text/egui").is_dir():
            self.skipTest("requires the reconstructed canonical GUI inputs")
        source = builder.eframe_source
        pins = json.loads(source.PINS.read_bytes())
        winit = json.loads(source.WINIT_PINS.read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archives = []
            for name in ("first", "second"):
                gui = builder.stage(root / name / "project")
                archive = root / name / "eframe-source.zip"
                receipt = source.source_bundle(gui, archive)
                self.assertEqual(receipt, {"pins": pins, "winitPins": winit, "archive": archive.name,
                                           "archiveSha256": builder.sha(archive)})
                archives.append(archive)
            self.assertEqual(archives[0].read_bytes(), archives[1].read_bytes())
            expected = {"pins.json": source.PINS, source.PATCH.name: source.PATCH,
                        source.APPLICATION_PATCH.name: source.APPLICATION_PATCH, "winit-pins.json": source.WINIT_PINS,
                        source.WINIT_PATCH.name: source.WINIT_PATCH, "notices/winit/LICENSE": gui / source.WINIT_PACKAGE / "LICENSE"}
            for family, folder in (("canonical", builder.GUI), ("retained", gui)):
                for filename in ("Cargo.lock", "Cargo.toml"):
                    expected[family + "/" + filename] = folder / filename
            for filename, evidence in pins["notices"].items():
                expected["notices/" + filename] = builder.ROOT / evidence["path"]
            packages = {review["crate"] + ".crate": review["archiveSha256"] for review in (pins, winit)}
            with ZipFile(archives[0]) as bundle:
                self.assertEqual(bundle.namelist(), sorted([*packages, *expected]))
                for package, digest in packages.items():
                    self.assertEqual(hashlib.sha256(bundle.read(package)).hexdigest(), digest)
                for member, original in expected.items():
                    self.assertEqual(bundle.read(member), original.read_bytes(), member)
            window_state = gui / source.WINIT_PACKAGE / "src/platform_impl/windows/window_state.rs"
            reviewed = window_state.read_bytes()
            window_state.write_bytes(reviewed + b"// Unreviewed native source change\n")
            with self.assertRaisesRegex(ValueError, "winit source changed during compilation"):
                source.source_bundle(gui, root / "wrong.zip")
            window_state.write_bytes(reviewed)
            changed_notice = root / "changed-notice"
            changed_notice.write_text("Changed license text", encoding="utf-8")
            pins["notices"]["eframe/LICENSE-MIT"]["path"] = str(changed_notice)
            changed_pins = root / "pins.json"
            changed_pins.write_text(json.dumps(pins), encoding="utf-8")
            with patch.object(source, "PINS", changed_pins), self.assertRaisesRegex(ValueError, "Changed source input"):
                source.source_bundle(gui, root / "wrong.zip")
            (gui / source.PACKAGE / "src/lib.rs").write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "changed during compilation"):
                source.source_bundle(gui, root / "wrong.zip")
            self.assertFalse((root / "wrong.zip").exists())
            lock = gui / "Cargo.lock"
            lock.write_bytes(lock.read_bytes().replace(b'version = 4\n', b'version = 3\n', 1))
            pins["retainedLockSha256"] = builder.sha(lock)
            with self.assertRaisesRegex(ValueError, "registry identity"):
                source.verify_lock(gui, pins)

    def test_reconstruction_rejects_changed_archive_patch_or_unreviewed_source_digest(self):
        source = builder.eframe_source
        pins = json.loads(source.PINS.read_bytes())
        try:
            archive = source.original_archive(pins)
        except FileNotFoundError:
            self.skipTest("requires the original native GUI crate cache")
        patch = source.PATCH.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "eframe"
            for inputs in ((archive + b"changed", patch), (archive, patch + b"changed")):
                with self.assertRaisesRegex(ValueError, "archive or retained source patch"):
                    source.reconstruct(dest, pins, *inputs)
                self.assertFalse(dest.exists())
            pins["modified"].pop("src/epi.rs")
            with self.assertRaisesRegex(ValueError, "Unexpected modified eframe compiler sources"):
                source.reconstruct(dest, pins, archive, patch)

    def test_reconstructed_winit_policy_uses_real_flag_definitions_and_updates_its_cache(self):
        source = builder.eframe_source
        pins = json.loads(source.WINIT_PINS.read_bytes())
        try:
            archive = source.original_archive(pins)
        except FileNotFoundError:
            self.skipTest("requires the original native GUI crate cache")
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            winit = work / "winit"
            source.reconstruct(winit, pins, archive, source.WINIT_PATCH.read_bytes())
            code = (winit / "src/platform_impl/windows/window_state.rs").read_text(encoding="utf-8")
            self.assertEqual(builder.sha(winit / pins["licenseFile"]), pins["licenseSha256"])
            # Compile the real flags, style mapping and state changes against a recording User32 stand-in.
            start = code.rindex("bitflags!", 0, code.index("pub struct WindowFlags"))
            flags = code[start:code.index("\n}", start) + 2]

            def method(signature):
                begin = code.index(signature)
                return code[begin:code.index("\n    }\n", begin) + 6]

            state = method("    pub fn set_window_flags<F>")
            command = method("    fn retained_visibility(")
            styles = method("    pub fn to_window_styles(")
            src = work / "src"
            src.mkdir()
            (src / "winit_policy.rs").write_text(
                f"{flags}\nimpl WindowState {{\n{state}\n}}\nimpl WindowFlags {{\n{command}\n{styles}\n}}\n", encoding="utf-8")
            (src / "lib.rs").write_bytes((inputs.HERE / "visibility_controls.rs").read_bytes())
            packages = tomllib.loads((builder.GUI / "Cargo.lock").read_text(encoding="utf-8"))["package"]
            native_winit, = [p for p in packages if p["name"] == "winit" and p["version"] == "0.30.13"]
            def winit_version(name):
                dependency, = [dep for dep in native_winit["dependencies"] if dep.startswith(name + " ")]
                return dependency.split()[1]

            (work / "Cargo.toml").write_text(
                '[package]\nname="retained-visibility-controls"\nversion="0.0.0"\nedition="2024"\n'
                f'[workspace]\n[dependencies]\nbitflags="={winit_version("bitflags")}"\n'
                f'[dependencies.windows-sys]\nversion="={winit_version("windows-sys")}"\n'
                'features=["Win32_UI_WindowsAndMessaging"]\n', encoding="utf-8")
            toolchain = builder.ROOT / "artifacts/rust/toolchain/bin"
            cargo = str(toolchain / ("cargo.exe" if os.name == "nt" else "cargo"))
            env = dict(os.environ, PATH=str(toolchain) + os.pathsep + os.environ["PATH"],
                       CARGO_HOME=str(builder.ROOT / "artifacts/rust/assessment-cache"), CARGO_TARGET_DIR=str(work / "target"))
            subprocess.run([cargo, "generate-lockfile", "--offline"], cwd=work, env=env, check=True)
            selected = tomllib.loads((work / "Cargo.lock").read_text(encoding="utf-8"))["package"]
            registry = {(p["name"], p["version"]): (p["source"], p["checksum"]) for p in packages if "source" in p}
            for dep in selected:
                if dep["name"] != "retained-visibility-controls":
                    self.assertEqual((dep["source"], dep["checksum"]), registry[dep["name"], dep["version"]])
            subprocess.run([cargo, "test", "--lib", "--frozen", "--quiet"], cwd=work, env=env, check=True)

    def test_compiler_receipt_requires_the_staged_library_sources_features_and_outputs(self):
        source = builder.eframe_source
        with tempfile.TemporaryDirectory() as temp:
            gui = Path(temp) / "gui"
            build = Path(temp) / "build"
            build.mkdir()
            finished = {"reason": "build-finished", "success": True}
            for package, features in ((source.PACKAGE, ["accesskit", "clipboard", "wgpu_no_default_features"]),
                                      (source.WINIT_PACKAGE, ["rwh_06"])):
                rlib = build / ("lib" + package.name + ".rlib")
                rlib.write_bytes(b"compiler test fixture")
                unit = {"reason": "compiler-artifact", "manifest_path": str(gui / package / "Cargo.toml"),
                        "target": {"name": package.name, "kind": ["lib"], "src_path": str(gui / package / "src/lib.rs")},
                        "features": features, "filenames": [str(rlib)]}
                result = builder.compiled_library([unit, finished], gui, build, package, features)
                self.assertEqual(result["outputs"], {rlib.name: builder.sha(rlib)})
                for messages in ([finished], [unit, unit, finished], [unit, dict(finished, success=False)],
                                 [dict(unit, manifest_path=str(gui / "Cargo.toml")), finished],
                                 [dict(unit, target=dict(unit["target"], kind=["custom-build"])), finished],
                                 [dict(unit, target=dict(unit["target"], src_path=str(gui / "registry/src/lib.rs"))), finished],
                                 [dict(unit, features=[*features, "unexpected"]), finished],
                                 [dict(unit, filenames=[str(rlib), str(rlib)]), finished],
                                 [dict(unit, filenames=[str(build / "libother.rlib")]), finished],
                                 [dict(unit, filenames=[str(gui / "elsewhere.rlib")]), finished]):
                    with self.assertRaises(ValueError):
                        builder.compiled_library(messages, gui, build, package, features)

    def test_resident_pages_are_counted_once_with_image_ownership(self):
        api = Mock()
        def working(proc, blocks, size):
            blocks[0:5] = (4, 1 << 12, 2 << 12, 3 << 12 | 0x100, 4 << 12)
            return True
        def region(proc, address, output, size):
            result = output._obj
            result.base = (address // 4096) * 4096
            result.size, result.state = 4096, 0x1000
            result.kind = {4096: 0x20000, 8192: 0x20000, 12288: 0x1000000, 16384: 0x40000}[address]
            result.allocation = result.base
            return c.sizeof(residency.Region)
        def mapped(proc, address, buffer, size):
            buffer.value = r"\Device\HarddiskVolume3\Windows\System32\d3d10warp.dll"
            return len(buffer.value)
        handlers = {"GetSystemInfo": lambda data: data.__setitem__(1, 4096), "K32QueryWorkingSet": working,
                    "VirtualQueryEx": region, "K32GetMappedFileNameW": mapped}
        with patch("native.bind", side_effect=lambda lib, name, *_: handlers[name]):
            found = residency.sample(api, 123)
        self.assertEqual(found["regionBytes"], {"private": 8192, "image": 4096, "mapped": 4096})
        self.assertEqual(found["imageBytes"], {"d3d10warp.dll": 4096})
        self.assertEqual(found["residentBytes"], 16384)
        self.assertEqual(found["shareableBytes"], 4096)

    def test_old_host_or_changed_budget_cannot_supply_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            where = root / "artifacts/rust/windows-performance/native-x86_64-pc-windows-msvc"
            where.mkdir(parents=True)
            env = {"COMPUTERNAME": "fixture", "ImageVersion": "test"}
            trials = [{"metrics": {"idle_close_p95_ms": 4}}] * 3
            baseline = {"target": inputs.TARGETS[0], "candidateRevision": "rev", "guiBinarySha256": "cold",
                        "guiReceiptSha256": "receipt", "referenceRevision": measure.REFERENCE,
                        "referenceSourceSha256": measure.REFERENCE_SOURCE_SHA256}
            meta = {"run": "1234", "attempt": "1", "revision": "rev", "baseline": "cold", "baselineReceipt": "receipt"}
            (where / "inputs.json").write_text(json.dumps(baseline))
            fixed = {"sourceInputsSha256": inputs.sha(where / "inputs.json"), "reference": {"idle_close_p95_ms": 4},
                     "maximums": {"idle_close_p95_ms": 14.0}}
            budget = where / "reference-budget.json"
            budget.write_text(json.dumps(fixed))
            host = {"host": {"run": "1234", "attempt": "1", "computerIdSha256": hashlib.sha256(b"fixture").hexdigest(),
                             "runnerImage": "test"}, "budgetSha256": inputs.sha(budget), "trials": {"wpf": trials}}
            (where / "result.json").write_text(json.dumps(host))
            with patch.object(measure, "ROOT", root), patch.dict(os.environ, env):
                self.assertEqual(measure.reference(inputs.TARGETS[0], meta)[1], fixed)
                with self.assertRaisesRegex(ValueError, "matching frozen WPF"):
                    measure.reference(inputs.TARGETS[0], {**meta, "attempt": "2"})
                fixed["maximums"]["idle_close_p95_ms"] = 150
                budget.write_text(json.dumps(fixed))
                with self.assertRaisesRegex(ValueError, "matching frozen WPF"):
                    measure.reference(inputs.TARGETS[0], meta)

    def test_fifo_can_report_a_full_over_budget_control_but_cannot_pair_different_or_missing_work(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mailbox.json"
            values = {key: {"candidate": 22.0, "maximum": 14.0, "passed": False} for key in measure.METRICS}
            common = dict(target=inputs.TARGETS[0], run="test", attempt="1", revision="rev", binary="bin",
                          buildReceipt="build", referenceBudgetSha256="budget", observerInputs={}, trials=[{}] * 3,
                          inputs={"workload": {"files": 100000}}, comparison=values)
            fifo = dict(common, presentMode="Fifo", diagnosticControl=True)
            mailbox = dict(common, presentMode="Mailbox", diagnosticControl=False)
            path.write_text(json.dumps(mailbox))
            self.assertEqual(measure.paired_scan(path, fifo)["metrics"]["Fifo"]["scan_close_p95_ms"], values["scan_close_p95_ms"])
            with self.assertRaisesRegex(ValueError, "different inputs"):
                measure.paired_scan(path, dict(fifo, binary="different"))
            with self.assertRaisesRegex(ValueError, "eleven measured"):
                measure.paired_scan(path, dict(fifo, comparison={**values, "startup_ms": {"passed": None}}))
            with self.assertRaisesRegex(ValueError, "different WPF"):
                measure.paired_scan(path, dict(fifo, comparison={**values, "scan_close_p95_ms": {**values["scan_close_p95_ms"], "maximum": 20}}))


if __name__ == "__main__":
    unittest.main()
