"""Parse real TextEdit state and software-rendered frame readbacks for the synthetic cases."""
from collections import Counter
import hashlib
import time

CASES = {
    "glyphs": ("あ界⬟.jpg", list(range(7))),
    "mixed": ("L-بتث-R.jpg", [0, 1, 4, 3, 2, 5, 6, 7, 8, 9, 10]),
    "numbers": ("L-ب12ت-R.jpg", [0, 1, 5, 3, 4, 2, 6, 7, 8, 9, 10, 11]),
}


def fields(messages):
    result = []
    for row in messages.splitlines():
        if row.startswith("FONT_FIELD\t"):
            _, primary, secondary, y, caret_x, text, layout = row.split("\t")
            glyphs = []
            for item in layout.split():
                code, x, width = item.split(":")
                glyphs.append({"character": chr(int(code, 16)), "x": float(x), "width": float(width)})
            result.append(dict(primary=int(primary), secondary=int(secondary), centerY=float(y), caretX=int(caret_x),
                               text=text, glyphs=glyphs))
    return result


def read_frame(path):
    with path.open("rb") as stream:
        if stream.readline() != b"P6\n":
            raise ValueError("Unexpected frame encoding")
        width, height = map(int, stream.readline().split())
        if stream.readline() != b"255\n":
            raise ValueError("Unexpected frame depth")
        pixels = stream.read()
    if len(pixels) != width * height * 3:
        raise ValueError("Truncated frame")
    return width, height, pixels


def pixel_mask(frame, bounds, threshold=None):
    width, height, pixels = frame
    x0, y0, x1, y1 = bounds
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("Glyph cell is outside the read-back frame")
    values = {(x, y): pixels[3 * (y * width + x)] for y in range(y0, y1) for x in range(x0, x1)}
    if threshold is None:
        # Compare the foreground and background on either theme, including antialiasing.
        background = Counter(values.values()).most_common(1)[0][0]
        values = {point: abs(value - background) for point, value in values.items()}
        threshold = max(1, max(values.values()) / 2)
    ink = {point for point, value in values.items() if value >= threshold}
    if not ink:
        return set()
    left, top = map(min, zip(*ink))
    return {(x - left, y - top) for x, y in ink}


def masks(frame, messages):
    result = {}
    bounds_by_code = {}
    for row in messages.splitlines():
        if row.startswith("FONT_CELL "):
            _, code, has, *bounds = row.split()
            bounds_by_code[code] = tuple(map(int, bounds))
            ink = pixel_mask(frame, bounds_by_code[code], 96)
            if not ink:
                digest = None
            else:
                left, top = map(min, zip(*ink))
                right, bottom = map(max, zip(*ink))
                data = bytes((x, y) in ink for y in range(top, bottom + 1) for x in range(left, right + 1))
                size = f"{right - left + 1}x{bottom - top + 1}:".encode()
                digest = hashlib.sha256(size + data).hexdigest()
            result[code] = {"hasGlyph": has == "true", "inkPixels": len(ink), "maskSha256": digest}
    if len(result) != 8:
        raise ValueError("Expected eight independent rendered cells")
    return result, bounds_by_code


def identify_glyph(field, samples):
    # Fractional cell and edit origins can round the boundary of antialiased ink differently.
    # Give every candidate the same one-physical-pixel registration and confidence thresholds.
    offsets = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    scores, alignment = {}, {}
    for code, sample in samples.items():
        best_score, best_offset = -1, (0, 0)
        for dx, dy in offsets:
            shifted = {(x + dx, y + dy) for x, y in sample}
            score = len(field & shifted) / max(1, len(field | shifted))
            if score > best_score:
                best_score, best_offset = score, (dx, dy)
        scores[code], alignment[code] = round(best_score, 3), best_offset
    best, second, *_ = sorted(scores, key=scores.get, reverse=True)
    observed = None
    if best != "10FFFD" and scores[best] >= .60 and scores[best] - scores[second] >= .2:
        observed = chr(int(best, 16))
    return {"character": observed, "maskOverlap": scores, "referenceOffsets": alignment}


def arabic_pixels(frame, bounds, initial):
    # These isolated characters on either side of the digits use the same shapes as the cells.
    # Classify the actual field pixels without using Galley.chr to identify their contents.
    samples = {k: pixel_mask(frame, bounds[k]) for k in ("628", "62A", "62B", "10FFFD")}
    scale = (bounds["41"][3] - bounds["41"][1]) / 64
    y = initial["centerY"]
    measured = []
    for g in sorted(initial["glyphs"], key=lambda item: item["x"]):
        if not (g["width"] > 0 and "\u0600" <= g["character"] <= "\u06ff"):
            continue
        xmin, xmax = round(g["x"]), round(g["x"] + g["width"])
        box = (xmin, round(y - 19 * scale), xmax, round(y + 19 * scale))
        field = pixel_mask(frame, box)
        measured.append(identify_glyph(field, samples))
    return measured


def wait_value(function, process, log, seconds=20):
    deadline = time.monotonic() + seconds
    while True:
        messages = log.read_text(encoding="utf-8", errors="replace")
        if value := function(messages):
            return value
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError(f"Expected native observation did not arrive. Child: {process.poll()}\n{messages[-3200:]}")
        time.sleep(.025)


def selection(field):
    first, last = sorted([field["primary"], field["secondary"]])
    return field["text"][first:last]


def check_case(profile, name, controls, process, log, directory):
    text, visual_to_logical = CASES[name]
    messages = wait_value(lambda m: m if "FONT_FRAME " in m else None, process, log)
    initial = fields(messages)[-1]
    if initial["text"] != text:
        raise ValueError("Synthetic model started with the wrong text")
    frame = read_frame(directory / "observed.ppm")
    cells, bounds = masks(frame, messages)
    missing = cells["10FFFD"]
    targets = [v for k, v in cells.items() if k not in ("41", "10FFFD")]
    unique = len({v["maskSha256"] for v in cells.values()})
    if missing["hasGlyph"] or not cells["41"]["hasGlyph"] or not cells["41"]["inkPixels"]:
        raise ValueError("Invalid Latin or unmapped control")
    if profile == "latin":
        glyphs_pass = all(not v["hasGlyph"] and v["maskSha256"] == missing["maskSha256"] for v in targets)
    else:
        glyphs_pass = unique == len(cells) and all(v["hasGlyph"] and v["inkPixels"] for v in targets)
    visible = sorted((g for g in initial["glyphs"] if g["width"] > 0), key=lambda g: g["x"])
    expected = "".join(text[i] for i in visual_to_logical)
    actual = "".join(g["character"] for g in visible)
    result = dict(profile=profile, name=name, before=text, expectedVisual=expected, observedVisual=actual,
                  glyphs=initial["glyphs"], visualOrderMatches=expected == actual, cells=cells,
                  renderedCoverageMatches=glyphs_pass)
    if name == "numbers":
        result["fieldPixelMatches"] = arabic_pixels(frame, bounds, initial)
        raster = [match["character"] for match in result["fieldPixelMatches"]]
        result["fieldPixelOrderMatchesOracle"] = raster == [text[5], text[2]]
    if profile == "latin":
        return result

    def read_after(start, predicate):
        def read(messages):
            return next((f for f in reversed(fields(messages)[start:]) if predicate(f)), None)
        return wait_value(read, process, log)

    def count():
        return len(fields(log.read_text(encoding="utf-8", errors="replace")))

    y = round(initial["centerY"])
    if name == "glyphs":
        first = visible[0]
        controls.click(round(first["x"] + first["width"] * .1), y)
        read_after(0, lambda f: (f["primary"], f["secondary"]) == (0, 0))
        start = count()
        controls.key("Right")
        caret = read_after(start, lambda f: f["primary"] == f["secondary"])
        result["caretAfterRightFromStart"] = caret["primary"]
        time.sleep(.7)  # A separate drag, outside the platform's double-click interval.
        target = next(g for g in visible if g["character"] == "界")
        expected_index = 1
    else:
        target = next(g for g in visible if "\u0600" <= g["character"] <= "\u06ff")
        expected_index = next(i for i in visual_to_logical if "\u0600" <= text[i] <= "\u06ff")
        # Start on one side of an interior cluster boundary. The Latin prefix fixes
        # paragraph direction; these interior carets have unambiguous logical positions.
        piece = target if name == "mixed" else next(g for g in visible if g["character"] == "1")
        start = count()
        fraction = .87 if name == "mixed" else .13
        controls.click(round(piece["x"] + piece["width"] * fraction), y)
        clicked = read_after(start, lambda f: f["primary"] >= 0)
        start = count()
        controls.key("Right")
        right = read_after(start, lambda f: f["primary"] >= 0)
        start = count()
        controls.key("Left")
        left = read_after(start, lambda f: f["primary"] >= 0)
        expected_carets = [4, 3, 4] if name == "mixed" else [3, 4, 3]
        indices = [f["primary"] for f in (clicked, right, left)]
        positions = [f["caretX"] for f in (clicked, right, left)]
        result.update(arrowLogicalIndices=indices, expectedArrowIndices=expected_carets,
                      arrowVisualPixels=positions,
                      keyboardMatches=indices == expected_carets and positions[0] < positions[1]
                      and positions[0] == positions[2])
        time.sleep(.7)
    start = count()
    controls.drag(round(target["x"] + target["width"] * .12),
                  round(target["x"] + target["width"] * .88), y)
    selected = read_after(start, lambda f: f["primary"] != f["secondary"])
    start = count()
    controls.key("Delete")
    after = read_after(start, lambda f: f["text"] != text)
    expected_after = text[:expected_index] + text[expected_index + 1:]
    result.update(expectedSelected=text[expected_index], selected=selection(selected),
                  selectedRange=[selected["primary"], selected["secondary"]],
                  afterDelete=after["text"], expectedAfterDelete=expected_after,
                  editMatches=(selection(selected) == text[expected_index] and after["text"] == expected_after))
    return result
