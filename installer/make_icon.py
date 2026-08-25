"""Build a small app icon for the installer and window."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _pixel(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    # BGRA-like RGB we convert later. Palette: dark panel + blue screen.
    bg = (16, 18, 22)
    panel = (27, 30, 38)
    accent = (110, 160, 255)
    mute = (90, 96, 108)

    nx = x / (size - 1)
    ny = y / (size - 1)
    pad = 0.16
    if nx < pad or nx > 1 - pad or ny < pad + 0.04 or ny > 0.78:
        if 0.44 <= nx <= 0.56 and 0.78 <= ny <= 0.90:
            return (*mute, 255)
        if 0.32 <= nx <= 0.68 and 0.88 <= ny <= 0.94:
            return (*mute, 255)
        return (*bg, 255)
    if nx < pad + 0.05 or nx > 1 - pad - 0.05 or ny < pad + 0.09 or ny > 0.72:
        return (*panel, 255)
    return (*accent, 255)


def _rgba_bitmap(size: int) -> bytes:
    rows = []
    for y in range(size - 1, -1, -1):
        row = bytearray()
        for x in range(size):
            r, g, b, a = _pixel(x, y, size)
            row.extend((b, g, r, a))
        rows.append(bytes(row))
    return b"".join(rows)


def _png(size: int) -> bytes:
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            r, g, b, a = _pixel(x, y, size)
            raw.extend((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def write_ico(path: Path) -> None:
    sizes = (16, 32, 48, 256)
    images = [_png(size) for size in sizes]
    count = len(sizes)
    offset = 6 + 16 * count
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    for size, data in zip(sizes, images, strict=True):
        width = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", width, width, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + b"".join(images))


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "rdpmanager.ico"
    write_ico(target)
    print(target)
