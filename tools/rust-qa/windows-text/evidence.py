"""Expected native filename observations and independent evaluation of the recorded cells."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import struct


GLYPHS = [ord(c) for c in "Aあ界⬟بتث"] + [0x10FFFD]
read_frame = runpy.run_path(str(Path(__file__).resolve().parents[1] / "font-coverage/text_observations.py"))["read_frame"]
CASES = [
    dict(text="あ界⬟.jpg", target="界", anchor="あ", fraction=.12, arrows=[0, 1, 0]),
    dict(text="L-بتث-R.jpg", target="ث", anchor="ث", fraction=.88, arrows=[4, 3, 4]),
    dict(text="L-ب12ت-R.jpg", target="ت", anchor="1", fraction=.12, arrows=[3, 4, 3]),
]
PLAN = {
    "initial": "Grüße – Sommer.jpg",
    "sample": " | ".join(map(chr, GLYPHS)),
    "glyphs": GLYPHS,
    "cases": [dict(c, after=c["text"].replace(c["target"], ""),
                   visualIndices=list(range(2, 6)) if "12" in c["text"] else []) for c in CASES],
}


def mask(width, height, blue):
    if not (0 < width <= 128 and 0 < height <= 128 and len(blue) == width * height):
        raise ValueError("Invalid native glyph crop dimensions")
    background = Counter(blue).most_common(1)[0][0]
    difference = [abs(value - background) for value in blue]
    threshold = max(24, max(difference) / 2)
    ink = [(i % width, i // width) for i, delta in enumerate(difference) if delta >= threshold]
    if not ink:
        raise ValueError("The captured character has no ink")
    left = min(x for x, _ in ink)
    top = min(y for _, y in ink)
    normalized = sorted((x-left, y-top) for x, y in ink)
    return {"inkPixels": len(ink), "maskSha256": hashlib.sha256(json.dumps(normalized).encode()).hexdigest()}


def glyphs(sample, png):
    capture = sample["capture"]
    image = png.read_bytes()
    if (sample["status"] != "observed" or hashlib.sha256(image).hexdigest() != capture["sha256"]
            or image[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"
            or [c["scalar"] for c in sample["cells"]] != GLYPHS):
        raise ValueError("Incomplete field screenshot or Unicode cell set")
    w, h = struct.unpack(">II", image[16:24])
    frame = png.with_suffix(".ppm")
    fw, fh, rgb = read_frame(frame)
    if (hashlib.sha256(frame.read_bytes()).hexdigest() != sample["frameSha256"]
            or not (0 < w <= 1024 and 0 < h <= 128)
            or (w, h) != (capture["width"], capture["height"]) or (fw, fh) != (w, h)):
        raise ValueError("Screen capture dimensions changed")
    masks = {}
    for cell in sample["cells"]:
        x, y, cw, ch = cell["crop"]
        if not (0 <= x < x+cw <= w and 0 <= y < y+ch <= h):
            raise ValueError("Glyph lies outside the field crop")
        pixels = b"".join(rgb[3*(row*w+x)+2:3*(row*w+x+cw):3] for row in range(y,y+ch))
        masks[f"U+{cell['scalar']:04X}"] = mask(cw, ch, pixels)
    if len({r["maskSha256"] for r in masks.values()}) != len(GLYPHS):
        raise ValueError("The native window painted duplicate glyph masks")
    return masks


def editing(row, spec):
    index = spec["text"].index(spec["target"])
    if (row["status"] != "observed" or row["text"] != spec["text"] or row["arrowIndices"] != spec["arrows"]
            or row["selected"] != spec["target"] or row["selectedAt"] != index or row["after"] != spec["after"]
            or len(row["dragScreen"]) != 3 or row["dragScreen"][0] >= row["dragScreen"][1]):
        raise ValueError(f"Native cursor, drag or delete differs for {spec['text']}")
    if spec["visualIndices"]:
        cells = row["characters"]
        if ([p["index"] for p in cells] != spec["visualIndices"]
                or any(p["right"] <= p["left"] for p in cells)):
            raise ValueError("Incomplete mixed-direction UIA geometry")
        sorted_cells = sorted(cells, key=lambda p: p["left"])
        if (len({p["left"] for p in sorted_cells}) != len(cells)
                or [p["index"] for p in sorted_cells] != [5, 3, 4, 2]):
            raise ValueError("Unexpected visual order of RTL letters and European digits")
