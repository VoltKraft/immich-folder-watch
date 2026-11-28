"""Exercise the measured boundaries with the existing synthetic ordinary-dispatch HWND controls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import readback
from test_dispatch import sample


def fixture(status=0, wait="dx12-wait", result=0, route="flag-show"):
    gui, dxgi, scan = sample(False)
    rows = []
    issued = 0

    def scope(label, start, end, *, parent=0, arg=0, answer=0, hwnd=0, children=None):
        nonlocal issued
        issued += 1
        ident = issued
        for ending, ticks in ((0, start), (1, end)):
            if ending and children:
                children(ident)
            ctx = 0 if status else ticks // 5
            reason = 0 if status else 4
            fields = (ident, parent, label, ending, 5, ticks, ticks, status, ctx, reason, ticks * 7,
                      answer if ending else arg, start if ending else 0, end if ending else 0, hwnd if ending else 0)
            rows.append("FRAME " + " ".join(map(str, fields)))

    for i in range(6):
        t = 100 * i + 10
        scope("hide-call", t + 2, t + 4, arg=9, children=lambda call:
              scope("direct", t + 2, t + 4, parent=call, arg=0, answer=1, hwnd=9))
        scope("show-call", t + 32, t + 48, arg=9, children=lambda call:
              scope("flags", t + 32, t + 48, parent=call, children=lambda flags:
                    scope(route, t + 33, t + 47, parent=flags, arg=5, answer=0, hwnd=9)))
        def frame(stamp):
            for label, a, b in (("update", 60, 61), ("tessellate", 61, 62), ("prepare", 62, 63),
                                ("acquire", 63, 64), ("draw", 64, 65), ("encode", 65, 66), ("submit", 66, 67), ("present", 68, 74)):
                nested = (lambda acq:scope(wait, t + 63, t + 64, parent=acq, arg=1000, answer=result)) if label == "acquire" else None
                scope(label, t + a, t + b, parent=stamp, children=nested)
        scope("frame", t + 60, t + 75, children=frame)
    text = "\n".join([gui, f"FRAME_BEGIN 42 1000 {len(rows)} 0", *rows, "FRAME_END"])
    return text, dxgi, scan, {"scan_close_p95_ms":1, "scan_reopen_p95_ms":1}


class FrameCost(unittest.TestCase):
    def test_native_wait_result_show_path_and_raw_counter_measurements(self):
        text, dxgi, scan, limits = fixture()
        result = readback.analyze(text, dxgi, scan, limits)
        self.assertEqual(result["waitResults"], {"0":6})
        self.assertEqual(result["visibilityPaths"], {"hide:direct":6, "show:flags-with-ShowWindow":6})
        self.assertEqual((result["verifiedPresentedFrames"], result["hidden"]["verifiedHiddenIntervals"]), (6, 6))
        self.assertTrue(result["schedulerComplete"])
        self.assertEqual(result["slowResponses"][0]["overlapMs"]["direct"], 2)
        nodes, _ = readback.read_spans(text, 42, 1000)
        direct = next(n for n in nodes.values() if n["stage"] == "direct")
        self.assertEqual((direct["arg"], direct["result"], direct["hwnd"], direct["cycles"], direct["reasons"]), (0, 1, 9, 14, 4))

    def test_denied_thread_profile_keeps_its_error_and_fallback_cycles(self):
        text, dxgi, scan, limits = fixture(status=5)
        result = readback.analyze(text, dxgi, scan, limits)
        self.assertFalse(result["schedulerComplete"])
        self.assertEqual(set(result["schedulerReadStatuses"]), {"5"})
        nodes, _ = readback.read_spans(text, 42, 1000)
        node = next(n for n in nodes.values() if n["stage"] == "direct")
        self.assertEqual((node["completeScheduler"], node["switches"], node["cycles"]), (False, None, 14))

    def test_rejects_incomplete_acquire_outside_present_or_wrong_visibility_path(self):
        for kw in ({"wait":"dx12-no-object"}, {"result":0xffffffff}, {"route":"flag-hide"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                readback.analyze(*fixture(**kw))
        text, dxgi, scan, limits = fixture()
        for bad in (text.replace(" dx12-wait ", " update "), text.replace(" submit ", " encode "),
                    text.replace("FRAME_BEGIN 42 ", "FRAME_BEGIN 43 "), text.replace("1000 180 0", "1000 180 1"),
                    text.replace("FRAME_END", ""), text.replace("direct 0 5", "direct 0 7"),
                    text.replace(" hide-call 0 5 12 12", " hide-call 0 5 999 12"),
                    text.replace(" 12 14 9\n", " 12 14 8\n"), text.replace(" 12 14 9\n", " 11 14 9\n")):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                readback.analyze(bad, dxgi, scan, limits)
        with self.assertRaises(ValueError):
            readback.analyze(text, dxgi.replace("79 82", "77 82"), scan, limits)

    def test_preserves_a_real_present_following_a_wait_timeout(self):
        result = readback.analyze(*fixture(result=258))
        self.assertEqual(result["waitResults"], {"258": 6})
        samples = result["presentedAfterTimeout"]
        self.assertEqual(len({s["frame"] for s in samples}), 6)
        for sample in samples:
            self.assertEqual(sample["requestedMs"], 1000)
            self.assertLessEqual(sample["waitQpc"][1], sample["dxgiPresentQpc"][0])

    def test_release_accepts_the_observed_native_cargo_layout_and_refuses_foreign_targets(self):
        exe = readback.PureWindowsPath("D:/runner/build/release/native-gui-assessment.exe")
        for directory in ("release/deps", "release/build/eframe/2e696ff6ae9846ad/out"):
            files = [exe.parent.parent / directory / ("libeframe-2e696ff6ae9846ad." + ext) for ext in ("rlib", "rmeta")]
            names = {f.relative_to(exe.parent.parent).as_posix() for f in files}
            self.assertTrue(readback.release_outputs(files, names, exe, "eframe"))
            self.assertFalse(readback.release_outputs(files, names, exe, "another"))
            self.assertFalse(readback.release_outputs(files[1:], names, exe, "eframe"))
            self.assertFalse(readback.release_outputs(files, {f.name for f in files}, exe, "eframe"))
            self.assertFalse(readback.release_outputs(files, names, exe.parent.parent.parent / "other/release/app.exe", "eframe"))

    def test_an_old_uninstrumented_native_trace_cannot_supply_cost(self):
        text, dxgi, scan = sample(False)
        with self.assertRaisesRegex(ValueError, "native frame trace"):
            readback.analyze(text, dxgi, scan, {})

    def test_original_frame_trace_is_distinct_from_the_new_message_measurement(self):
        original = fixture()
        self.assertNotIn("windowMessages", readback.analyze(*original))
        with self.assertRaisesRegex(ValueError, "HWND message trace"):
            readback.analyze(*original, message_trace=True)
        log, dxgi, scan, limits = original
        with self.assertRaisesRegex(ValueError, "matching diagnostic source"):
            readback.analyze(log + "\nWND_BEGIN\n", dxgi, scan, limits)

    def test_changed_compiler_manifest_or_library_tree_is_rejected(self):
        expected = readback.prepare.PINS["compilerTrees"]
        for tree in (expected, {**expected, "eframe": {"files": 1, "sha256": "wrong"}}):
            with self.subTest(tree=tree["eframe"]["files"]), self.assertRaisesRegex(ValueError, "compiler manifests"):
                readback.prepare.verify_compiler_sources(lambda name: b"changed compiler source", tree)

    def test_regular_dispatch_must_share_the_complete_ordinary_pe_and_limits(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw = {k:k for k in (*readback.HOST_BUILD, "referenceBudgetSha256", "observerInputs")}
            raw["observerInputs"] = {name: readback.sha(readback.prepare.WARM / name)
                                     for name in ("measure.py", "frame_latency.py", "inputs.py", "scan_present.py")}
            raw["pairedBinary"] = raw["binary"]
            raw.update(status="over-budget", presentMode="Mailbox", diagnosticControl=False, desiredMaximumFrameLatency=1,
                       inputs={"workload":{"files":100000}, "inventory":{"gui":raw["binary"]}},
                       trials=[{}] * 3, comparison={k:{"passed":False} for k in readback.METRICS})
            primary = base / "measured/result.json";primary.parent.mkdir()
            primary.write_text(json.dumps(raw))
            regular = dict(raw, status="dispatch-observed", diagnosticControl=True,
                         primaryResultSha256=readback.sha(primary), dispatchObserverSha256=readback.sha(readback.prepare.WARM / "dispatch.py"))
            path = base / "dispatch/result.json";path.parent.mkdir()
            path.write_text(json.dumps(regular))
            self.assertEqual(readback.pair(base, raw)["measuredSha256"], readback.sha(primary))
            for k in ("binary", "revision", "run", "referenceBudgetSha256", "primaryResultSha256", "dispatchObserverSha256"):
                path.write_text(json.dumps(dict(regular, **{k:"wrong"})))
                with self.subTest(k=k), self.assertRaises(ValueError):
                    readback.pair(base, raw)


if __name__ == "__main__":
    unittest.main()
