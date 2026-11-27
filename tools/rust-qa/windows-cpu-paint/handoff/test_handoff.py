"""Controls for the native retained-HWND texture handoff and its independent readback."""
import copy
from pathlib import Path
import tempfile
import unittest

from evidence import check, cpu, dxgi_calls, scene
from fixture_build import example_main, sha
import pixels

ROOT = dict(pid=47, hwnd=500, tid=19, width=640, height=480)
SS = "CPU_PAINT_FALLBACK reason=sampler"
DXGI = "READY\nQPC 47 1000\nP DXGI 59\nDXGI 47 19 0 0 56 59\nCOMPLETE\n"


def transfer(seq, begin):
    fmt = f"start={begin+4} end={begin+6} width=640 height=480"
    return (f"GDI_PRESENT frame={seq} hwnd=500 tid=19 {fmt} lines=480\n"
            f"CPU_FRAME seq={seq} pid=47 hwnd=500 tid=19 begin={begin} rasterEnd={begin+3} {fmt} "
            "meshes=3 vertices=12 indices=18 sets=1 frees=0 lines=480 flushed=1")


def tile(phase):
    return pixels.HEADER + (b"".join(bytes(rgb)*5 for rgb in pixels.EXPECTED[phase]))*5


def fixture(out):
    (out / "presents.log").write_text(DXGI)
    coords = [[15, 25], [54, 64], [150, 64]]
    draw = " {} 7 15 25 54 64 150 64"
    lines = ["GRAPHICS_ATTEMPT generation=1 policy=preferred", "GRAPHICS_MEMORY generation=1 hint=MemoryUsage",
             "GRAPHICS_READY generation=1", "ADAPTER Dx12 Cpu Microsoft Basic Render Driver", cpu.MODE,
             "HANDOFF_FULL id=7", "HANDOFF_DRAW" + draw.format(0), transfer(1,11),
             "HANDOFF_PARTIAL id=7", "HANDOFF_DRAW" + draw.format(1), transfer(2,31),
             "HANDOFF_NEAREST id=8", "HANDOFF_DRAW" + draw.format(2), "GDI_PRESENT_END frames=2 partial=0", SS,
             "DRAINED passes=3"]
    (out / "subject.log").write_text("\n".join(lines))
    result = dict(root=ROOT.copy(), frequency=1000, traceBoundsQpc=[5,85], exitCode=0, emptyJob=True,
                  profileRemoved=True, creation100ns=1001, quitQpc=87,
                  windowLifetime=[[500,"create",1],[500,"destroy",2]], phases=[])
    for i, issued in enumerate((10, 30, 50)):
        path = out / f"phase-{i}.ppm"
        path.write_bytes(tile(i))
        result["phases"].append(dict(phase=i, issuedQpc=issued, boundsQpc=[issued+10,issued+14], root=ROOT.copy(),
                                     jobPids=[47], creation100ns=1001, clientCenters=coords, screenCenters=coords,
                                     origin=[0,0], pixels=sha(path)))
    return result


class Handoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.row = fixture(self.out)

    def test_initial_partial_and_fallback_display(self):
        self.assertEqual(check(self.out, self.row), dict(originalTexture=7, nearestTexture=8, verifiedVisiblePhases=3,
                         fullCpuFrames=2, dxgiPresentsBeforeFinalPixels=1, root=ROOT))

    def test_all_patches_need_expected_screen_pixels_after_real_partial(self):
        for i in range(3):
            p = self.out / f"phase-{i}.ppm"
            p.write_bytes(tile((i+1)%3))
            self.row["phases"][i]["pixels"] = sha(p)
            with self.subTest(i=i), self.assertRaises(ValueError):
                check(self.out,self.row)
            self.row = fixture(self.out)

    def test_old_replaced_or_reuploaded_texture_fails(self):
        raw = (self.out / "subject.log").read_text()
        for old, new in (("HANDOFF_PARTIAL id=7","HANDOFF_PARTIAL id=8"),
                         ("HANDOFF_NEAREST id=8","HANDOFF_FULL id=7\nHANDOFF_NEAREST id=8"),
                         ("HANDOFF_NEAREST id=8","HANDOFF_NEAREST id=7"), ("DRAW 2 7","DRAW 2 9"),
                         (SS, "CPU_PAINT_FALLBACK reason=callback")):
            with self.subTest(old=old,new=new), self.assertRaises(ValueError):
                scene(raw.replace(old,new))

    def test_switch_cannot_resume_cpu_or_use_an_untimed_present(self):
        p = self.out / "subject.log"
        p.write_text(p.read_text() + "\n" + transfer(3,53))
        with self.assertRaises(ValueError):
            check(self.out,self.row)
        for before, after in (("47 19","47 20"),("56 59","45 59"),("0 0 56","0 1 56"),
                              ("DXGI 59","DXGI 60"),("COMPLETE","TRACE_ERROR"),("56 59","56 63")):
            with self.subTest(before=before), self.assertRaises(ValueError):
                dxgi_calls(DXGI.replace(before,after),ROOT,1000,[5,85],50,60)

    def test_foreign_job_lifetime_or_point_is_refused(self):
        for change in (
            lambda r:r["phases"][2]["root"].update(hwnd=501),lambda r:r["phases"][1].update(creation100ns=1002),
            lambda r:r["phases"][0].update(jobPids=[47,52]),lambda r:r["phases"][0].update(origin=[30,0]),
            lambda r:r["windowLifetime"].insert(1,[500,"destroy",8]),lambda r:r.update(profileRemoved=False),
            lambda r:r.update(quitQpc=40),lambda r:r.update(exitCode=1),lambda r:r["phases"][1].update(issuedQpc=38),
        ):
            row=copy.deepcopy(self.row)
            change(row)
            with self.subTest(change=change), self.assertRaises(ValueError):
                check(self.out,row)

    def test_binds_three_patch_sites_and_leaves_ordinary_reference_intact(self):
        source = b"mod fonts;\n            let language = ui.add(button);\n                Ok(()) if next[0] == b'O' => Command::Open,"
        self.assertIn(b"handoff_scene::advance",example_main(source))
        self.assertIn(b"handoff_scene::paint",example_main(source))
        for invalid in (source+source,source.replace(b"mod fonts;",b"")):
            with self.assertRaises(ValueError):
                example_main(invalid)
