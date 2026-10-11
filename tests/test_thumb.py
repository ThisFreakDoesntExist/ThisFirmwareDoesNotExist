import pytest

from freakpatch import thumb


@pytest.mark.parametrize(
    ("source", "target", "encoded"),
    [
        (0x0008, 0x0132, "00f093f8"),  # forward bl, from clang's encoding of patches/release.S
        (0x015A, 0x0140, "fff7f1ff"),  # backward bl
    ],
)
def test_bl_matches_assembler(source: int, target: int, encoded: str) -> None:
    assert thumb.bl(source, target).hex() == encoded


@pytest.mark.parametrize("delta", [-0x0100_0000, -0x7A_3C1E, -2, 0, 2, 0x4_2A60, 0x00FF_FFFE])
@pytest.mark.parametrize("encode", [thumb.bl, thumb.b_w])
def test_round_trip(delta: int, encode) -> None:  # type: ignore[no-untyped-def]
    source = 0x0803_4682
    assert thumb.branch_target(source, encode(source, source + 4 + delta)) == source + 4 + delta


def test_out_of_range_and_odd_targets_rejected() -> None:
    with pytest.raises(ValueError):
        thumb.bl(0x0800_0000, 0x0A00_0000)
    with pytest.raises(ValueError):
        thumb.b_w(0x0800_0000, 0x0800_0101)


def test_non_branch_decodes_to_none() -> None:
    assert thumb.branch_target(0, bytes.fromhex("dff84481")) is None  # ldr.w r8, [pc, #...]
