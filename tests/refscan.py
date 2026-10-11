"""Every way an image could reach an address range, from the raw bytes alone.

Decodes every halfword offset as each Thumb form that carries a target (BL/B.W,
B<c>.W, B, B<c>, CBZ/CBNZ, LDR/LDRB/LDRH/LDRD/VLDR literal, ADR) and every
halfword-aligned word as a pointer. Data decoded as code can only add hits, so an
empty result is a proof that nothing in the image refers into the range; it doesn't
depend on a disassembler having found all the code.
"""

from __future__ import annotations

import struct


def references(payload: bytes, base: int, lo: int, hi: int) -> list[tuple[int, str]]:
    """``(source address, form)`` for every candidate reference into ``[lo, hi)`` from outside it."""
    hits: list[tuple[int, str]] = []

    def add(src: int, form: str, target: int) -> None:
        if lo <= target < hi and not lo <= src < hi:
            hits.append((src, form))

    for off in range(0, len(payload) - 3, 2):
        a = base + off
        h1, h2 = struct.unpack_from("<HH", payload, off)
        add(a, "word", (h1 | h2 << 16) & ~1)
        if h1 & 0xF800 == 0xF000 and h2 & 0xD000 in (0xD000, 0x9000):
            s = (h1 >> 10) & 1
            i1, i2 = 1 - (((h2 >> 13) & 1) ^ s), 1 - (((h2 >> 11) & 1) ^ s)
            imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
            add(a, "bl/b.w", a + 4 + imm - (s << 25))
        if h1 & 0xF800 == 0xF000 and h2 & 0xD000 == 0x8000:
            s = (h1 >> 10) & 1
            imm = (
                (s << 20)
                | (((h2 >> 11) & 1) << 19)
                | (((h2 >> 13) & 1) << 18)
                | ((h1 & 0x3F) << 12)
                | ((h2 & 0x7FF) << 1)
            )
            add(a, "b<c>.w", a + 4 + imm - (s << 21))
        if h1 & 0xF800 == 0xE000:
            imm = (h1 & 0x7FF) << 1
            add(a, "b", a + 4 + imm - ((imm & 0x800) << 1))
        if h1 & 0xF000 == 0xD000 and (h1 >> 8) & 0xF < 0xE:
            imm = (h1 & 0xFF) << 1
            add(a, "b<c>", a + 4 + imm - ((imm & 0x100) << 1))
        if h1 & 0xF500 == 0xB100:
            add(a, "cbz", a + 4 + ((((h1 >> 9) & 1) << 6) | (((h1 >> 3) & 0x1F) << 1)))
        aligned = (a + 4) & ~3
        if h1 & 0xF800 in (0x4800, 0xA000):
            add(a, "ldr/adr", aligned + ((h1 & 0xFF) << 2))
        up = 1 if h1 & 0x80 else -1  # the U bit: literal after or before the instruction
        if h1 & 0xFF7F in (0xF85F, 0xF81F, 0xF83F, 0xF91F, 0xF93F):
            add(a, "ldr.w", aligned + up * (h2 & 0xFFF))
        if h1 & 0xFE7F == 0xE85F or h1 & 0xFF3F == 0xED1F:
            add(a, "ldrd/vldr", aligned + up * ((h2 & 0xFF) << 2))
        if h1 & 0xFBFF in (0xF2AF, 0xF20F):
            imm = ((h1 >> 10) & 1) << 11 | ((h2 >> 12) & 7) << 8 | (h2 & 0xFF)
            add(a, "adr.w", aligned - imm if h1 & 0xFBFF == 0xF2AF else aligned + imm)
    return hits
