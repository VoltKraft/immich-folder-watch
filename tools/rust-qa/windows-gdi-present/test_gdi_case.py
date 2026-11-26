"""Portable negative controls for the actual native GDI receipt reader."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import gdi_case as gdi
from test_frame_latency import inventory_trial, png


ROOT = dict(pid=11, hwnd=511, tid=20, width=400, height=240)


def line(seq, lo, hi, tag="PRESENT", lines=240):
    return (f"GDI_{tag} frame={seq} hwnd=511 tid=20 start={lo} end={hi} "
            f"width=400 height=240 lines={lines}")


def receipt(*events, full=1, partial=0):
    return "\n".join([gdi.MODE, *events, f"GDI_PRESENT_END frames={full} partial={partial}"])


def calibration():
    requests = []
    starts = [20, 30, 20000, 40000] + [45000 + i * 100 for i in range(gdi.recorder.SWITCHES * 2)]
    for index, tick in enumerate(starts):
        requests.append(dict(action=("close", "reopen")[index % 2], hwnd=511, issuedQpc=tick, responseQpc=tick + 1))
    samples = {mode:dict(seconds=15.0, samples=[1,3,5], working_set_mib=3, cpu_one_core_pct=0.4) for mode in ("visible", "hidden")}
    durations = dict.fromkeys(("close","reopen"), [1.0] * gdi.recorder.SWITCHES)
    metrics = {"startup_ms": 2, "idle_close_p95_ms": 1.0, "idle_reopen_p95_ms": 1.0}
    for mode, sample in samples.items():
        for key in ("working_set_mib", "cpu_one_core_pct"):
            metrics[mode + "_" + key] = sample[key]
    return dict(frameWindows=dict(root=ROOT, guiCreation100ns=5, startupQpc=[1,3], frequency=1000,
                                  spans=dict(visible=[1000,16000], hidden=[21000,36000]), controls=[[30,800],[40000,40800]],
                                  requests=requests), metrics=metrics, idleSamples=samples, idleVisibilityMs=durations,
                controls=dict(wholeProcessTree={11:dict(creation100ns=5, parent=3, image="subject.exe"),
                                                23:dict(creation100ns=6, parent=11, image="ifw-performance-worker.exe")},
                              successfulVisibilityCycles=gdi.recorder.SWITCHES), termination=dict(method="control-Q", exitCode=0))


class FrameTests(unittest.TestCase):
    def test_staging_requires_return_before_reuse_and_binds_each_transfer_to_its_mapping(self):
        first = ("STAGING_COPY seq=1 reused=0 width=400 height=240 bytes=430080 "
                 "begin=1 prepared=3 map=4 ready=6 returned=10 transfers=1")
        second = ("STAGING_COPY seq=2 reused=1 width=400 height=240 bytes=430080 "
                  "begin=11 prepared=12 map=13 ready=19 returned=22 transfers=0")
        resized = ("STAGING_COPY seq=3 reused=0 width=399 height=240 bytes=430080 "
                   "begin=24 prepared=25 map=26 ready=27 returned=29 transfers=0")
        rows = [line(1,7,9), first, second, resized, "STAGING_END copies=3"]
        result = gdi.staging_observation("\n".join(rows), 1000)
        self.assertEqual((result["allocations"], result["reuses"], result["copies"]), (2, 1, 3))
        self.assertEqual(result["mapAndWaitP95Ms"], 6)
        for original, replacement in (
                (second, second.replace("reused=1", "reused=0")),
                (resized, resized.replace("reused=0", "reused=1")),
                (first, first.replace("ready=6", "ready=8")),
                (second, second.replace("begin=11", "begin=8")),
                (first, first.replace("transfers=1", "transfers=0")),
                (first, first.replace("bytes=430080", "bytes=422400")),
                (rows[0], ""),
                (rows[-1], "STAGING_END copies=2")):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                gdi.staging_observation("\n".join(rows).replace(original, replacement), 1000)

    def test_source_and_sequence_are_bound_to_one_gui_and_final_aggregate(self):
        events = [line(1, 6, 8), line(1, 9, 10, "PARTIAL", 0), line(2, 11, 12, "PARTIAL", 240), line(2, 13, 14)]
        raw = receipt(*events, full=2, partial=2)
        series = gdi.frame_spans(raw, ROOT)
        self.assertEqual(series.complete, [(6,8),(13,14)])
        self.assertEqual(series.positive, [(6,8),(11,12),(13,14)])
        self.assertEqual(series.empty, [(9,10)])
        for old, new in [("tid=20","tid=99"), ("hwnd=511","hwnd=31"), ("width=400","width=390"),
                         ("lines=240","lines=239"), ("PRESENT frame=2","PRESENT frame=3"),
                         ("PARTIAL frame=2","PARTIAL frame=1"), ("start=13","start=11"), ("frames=2","frames=3"),
                         ("partial=2","partial=1"), (gdi.MODE, gdi.MODE+"\n"+gdi.MODE),
                         ("GDI_PARTIAL frame=1","GDI_FAILED frame=1"), ("GDI_PRESENT_END","exit")]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                gdi.frame_spans(raw.replace(old, new, 1), ROOT)

    def test_partial_and_zero_line_transfers_count_in_idle_but_cannot_qualify_calibrations(self):
        events = [line(1,6,7), line(2,42,48), line(1,2000,2002,"PARTIAL",0), line(2,3000,3004,"PARTIAL",1),
                  line(3,40003,40005)]
        native = "READY\nQPC 11 1000\nCOMPLETE\n"
        def run(values):
            return gdi.idle_observation(calibration(), gdi.frame_spans(receipt(*values, full=3, partial=2), ROOT), native)
        result = run(events)
        self.assertEqual(result["rates"]["visible_present_per_second"], 2/15)
        self.assertEqual(result["idlePositiveTransfers"], {"visible":1,"hidden":0})
        self.assertEqual(result["reopenControls"], [1,1])
        for replacement in (line(1,20001,20002,"PARTIAL",0), line(1,19999,20002,"PARTIAL",1)):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                run([events[0],events[1],events[3].replace("frame=2","frame=1"),replacement.replace("frame=1","frame=2"),events[4]])
        events[1] = line(1,42,48,"PARTIAL",240)
        events[2] = line(2,2000,2002,"PARTIAL",0)
        events[3] = line(3,3000,3004,"PARTIAL",1)
        events[4] = line(2,40003,40005)
        with self.assertRaisesRegex(ValueError, "reopened"):
            gdi.idle_observation(calibration(), gdi.frame_spans(receipt(*events, full=2, partial=3), ROOT), native)

    def test_positive_dxgi_or_foreign_empty_trace_fails(self):
        good = "READY\nQPC 11 1000\nCOMPLETE"
        gdi.no_swapchain(good, 11, 1000)
        for value in (good.replace("11","12"), good.replace("1000","900"), good.replace("READY","STOPPED"),
                      good.replace("COMPLETE","P DXGI 601\nCOMPLETE"), good + "\nDECODE_ERROR", "READY\nCOMPLETE"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gdi.no_swapchain(value, 11, 1000)

    def test_native_double_inventory_requires_work_at_reopen_and_at_first_full_present(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = inventory_trial(root, 1, 1)
            scan = row["scan"]
            scan.update(inventoryCreation100ns=23, termination=dict(exitCode=0))
            with (root / "rust-1-scan.log").open("a") as source:
                source.write(f"INVENTORY_WORKER pid={scan['inventoryPid']}\n")
            output = root / "rust-1-scan-presents.log"
            output.write_text("READY\nQPC 11 10000\nCOMPLETE\n", encoding="ascii")
            scan["presentation"] = dict(root=ROOT, traceBoundsQpc=[1,310000],
                                         guiCreation100ns=12, decodedEventsSha256=gdi.sha(output))
            requests = scan["allRequests"]
            frames = [(q["responseQpc"]+1, q["responseQpc"]+3) for q in requests[1::2]]
            series = gdi.FrameSeries(frames, frames, [])
            obs = gdi.scan_observation(root, row, series)
            self.assertEqual(obs["workQualifiedReopensWithFrame"], 9)
            self.assertEqual(obs["firstFullBlitAfterObservedReopenP95Ms"], 0.3)
            self.assertEqual(obs["workQualifiedResponses"], 20)
            with self.assertRaisesRegex(ValueError, "Fewer"):
                gdi.scan_observation(root, row, gdi.FrameSeries(frames[:4],frames,[]))
            stale = deepcopy(row)
            stale["scan"]["allRequests"][2]["hwnd"] += 2
            with self.assertRaises(ValueError):
                gdi.scan_observation(root, stale, series)
            file_log = root / "rust-1-scan-files.log"
            file_log.write_bytes(file_log.read_bytes().replace(b"D 1 10 ", b"D 1 11 ", 1))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                gdi.scan_observation(root, row, series)

    def test_full_frame_and_changed_field_pixels_must_both_belong_to_reopened_editor(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            area = root / "retained-edit"
            area.mkdir()
            gen = ["GRAPHICS_READY generation=1"]
            log = area / "subject.log"
            log.write_text("\n".join([*gen, "GRAPHICS_MEMORY generation=1 hint=MemoryUsage",
                                      "ADAPTER Dx12 Cpu Microsoft Basic Render Driver", "DRAINED passes=1",
                                      receipt(line(1, 5, 6), line(2, 30, 31), full=2)]))
            transition = dict(hidden=511, reopened=511, hiddenQpc=20, reopenIssuedQpc=25, visibleQpc=27,
                              generationBefore=gen, generationAfter=gen)
            row = dict(case="retained-edit", transitions=[transition], pid=11, creation100ns=1234,
                       exitCode=0, singleWake=False, subjectLog=gdi.sha(log))
            for phase in ("before", "after"):
                path = area / f"field-{phase}.json"
                field = dict(processId=11, windowHandle=511, status="passed", dpi=96, onInputDesktop=True,
                             foreground=True, draft="recoverydraft",
                             editedFrame=png(area / (path.name + ".edited.png"), int(phase == "after")))
                if phase == "after":
                    field.update(draft="recoverydraftafter", focusBeforeActivation="Dateiname",
                                 restoredFrame=png(area / (path.name + ".restored.png"), 0),
                                 difference=dict(pixels=128, columns=16, rows=8, textChanged=True))
                path.write_text(json.dumps(field))
                row[phase + "Field"] = gdi.sha(path)
                row[phase + "FrameWindow"] = dict(root=ROOT, qpc=[2,12] if phase == "before" else [29,35])
            report = gdi.edit_observation(root, row)
            self.assertEqual(report["reopenedEditorFrames"], 1)
            self.assertEqual(report["pixelDifference"]["pixels"], 128)
            row["afterFrameWindow"]["qpc"] = [32,35]
            with self.assertRaisesRegex(ValueError, "visible GDI edits"):
                gdi.edit_observation(root, row)
            row["afterFrameWindow"]["qpc"] = [29,35]
            (area / "field-after.json.edited.png").write_bytes((area / "field-after.json.restored.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "screen pixels"):
                gdi.edit_observation(root, row)
