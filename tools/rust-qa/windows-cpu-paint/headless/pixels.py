"""Compare every channel of each full BGRA frame against the independent Vulkan output."""
from array import array
import argparse
import hashlib
import json
from pathlib import Path


def compare(folder):
    rows = []
    for scale, width, height in (("1", 640, 400), ("1.5", 960, 600)):
        for frame in range(3):
            prefix = f"view-{scale}-{frame}"
            original = (folder / (prefix + "-wgpu.bgra")).read_bytes()
            count = width * height
            if len(original) != count * 4:
                raise ValueError(f"Unexpected reference dimensions: {prefix}")
            reference = array("I", original)
            if reference.itemsize != 4 or len(set(reference)) < 16:
                raise ValueError(f"Unexpected or flat reference: {prefix}")
            for mode in ("cached", "direct"):
                rendered = (folder / (prefix + f"-{mode}.bgra")).read_bytes()
                if len(rendered) != len(original):
                    raise ValueError(f"Incomplete software frame: {prefix} {mode}")
                exact = above2 = maximum = 0
                for a, b in zip(reference, array("I", rendered), strict=True):
                    if a == b:
                        exact += 1
                    else:
                        delta = max(abs((a >> shift & 255) - (b >> shift & 255)) for shift in (0, 8, 16, 24))
                        maximum = max(maximum, delta)
                        above2 += delta > 2
                rows.append({"scale": scale, "frame": frame, "mode": mode, "width": width, "height": height,
                             "pixels": count, "exact": exact, "above2": above2, "maxError": maximum,
                             "gpu": hashlib.sha256(original).hexdigest(),
                             "software": hashlib.sha256(rendered).hexdigest()})
    for offset in (0, 6):
        for key in ("gpu", "software"):
            for first, middle, last in ((0, 2, 4), (1, 3, 5)):
                a, b, c = [rows[offset + i][key] for i in (first, middle, last)]
                if a == b or a != c:
                    raise ValueError(f"The edited and restored images did not follow the input: {key}")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pixels", type=Path)
    args = parser.parse_args()
    observations = compare(args.pixels)
    print(json.dumps(observations, indent=2))
    if any(row["above2"] for row in observations):
        raise SystemExit(1)
