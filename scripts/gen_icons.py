"""Generate flat-colour PWA icons with no third-party deps (Pillow is unavailable
under Smart App Control). Replace the output with real artwork later."""
import struct
import zlib
from pathlib import Path

_OUT = Path(__file__).resolve().parents[1] / "apps/web/public"
_BG = (11, 15, 25)        # #0b0f19  (matches manifest background_color)
_FG = (56, 189, 248)      # #38bdf8  sky-400 accent block


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png(size: int) -> bytes:
    pad = size // 4
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        for x in range(size):
            inside = pad <= x < size - pad and pad <= y < size - pad
            raw += bytes(_FG if inside else _BG)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


if __name__ == "__main__":
    for s in (192, 512):
        (_OUT / f"icon-{s}.png").write_bytes(_png(s))
        print("wrote", _OUT / f"icon-{s}.png")
