"""Exercise native DWM owner, real-frame, file and original-pixel joins on portable receipts."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import dwm_transitions as dwm
from inputs import sha
from scan import environment
from test_frame_latency import inventory_trial, png


class TransitionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name)
        self.row = inventory_trial(self.out, 1, 1)
        scan = self.row["scan"]
        self.stem = self.out / "rust-1-scan.log"
        self.files = (self.out / "rust-1-scan-files.log").read_text()
        self.meta = dwm.read(self.out / "rust-1-scan-requests.json")
        self.root = dict(hwnd=self.meta["requests"][0]["hwnd"], pid=scan["guiPid"], tid=42)
        path = self.out / "rust-1-scan-presents.log"
        lines = []
        for line in path.read_text().splitlines():
            if line.startswith("DXGI "):
                lines.append("P DXGI " + line.split()[-1])
            lines.append(line)
        path.write_text("\n".join(lines) + "\n")
        self.frames = path.read_text()
        scan["presentation"].update(guiCreation100ns=123, decodedEventsSha256=sha(path))
        self.marker = "DWM_TRANSITIONS mode=disabled hwnd={hwnd} pid={pid} tid={tid} set=1 hresult=0".format(**self.root)
        self.stem.write_text(self.marker + "\n" + self.stem.read_text()
                             + f"ADAPTER Dx12 Cpu Microsoft Basic Render Driver\nINVENTORY_WORKER pid={scan['inventoryPid']}\n")

    def test_one_successful_set_on_original_root_and_no_write_on_control(self):
        text = self.stem.read_text()
        dwm.root_marker(text, "disabled", self.root)
        ordinary = text.replace("mode=disabled", "mode=ordinary").replace("set=1 hresult=0", "set=0")
        dwm.root_marker(ordinary, "ordinary", self.root)
        for bad in (text.replace("hresult=0", "hresult=1"), text.replace("set=1", "set=0"),
                    text.replace("tid=42", "tid=91"), text.replace("pid=11", "pid=12"), text.replace("hwnd=511", "hwnd=999"),
                    text + self.marker + "\n", text.replace("Microsoft Basic Render Driver", "another adapter"),
                    text.replace(self.marker + "\n", "") + self.marker + "\n"):
            with self.subTest(marker=bad[:80]), self.assertRaises(ValueError):
                dwm.root_marker(bad, "disabled", self.root)
        with self.assertRaises(ValueError):
            dwm.root_marker(ordinary.replace("set=0", "set=1 hresult=0"), "ordinary", self.root)

    def test_frames_have_successful_etw_pairs_and_same_thread_before_next_close_and_near_files(self):
        def score(text):
            return dwm.visible_frames(self.row["scan"], self.meta, self.files, text, self.root)
        good = score(self.frames)
        self.assertEqual(good["eligibleReopensWithPresent"], 8)
        self.assertEqual(good["eligibleReopens"], 10)
        for bad in (self.frames.replace("P DXGI ", "P D3D9 ", 1), self.frames.replace(" 42 0 0", " 73 0 0", 1),
                    self.frames.replace(" 42 0 0", " 42 0 512", 1), self.frames.replace(" 42 0 0", " 42 0 1", 1),
                    self.frames.replace("DXGI 11 42", "DXGI 17 42", 1), self.frames.replace("P DXGI 3721", "P DXGI 3711", 1)):
            with self.subTest(event=bad.splitlines()[2:4]), self.assertRaises(ValueError):
                score(bad)
        start = self.meta["requests"][0]["responseQpc"]
        hidden = f"P DXGI {start+2}\nDXGI 11 42 0 0 {start+1} {start+2}\n"
        with self.assertRaisesRegex(ValueError, "hidden"):
            score(self.frames.replace("P DXGI ", hidden + "P DXGI ", 1))
        # Cross the next issued close while spending the last ticks before its hide acknowledgement.
        bad = self.frames
        for q in self.meta["requests"][3::2][:-1]:
            begin = q["responseQpc"]
            end = self.meta["requests"][self.meta["requests"].index(q)+1]["issuedQpc"]
            bad = bad.replace(f"P DXGI {begin+1}\nDXGI 11 42 0 0 {begin} {begin+1}",
                              f"P DXGI {end+1}\nDXGI 11 42 0 0 {end} {end+1}")
        with self.assertRaisesRegex(ValueError, "five"):
            score(bad)

    def test_editor_on_original_scan_root_after_both_traces_preserves_focus_and_visible_change(self):
        folder = self.out / "disabled-editor"
        folder.mkdir()
        hwnd = self.root["hwnd"]
        generation = ["GRAPHICS_READY generation=1"]
        edit = dict(root=self.root, case="retained-edit", creation100ns=123, pid=11, singleWake=False, exitCode=0,
                    subjectLog=sha(self.stem), rootLifetimes=[[hwnd, "create", 2]], editorClocks=[310001, 310002, 310003, 310004],
                    rootEvents=[dict(event=s, hwnd=hwnd, root=True) for s in ("hide", "show")],
                    transitions=[dict(hidden=hwnd, reopened=hwnd, generationBefore=generation, generationAfter=generation)])
        self.row["scan"].update(editor=edit, termination=dict(method="control-Q", exitCode=0))
        for phase in ("before", "after"):
            path = folder / ("field-" + phase + ".json")
            field = dict(processId=11, windowHandle=hwnd, dpi=96, status="passed", onInputDesktop=True,
                         foreground=True, draft="recoverydraft", editedFrame=png(path.with_suffix(".json.edited.png"), int(phase == "after")))
            if phase == "after":
                field.update(draft="recoverydraftafter", focusBeforeActivation="Dateiname", restoredFrame=png(path.with_suffix(".json.restored.png"), 0),
                             difference=dict(pixels=128, columns=16, rows=8, textChanged=True))
            path.write_text(json.dumps(field))
            edit[phase + "Field"] = sha(path)
        result = dwm.scan_result(self.out, 1, "disabled", self.row)
        self.assertEqual(result["editor"]["pixelDifference"]["pixels"], 128)
        for key, wrong in (("rootLifetimes", [[hwnd, "destroy", 1], [hwnd, "create", 2]]),
                           ("rootEvents", []), ("editorClocks", [10, 20, 30, 40]), ("creation100ns", 121)):
            bad = deepcopy(self.row)
            bad["scan"]["editor"][key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                dwm.scan_result(self.out, 1, "disabled", bad)
        png(folder / "field-after.json.edited.png", 0)
        with self.assertRaisesRegex(ValueError, "screen pixels"):
            dwm.scan_result(self.out, 1, "disabled", self.row)

    def test_references_recompute_three_fixed_wpf_limits_and_original_ordinary_metrics(self):
        base = self.out / "windows-warm-window" / dwm.TARGET
        ordinary_dir = base / "measured"
        out = base / "dwm-transitions"
        wpf = self.out / "windows-performance" / ("native-" + dwm.TARGET)
        canonical_dir = self.out / "gui-native" / dwm.TARGET
        for path in (ordinary_dir, out, wpf, canonical_dir):
            path.mkdir(parents=True)
        def save(path, data):
            path.write_text(json.dumps(data))
            return sha(path)
        def executable(path, data):
            path.parent.mkdir(parents=True)
            path.write_bytes(data)
            return sha(path)
        binary = executable(base / "build/release/native-gui-assessment.exe", b"synthetic retained subject")
        cold = executable(self.out / "gui-build/release/native-gui-assessment.exe", b"synthetic canonical subject")
        canonical = dict(binarySha256=cold, source="revision", target=dwm.TARGET, lockSha256="lock", graphSha256="graph")
        common = dict(binary=binary, revision="revision", target=dwm.TARGET, baseline=cold, baselineReceipt=save(canonical_dir / "build.json", canonical))
        sources = {n: sha(dwm.HERE / n) for n in dwm.VARIANT_INPUTS}
        (base / "compiler.jsonl").write_bytes(b"synthetic compiler receipt")
        (base / "eframe-source.zip").write_bytes(b"synthetic source receipt")
        build = dict(common, canonicalLock="lock", canonicalGraph="graph", variantInputs=sources, compilerInputs=sources,
                     compilerEvidence=dict(application=dict(target="native-gui-assessment", crateRoot="src/main.rs",
                                           output="native-gui-assessment.exe", sha256=binary), sha256=sha(base / "compiler.jsonl")),
                     eframeSource=dict(archiveSha256=sha(base / "eframe-source.zip")))
        inv = dict(gui=binary, compiledEntry="entry", approvedBundle="bundle", sources={}, packages=[])
        workload = dict(files=100000)
        original = dict(target=dwm.TARGET, candidateRevision=common["revision"], guiBinarySha256=cold, guiReceiptSha256=common["baselineReceipt"],
                        referenceRevision=dwm.REFERENCE, referenceSourceSha256=dwm.REFERENCE_SOURCE_SHA256, inventory=inv, workload=workload)
        values = dict.fromkeys(dwm.METRICS, 1)
        budget = dict(sourceInputsSha256=save(wpf / "inputs.json", original), reference=values, maximums=dwm.recorder.budgets(values))
        digest = save(wpf / "reference-budget.json", budget)
        reference = dict(host=dict(run="run", attempt="1"), budgetSha256=digest, trials=dict(wpf=[dict(metrics=values) for _ in range(3)]))
        save(wpf / "result.json", reference)
        common.update(run="run", attempt="1", buildReceipt=save(base / "build.json", build), referenceBudgetSha256=digest,
                      inputs=dict(workload=workload, inventory=inv), diagnosticControl=True,
                      presentMode="Mailbox", desiredMaximumFrameLatency=1,
                      observerInputs={n: sha(dwm.HERE / n) for n in ("measure.py", "frame_latency.py", "inputs.py", "scan_present.py")})
        observed = dict(common, dwmObserver={n: sha(dwm.HERE / n) for n in dwm.INPUTS})
        trials = [inventory_trial(ordinary_dir, idx, 1) for idx in range(1, 4)]
        rows = dwm.recorder.comparison(budget["maximums"], dwm.recorder.summarize(trials))
        save(ordinary_dir / "result.json", dict(common, diagnosticControl=False, trials=trials, comparison=rows))
        checked = dwm.references(out, observed, wpf)
        self.assertEqual(checked["ordinaryThree"]["scan_reopen_p95_ms"], dict(maximum=11, candidate=22, passed=False))
        for key, wrong in (("referenceBudgetSha256", "other"), ("run", "wrong"), ("binary", "other subject")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                dwm.references(out, dict(observed, **{key: wrong}), wpf)
        budget["maximums"]["scan_reopen_p95_ms"] = 99
        save(wpf / "reference-budget.json", budget)
        with self.assertRaisesRegex(ValueError, "frozen"):
            dwm.references(out, observed, wpf)

    def test_a_stale_environment_cannot_enable_the_setter_on_ordinary_scans(self):
        area = self.out / "rust-1-scan"
        area.mkdir()
        token = "a" * 32
        (self.out / "inventory.owner").write_text(token)
        with patch.dict(os.environ, IFW_QA_DWM_TRANSITIONS="disabled"):
            child = environment(area, "http://127.0.0.1:51515", True, self.out / "files", token)
        self.assertNotIn("IFW_QA_DWM_TRANSITIONS", child)


if __name__ == "__main__":
    unittest.main()
