"""Exercise replacement-window, worker and CPU-frame evidence with synthetic observations."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import device_recovery as device
from test_frame_latency import png


def draw(hwnd, start):
    end = start + 1
    geometry = f"start={start} end={end} width=64 height=40"
    return (f"GDI_PRESENT frame=1 hwnd={hwnd} tid=3 {geometry} lines=40\n"
            f"CPU_FRAME seq=1 pid=1 hwnd={hwnd} tid=3 begin={start-2} rasterEnd={start-1} {geometry} "
            "meshes=1 vertices=3 indices=3 sets=1 frees=0 lines=40 flushed=1\n")


def generation(number):
    policy = "preferred" if number == 1 else "cpu"
    return (f"GRAPHICS_ATTEMPT generation={number} policy={policy}\nGRAPHICS_MEMORY generation={number} hint=MemoryUsage\n"
            f"{device.paint.MODE}\nGRAPHICS_READY generation={number}\n{device.ADAPTER}\n")


def sample(root, phase, hwnd, qpc):
    base = root / f"field-{phase}.json"
    record = dict(processId=1, windowHandle=hwnd, status="passed", foreground=True, onInputDesktop=True,
                  draft="recoverydraft", editedFrame=png(Path(str(base) + ".edited.png"), 0 if phase == "before" else 15))
    if phase == "after":
        record.update(draft="recoverydraftafter", focusBeforeActivation="Dateiname", dpi=96,
                      restoredFrame=png(Path(str(base) + ".restored.png"), 0),
                      difference=dict(columns=16, rows=8, pixels=128, textChanged=True))
    base.write_text(json.dumps(record))
    return dict(root=dict(pid=1, tid=3, hwnd=hwnd, width=64, height=40), qpc=qpc, field=device.sha(base))


def fixture(root):
    old, new = 444, 777
    passes = lambda n: f"INVENTORY_COMPLETE files=0 changed=0 pass={n}\n"
    text = "INVENTORY_WORKER pid=2\n" + generation(1) + draw(old, 11) + passes(0) + passes(1)
    snapshots = []

    def snapshot(qpc):
        raw = text.encode()
        members = [dict(pid=1, parent=91, image="cpu.exe", role="primary", creation100ns=100),
                   dict(pid=2, parent=1, image=device.WORKER, role="worker", creation100ns=110)]
        snapshots.append(dict(qpc=qpc, passes=device.completed(text), job=dict(pids=[1, 2], members=members), logBytes=len(raw),
                              logSha256=sha256(raw).hexdigest()))

    snapshot(17)
    text += ("GRAPHICS_DESTROY generation=1\n" + device.LOSS + "\nGDI_PRESENT_END frames=1 partial=0\n"
             "GRAPHICS_ERROR device_lost=true detail=None\nGRAPHICS_RETRY generation=1\n")
    text += generation(2) + draw(new, 41)
    snapshot(52)
    text += passes(2)
    snapshot(56)
    text += "GDI_PRESENT_END frames=1 partial=0\nDRAINED passes=7\n"
    log = root / "subject.log"
    log.write_bytes(text.encode())
    return dict(subjectLog=device.sha(log), pids=[1, 2], creation100ns=[100, 110], fields=[sample(root, "before", old, [5, 15]),
                sample(root, "after", new, [37, 48])], workers=snapshots, frequency=10_000_000, destroyQpc=20, quitQpc=60,
                workerExit=0, emptyJob=True, profileRemoved=True, termination=dict(method="control-Q", exitCode=0),
                lifetimes=[[old, "create", 1], [old, "destroy", 2], [new, "create", 3], [new, "destroy", 4]],
                windowEvents=[dict(event="show", hwnd=h) for h in (old, new)])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.good = fixture(self.root)

    def test_original_worker_completes_another_pass_and_both_generations_paint(self):
        observed = device.check(self.root, self.good)
        self.assertEqual(observed["meshFramesDuringEdits"], [1, 1])
        self.assertEqual(observed["workerPassesAfterRecovery"], 1)
        self.assertEqual(observed["changedPixels"], 128)

    def test_swapped_gui_or_worker_and_failed_quit_do_not_qualify(self):
        for key, value in (("passes", 2), ("logSha256", "0" * 64)):
            with self.subTest(key=key):
                changed = deepcopy(self.good)
                changed["workers"][2][key] = value
                with self.assertRaises(ValueError):
                    device.check(self.root, changed)
        for member, changes in ((0, dict(creation100ns=105)), (1, dict(pid=42)), (1, dict(parent=3)),
                                (1, dict(image="cpu.exe")), (1, dict(creation100ns=111))):
            with self.subTest(changes=changes):
                changed = deepcopy(self.good)
                changed["workers"][2]["job"]["members"][member].update(changes)
                with self.assertRaises(ValueError):
                    device.check(self.root, changed)
        for key, value in (("emptyJob", False), ("workerExit", 1), ("profileRemoved", False),
                           ("termination", dict(method="already exited", exitCode=0))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                device.check(self.root, dict(self.good, **{key:value}))

    def test_job_may_include_an_identified_console_host_of_the_original_worker(self):
        job = self.good["workers"][1]["job"]
        job["pids"].append(3)
        helper = dict(pid=3, role="systemConsoleHost", image="conhost.exe", parent=2, creation100ns=115)
        job["members"].append(helper)
        self.assertEqual(device.check(self.root, self.good)["workerPassesAfterRecovery"], 1)
        for changes in (dict(image="other.exe"), dict(role="primary"), dict(parent=91), dict(pid=5), dict(creation100ns=0)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                job["members"][-1] = {**helper, **changes}
                device.check(self.root, self.good)
        job["members"][-1] = helper
        job["pids"].append(4)
        with self.assertRaises(ValueError):
            device.check(self.root, self.good)
        job["members"].append(dict(helper, pid=4))
        with self.assertRaises(ValueError):
            device.check(self.root, self.good)

    def test_incomplete_native_observation_reports_the_recorded_failure(self):
        out = self.root / "recovery"
        out.mkdir()
        (out / "result.json").write_text(json.dumps(dict(status="incomplete", error="worker exited")))
        with self.assertRaisesRegex(ValueError, "Native device recovery incomplete: worker exited"):
            device.verify(self.root)

    def test_only_actual_destroyed_first_device_and_successful_new_generation_qualify(self):
        log = (self.root / "subject.log").read_text()
        for old, new in ((device.LOSS, "GRAPHICS_LOST generation=1 reason=Unknown"), (device.RETRY, ""),
                         ("GRAPHICS_MEMORY generation=2", "GRAPHICS_MEMORY generation=1"),
                         ("DRAINED", "CPU_PAINT_FALLBACK reason=sampler\nDRAINED")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                device.generations(log.replace(old, new))

    def test_unrelated_gdi_or_window_and_stale_field_are_rejected(self):
        for key, mutate in (("non-edit transfer", lambda r: r["fields"][1].update(qpc=[45, 48])),
                            ("wrong window", lambda r: r["fields"][1]["root"].update(hwnd=444)),
                            ("missing destruction", lambda r: r["lifetimes"].pop())):
            with self.subTest(key=key):
                changed = deepcopy(self.good)
                mutate(changed)
                with self.assertRaises(ValueError):
                    device.check(self.root, changed)
        field = self.root / "field-after.json"
        report = device.read(field)
        report["draft"] = "after"
        field.write_text(json.dumps(report))
        self.good["fields"][1]["field"] = device.sha(field)
        with self.assertRaisesRegex(ValueError, "text"):
            device.check(self.root, self.good)

    def test_recovered_editor_requires_the_original_field_pixels(self):
        image = self.root / "field-after.json.edited.png"
        image.write_bytes((self.root / "field-after.json.restored.png").read_bytes())
        with self.assertRaisesRegex(ValueError, "screen pixels"):
            device.check(self.root, self.good)


if __name__ == "__main__":
    unittest.main()
