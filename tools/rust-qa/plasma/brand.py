"""Reproduce the tray's straight-alpha, network-order ARGB frames from the project SVG."""

import argparse
import hashlib
from pathlib import Path

SIZES = (16, 22, 32, 48, 64)
SOURCE = "8530d5c2ef894054cd5cd807794b7c4ea54952621f2455489173a988c81faa00"


def render(svg):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    if hashlib.sha256(svg.read_bytes()).hexdigest() != SOURCE:
        raise ValueError("Review the changed project logo before regenerating the tray artwork")
    result = bytearray()
    for size in SIZES:
        image = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg), size, size, True)
        width, height = image.get_width(), image.get_height()
        if not image.get_has_alpha() or image.get_n_channels() != 4 or width != size or not 0 < height <= size:
            raise ValueError("Unexpected RGBA dimensions for the branded tray frame")
        frame = bytearray(size * size * 4)
        rgba = image.get_pixels()
        for y in range(height):
            for x in range(width):
                at = y * image.get_rowstride() + x * 4
                r, g, b, a = rgba[at:at+4]
                dest = (((size-height)//2 + y) * size + x) * 4
                frame[dest:dest+4] = bytes((a, r, g, b))
        result.extend(frame)
    return bytes(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("argb", type=Path)
    parser.add_argument("--create", action="store_true", help="create a new file for a deliberate artwork update")
    args = parser.parse_args()
    frames = render(args.svg)
    if args.create:
        with args.argb.open("xb") as output:
            output.write(frames)
    elif args.argb.read_bytes() != frames:
        raise ValueError("The project logo and embedded SNI pixmaps differ")
    print(f"{len(frames)} ARGB bytes, SHA-256 {hashlib.sha256(frames).hexdigest()}")
