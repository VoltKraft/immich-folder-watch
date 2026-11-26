"""Portable controls for linking tessellated CPU meshes to original, flushed HWND transfers."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("ifw_cpu_case_test", Path(__file__).with_name("measure.py"))
case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(case)
ROOT = dict(pid=47, hwnd=500, tid=19, width=640, height=480)
DEVICE = ("GRAPHICS_ATTEMPT generation=1 policy=preferred\nGRAPHICS_MEMORY generation=1 hint=MemoryUsage\n"
          "GRAPHICS_READY generation=1\nADAPTER Dx12 Cpu Microsoft Basic Render Driver\n"
          "WINDOW_RELEASED passes=2\nDRAINED passes=2")


def transfer(seq, count, begin, *, partial=False, lines=480, geometry=True):
    stage = "PARTIAL" if partial else "PRESENT"
    win = "hwnd=500 tid=19"
    times = f"start={begin+4} end={begin+6} width=640 height=480"
    mesh = "meshes=1 vertices=5 indices=9" if geometry else "meshes=0 vertices=0 indices=0"
    return (f"GDI_{stage} frame={count} {win} {times} lines={lines}\n"
            f"CPU_FRAME seq={seq} pid=47 {win} begin={begin} rasterEnd={begin+3} {times} {mesh} sets=1 frees=0 lines={lines} flushed=1")


def receipt():
    return "\n".join([case.MODE, transfer(1, 1, 10), transfer(2, 2, 20, geometry=False),
                      transfer(3, 1, 30, lines=0, partial=True), "GDI_PRESENT_END frames=2 partial=1"])


class FrameEvidence(unittest.TestCase):
    def test_counts_clear_and_zero_line_attempts_without_qualifying_them_as_visible_meshes(self):
        series, costs = case.frames(receipt(), ROOT, 1000)
        self.assertEqual(series.complete, [(14,16)])
        self.assertEqual(series.positive, [(14,16),(24,26)])
        self.assertEqual(series.empty, [(34,36)])
        self.assertEqual(costs, dict(transfers=3, fullTransfers=2, partialTransfers=1, clearOnlyFull=1,
                                     meshBearingTransfers=2, meshes=2, textureSets=3, textureFrees=0,
                                     cpuPaintP95Ms=3., dibAndFlushP95Ms=2.))
        self.assertEqual(case.gdi.inside(series.complete, (20,29)), 0)
        self.assertEqual(case.gdi.inside(series.complete, (10,17)), 1)

    def test_rejects_wrong_process_root_thread_geometry_clock_or_native_return(self):
        raw = receipt()
        for old, new in (("seq=2","seq=1"), ("pid=47","pid=48"), ("tid=19","tid=20"), ("hwnd=500","hwnd=501"),
                         ("width=640","width=641"), ("rasterEnd=13","rasterEnd=15"), ("begin=20","begin=15"),
                         ("start=14","start=13"), ("end=16","end=15"), ("indices=9","indices=8"),
                         ("vertices=5","vertices=1"), ("flushed=1","flushed=0"), ("frame=2","frame=1"),
                         ("frames=2 partial=1","frames=1 partial=2"), ("lines=480","lines=479")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                case.frames(raw.replace(old,new,1), ROOT, 1000)

    def test_gpu_staging_missing_duplicate_or_late_receipts_do_not_qualify(self):
        raw = receipt().splitlines()
        for changed in (raw + [raw[2]], raw[:2] + raw[3:], raw[:3] + [raw[2]] + raw[3:], raw[1:],
                        [raw[1],raw[0],*raw[2:]], raw[:-1], [*raw[:1],"STAGING_END copies=1",*raw[1:]],
                        [*raw[:1],"GDI_FAILED",*raw[1:]], [*raw[:1],"GDI_PRESENT_MODE backend=Dx12 device=Cpu",*raw[1:]],
                        [case.MODE,transfer(1,1,10,geometry=False), "GDI_PRESENT_END frames=1 partial=0"]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                case.frames("\n".join(changed), ROOT, 1000)

    def test_local_transfer_is_distinct_from_real_warp_adapter_setup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"subject.log"
            source = receipt() + "\n" + DEVICE
            path.write_text(source)
            self.assertEqual(case.generation(path)["transfer"],"GDI")
            for text in (source.replace("ADAPTER Dx12 Cpu","ADAPTER Vulkan Cpu"), source.replace(case.MODE,""),
                         source.replace("DRAINED passes=","ABORT passes="), source+"\nFRAME_READY_BEGIN",
                         source+"\nSTAGING_COPY"):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    path.write_text(text)
                    case.generation(path)

    def test_active_device_loss_cannot_pass_as_normal_quit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "subject.log"
            source = receipt() + "\n" + DEVICE
            for reason in ("Unknown", "Destroyed"):
                for boundary in ("WINDOW_RELEASED", "DRAINED"):
                    with self.subTest(reason=reason, boundary=boundary):
                        loss = f"GRAPHICS_LOST generation=1 reason={reason}"
                        path.write_text(source.replace(boundary, loss + "\n" + boundary))
                        with self.assertRaisesRegex(ValueError, "without loss or retry"):
                            case.generation(path)
            for changed in (source.replace("GRAPHICS_READY generation=1", "GRAPHICS_READY generation=2"),
                            source.replace("GRAPHICS_ATTEMPT generation=1", "GRAPHICS_ATTEMPT generation=2"),
                            source + "\nGRAPHICS_LOST generation=2 reason=Unknown",
                            source + "\nGRAPHICS_RETRY generation=1",
                            source + "\nGRAPHICS_ERROR device_lost=true detail=None"):
                with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "without loss or retry"):
                    path.write_text(changed)
                    case.generation(path)

    def test_all_eleven_limits_use_original_comparisons_including_a_real_failure(self):
        limits = dict.fromkeys(case.METRICS, 10)
        ordinary = case.recorder.comparison(limits, dict.fromkeys(case.METRICS,7))
        metrics = dict.fromkeys(case.METRICS,10)
        self.assertEqual(case.resource_comparison(metrics,limits,ordinary)["status"],"within-limits")
        metrics["scan_reopen_p95_ms"] = 11
        actual = case.resource_comparison(metrics,limits,ordinary)
        self.assertEqual(actual["status"],"over-budget")
        self.assertEqual(actual["metrics"]["scan_reopen_p95_ms"], dict(maximum=10,candidate=11,passed=False,ordinaryMedian=7))
        with self.assertRaises(ValueError):
            case.resource_comparison(metrics,{**limits,"visible_present_per_second":11},ordinary)
        del metrics["startup_ms"]
        with self.assertRaises(ValueError):
            case.resource_comparison(metrics,limits,ordinary)

    def test_both_editor_inputs_need_their_own_mesh_and_the_same_scanning_window(self):
        root = {key:ROOT[key] for key in ("hwnd", "pid", "tid")}
        field = lambda a,b: dict(root=dict(ROOT), qpc=[a,b])
        edit = dict(root=root, creation100ns=101, editorClocks=[10,40,60,90], presentationQpc=[9,91],
                    fields=dict(before=field(12,30), after=field(65,80)), rootLifetimes=[[500,"create"]],
                    rootEvents=[dict(hwnd=500,root=True,event=name) for name in ("hide","show")])
        scan = dict(editor=edit, presentation=dict(root=ROOT,guiCreation100ns=101,traceBoundsQpc=[1,9]),
                    termination={"method":"control-Q","exitCode":0})
        row = {"scan":scan, "frameWindows":{"guiCreation100ns":1, "frequency":1000}}
        series = case.gdi.FrameSeries([(16,20),(69,73)],[],[])
        with tempfile.TemporaryDirectory() as area, patch.object(case, "visible_edit", return_value={"pid":47,"hwnd":500}) as pixels:
            out = Path(area)
            etw = out / "editor-presents.log"
            okay = "READY\nQPC 47 1000\nCOMPLETE\n"
            etw.write_text(okay)
            value = case.editor_result(out,row,series)
            self.assertEqual(value["fullMeshTransfers"], {"before":1,"after":1})
            self.assertEqual(pixels.call_args.kwargs["subject_log"],out / "rust-1-scan.log")
            etw.write_text(okay.replace("COMPLETE", "P DXGI 75\nCOMPLETE"))
            with self.assertRaisesRegex(ValueError, "DXGI/D3D9 present"):
                case.editor_result(out,row,series)
            etw.write_text(okay)
            for missing in ([(16,20)], [(69,73)], [(11,15),(70,84)]):
                with self.assertRaisesRegex(ValueError,"during one of the visible edits"):
                    case.editor_result(out,row,case.gdi.FrameSeries(missing,[],[]))
            edit["fields"]["after"]["root"]["tid"] += 1
            with self.assertRaisesRegex(ValueError,"visible root intervals"):
                case.editor_result(out,row,series)
            edit["fields"]["after"]["root"] = ROOT
            edit["creation100ns"] = 102
            with self.assertRaisesRegex(ValueError,"edited process or root"):
                case.editor_result(out,row,series)


if __name__ == "__main__":
    unittest.main()
