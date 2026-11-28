"""Check named 64-bit import objects and the linked PE import directory."""

import struct
from collections import defaultdict

ARM64 = 0xAA64
AMD64 = 0x8664


def import_headers(path, machine=ARM64):
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("Invalid COFF archive")
    pos = 8
    symbols = defaultdict(dict)
    coff = 0
    while pos < len(data):
        header = data[pos:pos + 60]
        size = int(header[48:58])
        blob = data[pos + 60:pos + 60 + size]
        if header[58:60] != b"`\n" or len(blob) != size:
            raise ValueError(f"Bad archive member at {pos}")
        pos += 60 + size + size % 2
        if header[:16].rstrip() in (b"/", b"//"):
            continue
        if blob[:4] != b"\0\0\xff\xff":
            if struct.unpack_from("<H", blob)[0] != machine:
                raise ValueError("Wrong COFF descriptor machine")
            coff += 1
            continue
        _, _, version, arch, _, length, hint, flags = struct.unpack_from("<HHHHIIHH", blob)
        if (version, arch, length, flags) != (0, machine, len(blob) - 20, 4):
            raise ValueError("Unexpected import version, machine, size, lookup-by-name or function type")
        symbol, library, tail = blob[20:].decode("ascii").split("\0")
        if tail or symbol in symbols[library]:
            raise ValueError(f"Duplicate or malformed import in {library}")
        symbols[library][symbol] = hint
    if pos != len(data):
        raise ValueError("Archive alignment mismatch")
    return dict(symbols), coff


def pe_imports(path, machine=ARM64):
    image = path.read_bytes()
    pe, = struct.unpack_from("<I", image, 0x3C)
    arch, count = struct.unpack_from("<HH", image, pe + 4)
    opt_size, = struct.unpack_from("<H", image, pe + 20)
    opt = pe + 24
    if (image[pe:pe+4], arch, struct.unpack_from("<H", image, opt)[0]) != (b"PE\0\0", machine, 0x20B):
        raise ValueError(f"Expected a PE32+ image with machine {machine:#x}")
    sections = [struct.unpack_from("<IIII", image, opt + opt_size + i * 40 + 8)
                for i in range(count)]

    def offset(rva):
        for _, address, raw_size, raw in sections:
            if address <= rva < address + raw_size:
                return raw + rva - address
        raise ValueError(f"Unmapped RVA {rva:#x}")

    def string(rva):
        start = offset(rva)
        return image[start:image.index(b"\0", start)].decode("ascii")

    imports = {}
    import_rva, import_size = struct.unpack_from("<II", image, opt + 112 + 8)
    start = offset(import_rva)
    for pos in range(start, start + import_size, 20):
        thunk, _, _, name, _ = struct.unpack_from("<5I", image, pos)
        if not name:
            return imports
        library = string(name)
        imports[library] = []
        slot = offset(thunk)
        while target := struct.unpack_from("<Q", image, slot)[0]:
            if target & (1 << 63):
                imports[library].append(f"#{target & 0xffff}")
            else:
                imports[library].append(string(target + 2))
            slot += 8
    raise ValueError("Unterminated import directory")
