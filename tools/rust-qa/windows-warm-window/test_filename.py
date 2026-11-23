"""Portable rejection controls for the reopened native filename assessment."""
from contextlib import nullcontext
from copy import deepcopy
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import filename
import observe
from filename import check_desktop, check_lifetime, check_sources, exercise_reopened, readback, sha, text

TARGET = "x86_64-pc-windows-msvc"
IMAGE = f"artifacts/rust/windows-warm-window/{TARGET}/build/release/native-gui-assessment.exe"

def console(name="Default", session=2):
    return dict(windowStation="WinSta0", stationVisible=True, session=session, activeConsoleSession=session,
                wts=dict(session=session, connectionState=0, lockFlags=1), threadDesktop=name, inputDesktop=name,
                inputObjectReceivesInput=True, threadReceivesInput=True)


def native_case():
    generation = ["GRAPHICS_READY generation=1"]
    case = dict(case="retained-filename", phase="complete", pid=17, creation100ns=844, exitCode=0, singleWake=False,
                transitions=[dict(hidden=42, reopened=42, generationBefore=generation, generationAfter=generation,
                                  windowEventRange=[1, 3], lifetimeStart=1, lifetimeEnd=2)],
                windowEvents=[dict(hwnd=42, root=True, event=action) for action in ("show", "hide", "show")],
                objectLifetimes=[[42, "create", 5], [31, "destroy", 6], [42, "destroy", 11]])
    observed = dict(pid=17, creation100ns=844, hwnd=42, image=IMAGE, imageSha256="warm", desktop=console(),
                    endingDesktop=console(), window=dict(pid=17, hwnd=hex(42), tid=37, session=2,
                    threadDesktop="Default", visible=True, iconic=False))
    return case, observed


class RetainedFilenameTests(unittest.TestCase):
    def test_controller_and_subject_use_one_unlocked_input_desktop_until_the_end(self):
        _, subject = native_case()
        for name in ("Default", "IfwQa_" + "a" * 32):
            accepted = dict(subject, desktop=console(name), endingDesktop=console(name),
                            window=dict(subject["window"], threadDesktop=name))
            check_desktop(accepted)
        for name in ("desktop", "endingDesktop", "window"):
            incomplete = dict(subject)
            del incomplete[name]
            with self.subTest(missing=name), self.assertRaises(KeyError):
                check_desktop(incomplete)
        for field, values in (("desktop", {"inputDesktop": "Winlogon"}), ("desktop", {"stationVisible": False}),
                              ("desktop", {"threadReceivesInput": False}), ("desktop", {"wts": {"lockFlags": 0}}),
                              ("endingDesktop", console("Other")), ("endingDesktop", console(session=4)),
                              ("endingDesktop", {"inputObjectReceivesInput": False}),
                              ("endingDesktop", {"activeConsoleSession": 0}),
                              ("window", {"hwnd": hex(87)}), ("window", {"pid": 7}), ("window", {"tid": 0}),
                              ("window", {"threadDesktop": "Other"}), ("window", {"session": 6}),
                              ("window", {"visible": False}), ("window", {"iconic": True})):
            changed = deepcopy(subject)
            changed[field].update(values)
            with self.subTest(field=field, values=values), self.assertRaises(ValueError):
                check_desktop(changed)
        unknown = dict(subject, desktop=console("Other"), endingDesktop=console("Other"),
                       window=dict(subject["window"], threadDesktop="Other"))
        with self.assertRaises(ValueError):
            check_desktop(unknown)

    def test_live_observer_saves_the_real_ending_context_and_keeps_a_completed_edit(self):
        _, subject = native_case()
        ending = dict(console(), inputDesktop="Winlogon", inputObjectReceivesInput=False)
        desk = Mock(context=Mock(return_value=ending), observed=Mock(return_value={"subject": subject["window"]}))
        helper = text["exercise_window"]
        report = {}
        def assessed(_record, _out, _pid, _hwnd, result):
            result["editingPassed"] = ["previously observed edit"]
        with (patch.dict(helper.__globals__, powershell=lambda *args: 0, read=lambda _: {}, evaluate=assessed),
              self.assertRaisesRegex(RuntimeError, "active desktop changed")):
            helper(desk, console(), 17, 42, {}, "PowerShell", Path("evidence"), report)
        self.assertEqual(report["endingDesktop"], ending)
        self.assertEqual(report["window"], subject["window"])
        self.assertEqual(report["editingPassed"], ["previously observed edit"])

    def test_sources_require_one_complete_checkout_with_its_original_git_filters(self):
        paths = ["one.py", "two.ps1"]
        revision = "a" * 40
        def checkout(cmd, cwd):
            self.assertIn("--attr-source=" + revision, cmd)
            self.assertEqual(cmd[-3:-1], ["cat-file", "--filters"])
            path = cmd[-1].removeprefix(revision + ":")
            return (path + ("\r\n" if "core.autocrlf=true" in cmd else "\n")).encode()
        lf, crlf = [{p: hashlib.sha256((p + eol).encode()).hexdigest() for p in paths} for eol in ("\n", "\r\n")]
        with patch.object(filename, "observer_paths", return_value=paths), patch.object(filename.subprocess, "check_output", checkout):
            for record in (lf, crlf):
                check_sources(revision, record)
            for invalid in ({}, {**lf, "missing.py": "0" * 64}, {**lf, "one.py": crlf["one.py"]},
                            {**lf, "two.ps1": "0" * 64}):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    check_sources(revision, invalid)
    def test_exact_native_process_and_reopened_hwnd(self):
        case, subject = native_case()
        check_lifetime(case, subject, TARGET, "warm")
        for key, value in (("pid", 18), ("creation100ns", 845), ("hwnd", 43), ("imageSha256", "cold"),
                           ("image", "artifacts/rust/gui-build/release/native-gui-assessment.exe")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_lifetime(case, dict(subject, **{key: value}), TARGET, "warm")
        with self.assertRaises(ValueError):
            check_lifetime(case, subject, "aarch64-pc-windows-msvc", "warm")

    def test_requires_ordered_root_events_and_a_positive_object_lifetime(self):
        case, subject = native_case()
        for change in ("replacedWindow", "replacedDevice", "foreignHide", "reversed", "noHook",
                       "recycled", "lateCreate", "earlyDestroy", "escapedRange", "failedDrain"):
            c = deepcopy(case)
            transition = c["transitions"][0]
            if change == "replacedWindow":
                transition["reopened"] = 43
            elif change == "replacedDevice":
                transition["generationAfter"] = ["GRAPHICS_READY generation=2"]
            elif change == "foreignHide":
                c["windowEvents"][1]["root"] = False
            elif change == "reversed":
                c["windowEvents"][1:3] = reversed(c["windowEvents"][1:3])
            elif change == "noHook":
                c["objectLifetimes"] = []
            elif change == "recycled":
                c["objectLifetimes"][1] = [42, "create", 7]
            elif change == "lateCreate":
                transition["lifetimeStart"] = 0
            elif change == "earlyDestroy":
                transition["lifetimeEnd"] = 3
            elif change == "escapedRange":
                transition["windowEventRange"] = [1, 4]
            else:
                c["exitCode"] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_lifetime(c, subject, TARGET, "warm")

    def test_retains_partial_edits_and_checks_loaded_image_before_sending_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "native-gui-assessment.exe"
            exe.write_bytes(b"pinned retained executable")
            proc = Mock(pid=17, _handle=193)
            def load_image(handle, _flags, name, _capacity):
                self.assertEqual(handle, 193)
                name.value = str(exe)
                return True
            def partial_edit(_desk, _context, _pid, _hwnd, _env, _ps, _out, result):
                result.update(editingPassed=["completed"], issues=["glyphs"])
                raise RuntimeError("observed partial filename result")
            editor = Mock(side_effect=partial_edit)
            observed = {"status": "failed"}
            with patch.object(filename, "ROOT", root), patch.dict(
                    text, exercise_window=editor, select_powershell=lambda *a, **kw: ("observer", [])):
                desk = Mock(image=load_image, context=Mock(return_value=console()))
                options = dict(api=Mock(process_identity=lambda h: 844), desk=desk, binary=exe, output=root, observed=observed)
                exercise_reopened(proc, 42, {}, expected_hash=sha(exe), **options)
                self.assertEqual(observed["status"], "failed")
                self.assertEqual(observed["editingPassed"], ["completed"])
                self.assertIn("observed partial filename result", observed["error"])
                exercise_reopened(proc, 42, {}, expected_hash="a different PE", **options)
                self.assertIn("did not load the pinned retained executable", observed["error"])
                desk.context.return_value = dict(console(), inputDesktop="Winlogon")
                exercise_reopened(proc, 42, {}, expected_hash=sha(exe), **options)
                self.assertEqual(observed["status"], "unavailable")
                editor.assert_called_once()

    def test_lost_reopened_hwnd_retains_actual_hooks_and_primary_error_through_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "capture"
            result, events, objects = {}, [], [[42, "create", 5]]
            proc = Mock(pid=17, returncode=None)
            proc.poll.return_value = None
            api = Mock(process_identity=Mock(return_value=844))
            api.close.side_effect = OSError("independent cleanup failure")
            windows = Mock(events=events)
            state = {"hwnd": 42}
            windows.visible.side_effect = lambda *_a: state["hwnd"]
            windows.is_visible.side_effect = lambda hwnd: state["hwnd"] == hwnd
            def owned(_hwnd, owner):
                ctypes.cast(owner, ctypes.POINTER(wintypes.DWORD)).contents.value = 17
                return 37
            def caption(_hwnd, dest, _size):
                dest.value = "fixture"
                return len(dest.value)
            windows.owner.side_effect = owned
            windows.caption.side_effect = caption
            def visibility(hwnd, kind):
                state["hwnd"] = hwnd if kind == "show" else None
                events.append(dict(hwnd=hwnd, root=True, event=kind))
            windows.close_window.side_effect = lambda hwnd: visibility(hwnd, "hide")
            def command(data):
                if data == b"T":
                    (out / "subject.log").write_text("READY Visible Available\nADAPTER Dx12 test\nGRAPHICS_READY generation=1\n")
                    visibility(42, "show")
                elif data == b"O":
                    visibility(42, "show")
            proc.stdin.write.side_effect = command
            def lost(_proc, hwnd, _env):
                self.assertEqual(hwnd, 42)
                objects.append([42, "destroy", 11])
                visibility(43, "show")
            def stop(child, rust):
                self.assertTrue(rust)
                child.returncode = 0
            lifetime = Mock(events=objects)
            fixture = Mock(TITLE="fixture", Windows=Mock(return_value=windows))
            with (patch.dict(os.environ, RUNNER_TEMP=tmp),
                  patch.object(observe, "owned_directory", return_value=nullcontext(root)),
                  patch.object(observe.subprocess, "Popen", return_value=proc),
                  patch.object(observe, "WindowLifetime", return_value=lifetime),
                  patch.object(observe.recorder, "stop_subject", side_effect=stop) as cleanup,
                  self.assertRaisesRegex(OSError, "independent cleanup failure")):
                observe.drive(api, fixture, root / "gui.exe", out, "retained-filename", after_reopen=lost, evidence=result)
            self.assertEqual((result["pid"], result["creation100ns"], result["phase"]), (17, 844, "validate reopened HWND"))
            self.assertIn("reopened HWND changed", result["failure"])
            self.assertEqual(result["transitions"][0]["windowEventRange"], [1, 3])
            self.assertEqual(result["objectLifetimes"], [[42, "create", 5], [42, "destroy", 11]])
            self.assertEqual([e["hwnd"] for e in result["windowEvents"]], [42, 42, 42, 43])
            self.assertEqual(result["subjectLog"], sha(out / "subject.log"))
            self.assertEqual(result["exitCode"], 0)
            cleanup.assert_called_once_with(proc, True)
            windows.close.assert_called_once()
            lifetime.close.assert_called_once()

    def test_detached_compiler_and_ordinary_observer_must_belong_to_the_same_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            warm = base / "windows-warm-window" / TARGET
            out = warm / "windows-text"
            cold = base / "gui-native" / TARGET
            (out / "lifecycle").mkdir(parents=True)
            cold.mkdir(parents=True)
            def save(path, obj):
                path.write_text(json.dumps(obj), encoding="utf-8")
            save(cold / "graph.json", dict(target=TARGET, lockSha256="canonical-lock"))
            graph = sha(cold / "graph.json")
            save(cold / "build.json", dict(target=TARGET, source="revision", binarySha256="cold", graphSha256=graph,
                                          lockSha256="canonical-lock", fallbackFonts={"fallback": {"sha256": "font"}}))
            (warm / "compiler.jsonl").write_bytes(b"original native compiler stream")
            (warm / "eframe-source.zip").write_bytes(b"reviewed retained source")
            compiler = dict(sha256=sha(warm / "compiler.jsonl"), application=dict(sha256="warm"))
            cold_receipt = sha(cold / "build.json")
            claims = dict(compilerEvidence=compiler, canonicalGraph=graph, lock="retained-lock", selectedFeatureRows=400,
                          eframeSource=dict(archiveSha256=sha(warm / "eframe-source.zip")), baseFonts={"base": "other-font"},
                          fallbackFonts={"fallback": "font"}, eframeUnit={"outputs": {"libeframe.rlib": "eframe"}},
                          winitUnit={"outputs": {"libwinit.rlib": "winit"}}, compilerInputs={"main.rs": "app"},
                          variantInputs={"build.py": "builder"})
            save(warm / "build.json", dict(target=TARGET, revision="revision", baseline="cold", binary="warm",
                                          canonicalLock="canonical-lock", baselineReceipt=cold_receipt, **claims))
            retained = dict(target=TARGET, revision="revision", run="72", attempt="1", baseline="cold", binary="warm",
                            buildReceipt=sha(warm / "build.json"), baselineReceipt=cold_receipt, **claims)
            case, observed = native_case()
            observed.update(status="passed", observerExit=0, windowReadback=["masks"], editingPassed=["edits"], issues=[])
            log = out / "lifecycle/subject.log"
            log.write_text("GRAPHICS_MEMORY generation=1 hint=MemoryUsage\nGRAPHICS_READY generation=1\n"
                           "GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Fifo, Mailbox]\n"
                           "GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode=Mailbox latency=Some(1)\n"
                           "GRAPHICS_DX12_WAIT generation=1 policy=Wait\nDRAINED passes=1\n", encoding="utf-8")
            case["subjectLog"] = sha(log)
            save(out / "plan.json", text["PLAN"])
            save(out / "observations.json", {"pid": 17, "hwnd": 42})
            report = dict(subject="retained", target=TARGET, run="72", attempt="1", lifecycle=case, text=observed,
                          inputs={"observer.py": "source"},
                          canonical=dict(target=TARGET, source="revision", binarySha256="cold", receiptSha256=cold_receipt,
                                         graphSha256=graph),
                          retained=retained, device=dict(generation=1, memoryHint="MemoryUsage", presentMode="Mailbox",
                          offered=["Fifo", "Mailbox"], desiredMaximumFrameLatency=1, waitPolicy="Wait"))
            def assess(record, path, pid, hwnd, derived):
                self.assertEqual((record, path, pid, hwnd), ({"pid": 17, "hwnd": 42}, out, 17, 42))
                derived.update(windowReadback=["masks"], editingPassed=["edits"], issues=[])
            def source_check(revision, recorded):
                if (revision, recorded) != ("revision", {"observer.py": "source"}):
                    raise ValueError("observer source mismatch")
            with patch.dict(text, evaluate=assess), patch.object(filename, "check_sources", source_check):
                readback(out, TARGET, report)
                changed = deepcopy(report)
                changed["text"]["editingPassed"] = []
                with self.assertRaisesRegex(ValueError, "original captures"):
                    readback(out, TARGET, changed)
                for key in claims:
                    changed = deepcopy(report)
                    changed["retained"][key] = {}
                    with self.subTest(key=key), self.assertRaisesRegex(ValueError, "originating build"):
                        readback(out, TARGET, changed)
                for key in ("desktop", "window", "endingDesktop"):
                    changed = deepcopy(report)
                    del changed["text"][key]
                    with self.subTest(key=key), self.assertRaises(KeyError):
                        readback(out, TARGET, changed)
                with self.assertRaisesRegex(ValueError, "observer source"):
                    readback(out, TARGET, dict(report, inputs={}))
                (warm / "compiler.jsonl").write_bytes(b"different compiler stream")
                with self.assertRaisesRegex(ValueError, "originating build"):
                    readback(out, TARGET, report)


if __name__ == "__main__":
    unittest.main()
