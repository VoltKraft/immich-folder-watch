"""Portable controls for native text evidence. These checks send no Windows input."""

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from evidence import GLYPHS, PLAN, editing, glyphs, mask
from run import evaluate


def observation(spec):
    row = dict(status="observed", text=spec["text"], arrowIndices=spec["arrows"], selected=spec["target"],
               selectedAt=spec["text"].index(spec["target"]), after=spec["after"], afterValue=spec["after"],
               deleteSubmitted=True, deleteStage="verified", dragScreen=[15, 21, 99])
    if spec["visualIndices"]:
        row["characters"] = [dict(index=i, left=x, right=x+4) for i, x in zip(range(2, 6), [30, 15, 20, 10])]
    return row


def sample(directory, duplicate=False):
    w, h = 32, 3
    pixels = bytearray(w*h*3)
    cells = []
    for i, cp in enumerate(GLYPHS):
        cells.append(dict(scalar=cp, crop=[4*i, 0, 4, h]))
        for pos in range(1 if duplicate else i+1):
            # A common origin and a different number of ink pixels in each 4x3 cell.
            at = 3*((pos//3)*w+4*i+pos%3)
            pixels[at:at+3] = b"\xed"*3
    ppm = f"P6\n{w} {h}\n255\n".encode() + pixels
    (directory/"observations.json.glyphs.ppm").write_bytes(ppm)
    def chunk(typ, data):
        return struct.pack(">I",len(data))+typ+data+struct.pack(">I",zlib.crc32(typ+data))
    rows = b"".join(b"\0"+pixels[3*w*j:3*w*(j+1)] for j in range(h))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))
    png += chunk(b"IDAT",zlib.compress(rows)) + chunk(b"IEND",b"")
    path = directory/"observations.json.glyphs.png"
    path.write_bytes(png)
    return dict(status="observed", cells=cells, frameSha256=hashlib.sha256(ppm).hexdigest(),
                capture=dict(width=w, height=h, sha256=hashlib.sha256(png).hexdigest())), path


class TextTests(unittest.TestCase):
    def test_matches_native_x11_cases(self):
        path = Path(__file__).resolve().parents[1] / "gui/profile_text.py"
        loop, = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n,ast.For)
                 and isinstance(n.target,ast.Tuple) and [v.id for v in n.target.elts]==["text","target","arrows","fraction","anchor"]]
        self.assertEqual(list(ast.literal_eval(loop.iter)),
                         [tuple(c[k] for k in ("text","target","arrows","fraction","anchor")) for c in PLAN["cases"]])

    def test_normalizes_translation_and_contrast(self):
        left = mask(4, 2, bytes([0, 200, 0, 0, 0, 200, 200, 0]))
        shifted = mask(5, 2, bytes([255,255,50,255,255,255,255,50,50,255]))
        self.assertEqual(left, shifted)
        for invalid in (bytes(8), bytes([100,90]*4), bytes(7)):
            with self.assertRaises(ValueError):
                mask(4,2,invalid)

    def test_raster_requires_unique_ink_and_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            record, path = sample(Path(tmp))
            self.assertEqual(len(glyphs(record,path)),8)
            path.with_suffix(".ppm").write_bytes(path.with_suffix(".ppm").read_bytes()[:-1])
            with self.assertRaises(ValueError): glyphs(record,path)
            record, path = sample(Path(tmp),duplicate=True)
            with self.assertRaisesRegex(ValueError,"duplicate"): glyphs(record,path)

    def test_rejects_wrong_caret_drag_and_deleted_character(self):
        case = PLAN["cases"][1]
        row = observation(case)
        editing(row,case)
        for key,value in (("arrowIndices",[4,5,4]),("selected","ت"),("selectedAt",3),("after",case["text"]),
                          ("afterValue",case["text"]),("deleteSubmitted",False),("deleteStage","keyboard"),("dragScreen",[3,3,9])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                editing(dict(row,**{key:value}),case)

    def test_requires_observed_visual_order(self):
        spec = PLAN["cases"][2]
        row = observation(spec)
        editing(row,spec)
        for bad in ([2,3,4,5],[5,3,2,4],[5,3,3,2]):
            broken=deepcopy(row)
            for box, position in zip(broken["characters"],bad): box["left"],box["right"]=position,position+1
            with self.subTest(bad=bad), self.assertRaises(ValueError): editing(broken,spec)

    def test_unavailable_input_and_wrong_process_are_never_accepted(self):
        row=dict(pid=49,hwnd=900,status="unavailable",error="no active foreground")
        report={}
        with self.assertRaisesRegex(RuntimeError,"no active foreground"): evaluate(row,None,49,900,report)
        self.assertEqual(report["status"],"unavailable")
        with self.assertRaises(ValueError): evaluate(row,None,50,900,{})

    def test_independent_case_survives_raster_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            area=Path(tmp)
            specimen,_=sample(area,duplicate=True)
            rows=[observation(s) for s in PLAN["cases"]]
            rows[1]["arrowIndices"]=[4,5,4]
            report={}
            with self.assertRaises(RuntimeError):
                evaluate(dict(pid=49,hwnd=900,field="Dateiname",foreground=True,inputDesktop=True,status="observed",
                              sample=specimen,cases=rows),area,49,900,report)
            self.assertEqual(report["editingPassed"],[rows[0]["text"],rows[2]["text"]])
            self.assertEqual(len(report["issues"]),2)


if __name__ == "__main__":
    unittest.main()
