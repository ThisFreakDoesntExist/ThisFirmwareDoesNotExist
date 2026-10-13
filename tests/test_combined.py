"""Combined builds and the mod-matrix CC table: static checks that need neither the firmware nor an emulator."""

from __future__ import annotations

import pytest

from freakpatch import mff
from freakpatch.patcher import OLED_BASE, RESERVED_CCS, STOCK_CCS, Edit, Part, Patch, PatchError, apply

MATRIX_REGION = (0x0802_CA94, 0x0802_CC04)
RELEASE_DEFAULT_CC = 72
CURVE_SITE = 0x0804_F7C8
"""Envelope popup: fp7's curve_time hook, which release-matrix leaves stock (slot 2 = Decay)."""
GRAPH_EDITS = (
    Edit(0x0804_F7E0, "movw", 0x1400, 0),  # slot 4: Release instead of 0x605
    Edit(0x0800_8342, "half", 0x9E02, image="oled"),  # ldr r6, [sp, #8]
    Edit(0x0800_835E, "half", 0x08B6, image="oled"),  # lsrs r6, r6, #2
)


@pytest.fixture(scope="module")
def patch() -> Patch:
    return Patch.load("release-matrix")


def test_combined_build_is_release_plus_matrix(patch: Patch) -> None:
    release, matrix = Patch.load("release"), Patch.load("matrix-cc")
    assert patch.parts == release.parts + matrix.parts
    assert patch.hooks == tuple(h for h in release.hooks if h.site != CURVE_SITE) + matrix.hooks
    assert patch.edits == release.edits + matrix.edits + GRAPH_EDITS
    assert patch.options == release.options and patch.cc_table == matrix.cc_table
    assert patch.parts[1].region == MATRIX_REGION


def test_symbols_resolve_in_their_own_part(patch: Patch) -> None:
    for part in patch.parts:
        for symbol, offset in part.symbols.items():
            assert patch.address(symbol) == part.region[0] + offset
    with pytest.raises(PatchError, match="no symbol"):
        patch.address("nonexistent")


def test_single_region_accessors_refuse_a_combined_build(patch: Patch) -> None:
    with pytest.raises(PatchError, match="2 code regions"):
        _ = patch.region
    assert Patch.load("release").region == (0x0802_BB60, 0x0802_BD10)


def test_cc_table() -> None:
    ccs = Patch.load("matrix-cc").mapped_ccs()
    assert len(ccs) == 34 and len(set(ccs)) == 34  # 35 cells; Env -> Cutoff keeps stock CC 26
    assert not set(ccs) & (STOCK_CCS | RESERVED_CCS | {RELEASE_DEFAULT_CC})
    assert all(1 <= cc <= 119 for cc in ccs)
    assert 88 in RESERVED_CCS and 88 not in ccs  # high-resolution velocity prefix


@pytest.mark.parametrize(
    ("table", "message"),
    [
        (bytes([14, 14]), "twice"),
        (bytes([14, 64]), "must not"),
        (bytes([14, 23]), "must not"),
        (bytes([72]), "must not"),
    ],
)
def test_bad_cc_tables_are_refused(stock_mff: bytes, patch: Patch, table: bytes, message: str) -> None:
    matrix = patch.parts[1]
    offset = matrix.symbols["matrix_ccs"]
    code = matrix.code[:offset] + table + bytes(35 - len(table)) + matrix.code[offset + 35 :]
    bad = Patch(
        patch.name,
        patch.description,
        (patch.parts[0], Part(matrix.region, code, matrix.symbols)),
        patch.hooks,
        patch.edits,
        patch.options,
        patch.cc_table,
    )
    with pytest.raises(PatchError, match=message):
        apply(stock_mff, bad)


def _images(raw: bytes) -> dict[str, bytes]:
    update = mff.Update.from_bytes(raw)
    return {m.info.filename: m.data for m in update.members}


def test_curve_draws_decay_and_release_separately(stock_mff: bytes, patch: Patch) -> None:
    """Slot 2 stays Decay, slot 4 carries Release, and the OLED takes the release width from slot 4."""
    stock, out = _images(stock_mff), _images(apply(stock_mff, patch))
    main = next(n for n in stock if n.startswith(mff.MAIN_IMAGE_PREFIX))
    oled = next(n for n in stock if n.startswith(mff.OLED_IMAGE_PREFIX))
    assert [n for n in stock if stock[n] != out[n]] == [main, oled]  # info.json and the other chips untouched

    main_payload = mff.main_payload(out[main])
    assert main_payload[CURVE_SITE - 0x0800_C000 :][:4] == bytes.fromhex("fff7d8fa")  # stock bl 0x0804ED7C
    assert main_payload[0x0804_F7E0 - 0x0800_C000 :][:4] == bytes.fromhex("41f20040")  # movw r0, #0x1400

    old, new = mff.main_payload(stock[oled]), mff.main_payload(out[oled])
    assert len(out[oled]) == len(stock[oled]) == 81_712
    assert out[oled][0] == stock[oled][0] == 1  # image number
    changed = [OLED_BASE + i for i in range(len(old)) if old[i] != new[i]]
    assert changed == [0x0800_8342, 0x0800_8343, 0x0800_835E, 0x0800_835F]
    assert old[0x8342:0x8344] == old[0x835E:0x8360] == bytes.fromhex("89b2")  # uxth r1, r1, both
    assert new[0x8342:0x8344] + new[0x835E:0x8360] == bytes.fromhex("029eb608")


def test_release_build_keeps_the_stock_oled_image(stock_mff: bytes) -> None:
    stock, out = _images(stock_mff), _images(apply(stock_mff, Patch.load("release")))
    oled = next(n for n in stock if n.startswith(mff.OLED_IMAGE_PREFIX))
    assert out[oled] == stock[oled]
