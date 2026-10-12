"""Combined builds and the mod-matrix CC table: static checks that need neither the firmware nor an emulator."""

from __future__ import annotations

import pytest

from freakpatch.patcher import RESERVED_CCS, STOCK_CCS, Part, Patch, PatchError, apply

MATRIX_REGION = (0x0802_CA94, 0x0802_CC04)
RELEASE_DEFAULT_CC = 72


@pytest.fixture(scope="module")
def patch() -> Patch:
    return Patch.load("release-matrix")


def test_combined_build_is_release_plus_matrix(patch: Patch) -> None:
    release, matrix = Patch.load("release"), Patch.load("matrix-cc")
    assert patch.parts == release.parts + matrix.parts
    assert patch.hooks == release.hooks + matrix.hooks
    assert patch.edits == release.edits + matrix.edits
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
