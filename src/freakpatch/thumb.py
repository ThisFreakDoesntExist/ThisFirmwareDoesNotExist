"""Thumb-2 branch encodings (ARMv7-M BL T1 and B T4) used to hook stock code."""

from __future__ import annotations

import struct

_RANGE = 1 << 24  # +-16 MB


def _encode(source: int, target: int, link: bool) -> bytes:
    offset = target - (source + 4)
    if offset % 2 or not -_RANGE <= offset < _RANGE:
        raise ValueError(f"branch {source:#010x} -> {target:#010x} out of range or misaligned")
    imm = offset & 0x1FFFFFF
    s = imm >> 24
    i1, i2 = (imm >> 23) & 1, (imm >> 22) & 1
    j1, j2 = (1 - i1) ^ s, (1 - i2) ^ s
    hi = 0xF000 | (s << 10) | ((imm >> 12) & 0x3FF)
    lo = (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | ((imm >> 1) & 0x7FF)
    return struct.pack("<HH", hi, lo)


def bl(source: int, target: int) -> bytes:
    """``bl target`` placed at ``source``."""
    return _encode(source, target, link=True)


def b_w(source: int, target: int) -> bytes:
    """``b.w target`` placed at ``source``."""
    return _encode(source, target, link=False)


def movw(rd: int, value: int) -> bytes:
    """``movw rd, #value`` (T3)."""
    if not 0 <= rd <= 14 or not 0 <= value <= 0xFFFF:
        raise ValueError(f"movw r{rd}, #{value:#x} is not encodable")
    hi = 0xF240 | ((value >> 11) & 1) << 10 | (value >> 12)
    lo = ((value >> 8) & 7) << 12 | rd << 8 | (value & 0xFF)
    return struct.pack("<HH", hi, lo)


def branch_target(source: int, code: bytes) -> int | None:
    """Target of a ``bl`` / ``b.w`` encoded in ``code`` at ``source``, or None if it is neither."""
    hi, lo = struct.unpack("<HH", code[:4])
    if hi & 0xF800 != 0xF000 or lo & 0xD000 not in (0xD000, 0x9000):
        return None
    s = (hi >> 10) & 1
    j1, j2 = (lo >> 13) & 1, (lo >> 11) & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((hi & 0x3FF) << 12) | ((lo & 0x7FF) << 1)
    if s:
        imm -= 1 << 25
    return source + 4 + imm
