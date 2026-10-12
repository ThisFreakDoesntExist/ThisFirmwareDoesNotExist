"""The mod matrix over MIDI CC, in the combined Release + matrix build, checked statically and run under emulation."""

from __future__ import annotations

import hashlib
import struct

import pytest

pytest.importorskip("unicorn")

from emu import CC_MAP, GROUP_COUNT, PARAMS, Emu
from refscan import references

from freakpatch import mff, thumb
from freakpatch.patcher import MAIN_BASE, STOCK_CCS, Patch, PatchError, apply

REGION = (0x0802_CA94, 0x0802_CC04)
SYNTH_SLOT, SYNTH_HANDLER, STUB = 0x0807_40D4, 0x0802_CA95, 0x0802_B8ED
PARAM_INIT, PARAM_INIT_CALL = 0x0800_EB10, 0x0804_3530
CC_IN, CC_IN_HOOK = 0x0804_78A4, 0x0804_79D6
CC_OUT, CC_OUT_HOOK = 0x0802_39CC, 0x0802_3A02
CC_OUT_LISTENER = 0x2000_0C0C
MIDI_STATE, MIDI_SETTINGS = 0x2000_00E4, 0x2000_07A8
CC_OUT_SETTINGS_LITERAL = 0x0802_3B74
"""Literal pool word holding the settings the CC-out listener gates on (Knob Send CCs and so on)."""
FIRST_ROW, ROWS, SOURCES = 10, 7, 5
CC_TABLE = [
    [14, 15, 20, 21, 22],
    [25, 27, 30, 31, 3],
    [85, 86, 87, 88, 89],
    [90, 0, 104, 107, 108],
    [109, 110, 111, 112, 113],
    [114, 115, 116, 117, 118],
    [119, 75, 76, 77, 78],
]
CELLS = {cc: ((FIRST_ROW + row) << 8) | src for row, ccs in enumerate(CC_TABLE) for src, cc in enumerate(ccs) if cc}
ENV_TO_CUTOFF, FILTER_AMT = 0x0D01, 0x0605


def payload_of(raw: bytes) -> bytes:
    update = mff.Update.from_bytes(raw)
    return mff.main_payload(update.read(update.main_name))


def signed(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


@pytest.fixture(scope="module")
def patch() -> Patch:
    return Patch.load("release-matrix")


@pytest.fixture(scope="module")
def combined_mff(stock_mff: bytes, patch: Patch) -> bytes:
    return apply(stock_mff, patch)


@pytest.fixture(scope="module")
def combined_payload(combined_mff: bytes) -> bytes:
    return payload_of(combined_mff)


@pytest.fixture(scope="module")
def release_payload(stock_mff: bytes) -> bytes:
    """The hardware-tested Release build: what every non-matrix CC must keep doing."""
    return payload_of(apply(stock_mff, Patch.load("release")))


def stretch(value: int) -> int:
    """Stock's 7-to-15-bit stretch of a CC value."""
    return (value << 8) | (value << 1) | (value >> 6)


def amount_of(value: int) -> int:
    """The signed matrix amount for a CC value: stock's Filter Amt formula, CC 64 = 0."""
    return 0 if value == 64 else (stretch(value) - 0x4000) * 2


def booted(payload: bytes, patch: Patch | None) -> Emu:
    """The parameter object as boot leaves it: the constructor through its caller's hook, if patched."""
    e = Emu(payload, construct=False)
    e.call(patch.address("matrix_boot") if patch else PARAM_INIT, PARAMS, count=3_000_000)
    return e


def send_cc(e: Emu, cc: int, value: int) -> None:
    """Run the stock MIDI input handler on one Control Change, channel 1."""
    e.write(MIDI_STATE, b"\x00")  # not 0xFF: the handler bails on 0xFF
    e.write(MIDI_SETTINGS + 0x3C, b"\x7f")  # input channel: all
    for side_effect in (0x0804_8524, 0x0804_95C0, 0x0805_5ED8, 0x0804_7FC4):  # MIDI thru, UI, bookkeeping
        e.stub(side_effect)
    msg = 0x2001_0000
    e.write(msg, bytes([0xB0, cc, value, 0]))
    e.call(CC_IN, msg, count=2_000_000)


def sent_cc_value(e: Emu, payload: bytes, pid: int, value: int) -> int | None:
    """Run the stock CC-out listener on one parameter change; the CC value it queues, or None."""
    settings = struct.unpack_from("<I", payload, CC_OUT_SETTINGS_LITERAL - MAIN_BASE)[0]
    e.write(settings + 0x40, b"\x01\x01\x01")
    e.write(CC_OUT_LISTENER + 0x30, b"\x00")
    e.write(CC_OUT_LISTENER + 0x10, b"\xff\xff\xff")
    e.stub(0x0803_B7BC, lambda emu: emu.set_regs(r0=1))  # MIDI out queue: report "sent"
    event = 0x2001_0000
    e.write(event, struct.pack("<HHh", pid, 0, value))
    e.call(CC_OUT, CC_OUT_LISTENER, event)
    if e.read(CC_OUT_LISTENER + 0x30, 1) == b"\x00":
        return None
    assert e.read16(CC_OUT_LISTENER + 0x10) == pid
    return e.read(CC_OUT_LISTENER + 0x12, 1)[0]


# ------------------------------------------------------------------ patched file


def test_combined_build_keeps_the_release_code(patch: Patch) -> None:
    release = Patch.load("release")
    assert patch.parts[0] == release.parts[0]
    assert set(release.hooks) <= set(patch.hooks) and set(release.edits) <= set(patch.edits)
    assert patch.parts[1] == Patch.load("matrix-cc").parts[0]


def test_only_patch_bytes_change(stock_mff: bytes, stock_payload: bytes, combined_mff: bytes, patch: Patch) -> None:
    assert len(combined_mff) == len(stock_mff)
    after = payload_of(combined_mff)
    changed = {i for i in range(len(stock_payload)) if stock_payload[i] != after[i]}
    assert changed <= patch.touched()
    for part in patch.parts:
        start = part.region[0] - MAIN_BASE
        assert after[start : start + len(part.code)] == part.code


def test_hook_sites_held_the_expected_stock_instructions(stock_payload: bytes) -> None:
    def at(address: int, n: int = 4) -> bytes:
        return stock_payload[address - MAIN_BASE : address - MAIN_BASE + n]

    assert thumb.branch_target(PARAM_INIT_CALL, at(PARAM_INIT_CALL)) == PARAM_INIT
    assert at(CC_IN_HOOK) == bytes.fromhex("c9f30723")  # ubfx r3, r9, #8, #8
    assert at(CC_IN_HOOK + 4, 2) == bytes.fromhex("1f2b")  # cmp r3, #0x1f: runs after the hook returns
    assert at(CC_OUT_HOOK) == bytes.fromhex("2d12e9b2")  # asrs r5, r5, #8; uxtb r1, r5
    assert struct.unpack("<I", at(SYNTH_SLOT))[0] == SYNTH_HANDLER
    assert at(STUB & ~1, 2) == bytes.fromhex("7047")  # bx lr


def test_region_is_reached_only_through_the_patch(stock_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    assert {src for src, _ in references(stock_payload, MAIN_BASE, *REGION)} == {SYNTH_SLOT}
    matrix_hooks = {h.site for h in patch.hooks if patch.part_of(h.symbol).region == REGION}
    assert {src for src, _ in references(combined_payload, MAIN_BASE, *REGION)} == matrix_hooks


def test_cc_table(patch: Patch) -> None:
    ccs = patch.mapped_ccs()
    assert ccs == set(CELLS) and len(CELLS) == ROWS * SOURCES - 1
    assert not ccs & STOCK_CCS and 72 not in ccs and all(1 <= cc <= 119 for cc in ccs)
    reserved = {0, 1, 6, 7, 11, 32, 38, *range(64, 70), *range(96, 102)}  # bank, wheel, data, volume, pedals, RPN
    assert not ccs & reserved


def test_release_cc_cannot_take_a_matrix_cc(stock_mff: bytes, patch: Patch) -> None:
    with pytest.raises(PatchError, match="mod matrix"):
        apply(stock_mff, patch, release_cc=14)
    code = payload_of(apply(stock_mff, patch, release_cc=80))[0x0802_BB60 - MAIN_BASE :]
    assert code[patch.symbols["release_cc"]] == 80


def test_default_build_is_deterministic(combined_mff: bytes, stock_mff: bytes, patch: Patch) -> None:
    assert hashlib.sha256(apply(stock_mff, patch)).digest() == hashlib.sha256(combined_mff).digest()


# ------------------------------------------------------------------ boot


def test_boot_maps_every_cell_both_ways(combined_payload: bytes, patch: Patch) -> None:
    e = booted(combined_payload, patch)
    for cc, pid in CELLS.items():
        assert e.read(CC_MAP + cc * 2, 2) == bytes([pid & 0xFF, pid >> 8])
        assert e.read(e.read32(PARAMS + 0xEC + (pid >> 8) * 4) + (pid & 0xFF), 1) == bytes([cc])
    assert e.read32(GROUP_COUNT) == 21  # Release is still registered
    assert e.read(CC_MAP + 72 * 2, 2) == bytes([0, 20])


def test_boot_changes_nothing_else(stock_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    stock, ours = booted(stock_payload, None), booted(combined_payload, patch)
    stock_map, our_map = bytearray(stock.read(CC_MAP, 256)), bytearray(ours.read(CC_MAP, 256))
    for cc in [*CELLS, 72]:
        our_map[cc * 2 : cc * 2 + 2] = stock_map[cc * 2 : cc * 2 + 2]
    assert our_map == stock_map
    for group in range(20):
        size = len(CC_TABLE[0]) + 1 if FIRST_ROW <= group < FIRST_ROW + ROWS else 16
        stock_ccs = bytearray(stock.read(stock.read32(PARAMS + 0xEC + group * 4), size))
        our_ccs = bytearray(ours.read(ours.read32(PARAMS + 0xEC + group * 4), size))
        if FIRST_ROW <= group < FIRST_ROW + ROWS:
            for src in range(SOURCES):
                if CC_TABLE[group - FIRST_ROW][src]:
                    our_ccs[src] = stock_ccs[src]
        assert our_ccs == stock_ccs, f"group {group}"


# ------------------------------------------------------------------ MIDI in


@pytest.mark.parametrize("value", [0, 1, 32, 63, 64, 65, 96, 127])
@pytest.mark.parametrize("cc", [14, 22, 90, 119, 78])
def test_cc_sets_a_signed_amount(combined_payload: bytes, patch: Patch, cc: int, value: int) -> None:
    e = booted(combined_payload, patch)
    e.set_param(CELLS[cc], 0x1234)
    send_cc(e, cc, value)
    assert signed(e.param(CELLS[cc])) == amount_of(value)
    assert {0: -0x8000, 64: 0, 127: 0x7FFE}.get(value, amount_of(value)) == amount_of(value)  # -100%, 0, +100%


def test_matches_stocks_own_filter_amt_conversion(stock_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    """Stock writes CC 26 into Env -> Cutoff with the same formula the patch uses for every cell."""
    for value in range(128):
        stock = booted(stock_payload, None)
        stock.set_param(ENV_TO_CUTOFF, 0x1234)
        stock.set_param(FILTER_AMT, 0x1234)  # stock skips CC 26 when it equals Filter Amt's current value
        send_cc(stock, 26, value)
        ours = booted(combined_payload, patch)
        ours.set_param(CELLS[15], 0x1234)  # Wave <- Env
        send_cc(ours, 15, value)
        assert ours.param(CELLS[15]) == stock.param(ENV_TO_CUTOFF), value


@pytest.mark.parametrize(("cc", "pid"), [(23, 0x0101), (105, 0x0601), (26, FILTER_AMT), (72, 0x1400)])
def test_other_ccs_behave_as_before(
    release_payload: bytes, combined_payload: bytes, patch: Patch, cc: int, pid: int
) -> None:
    for value in (0, 1, 64, 127):
        before, after = booted(release_payload, None), booted(combined_payload, patch)
        send_cc(before, cc, value)
        send_cc(after, cc, value)
        assert after.param(pid) == before.param(pid)
        assert after.param(ENV_TO_CUTOFF) == before.param(ENV_TO_CUTOFF)


# ------------------------------------------------------------------ MIDI out


@pytest.mark.parametrize(
    ("amount", "value"),
    [(-0x8000, 0), (-0x7FFF, 0), (-0x3F02, 32), (0, 64), (0x0306, 65), (0x7FFE, 127), (0x7FFF, 127)],
)
def test_amount_is_sent_as_its_cc_value(combined_payload: bytes, patch: Patch, amount: int, value: int) -> None:
    e = booted(combined_payload, patch)
    assert sent_cc_value(e, combined_payload, CELLS[30], amount) == value


def test_every_value_round_trips(combined_payload: bytes, patch: Patch) -> None:
    for value in range(128):
        e = booted(combined_payload, patch)
        send_cc(e, 110, value)
        amount = signed(e.param(CELLS[110]))
        assert sent_cc_value(booted(combined_payload, patch), combined_payload, CELLS[110], amount) == value


@pytest.mark.parametrize(("pid", "value"), [(0x0101, 0x7FFF), (0x0601, 0x4081), (0x1400, 0x1234), (FILTER_AMT, 0x2000)])
def test_other_parameters_are_sent_as_before(
    release_payload: bytes, combined_payload: bytes, patch: Patch, pid: int, value: int
) -> None:
    before = sent_cc_value(booted(release_payload, None), release_payload, pid, value)
    assert before == value >> 8
    assert sent_cc_value(booted(combined_payload, patch), combined_payload, pid, value) == before


def test_unmapped_cells_send_nothing(combined_payload: bytes, patch: Patch) -> None:
    e = booted(combined_payload, patch)
    assert sent_cc_value(e, combined_payload, ENV_TO_CUTOFF, 0x1000) is None  # Filter Amt sends CC 26 instead
    assert sent_cc_value(booted(combined_payload, patch), combined_payload, 0x0A05, 3) is None  # Dest
