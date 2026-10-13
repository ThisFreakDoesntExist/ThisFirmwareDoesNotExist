"""The mod matrix over MIDI CC, in the combined Release + matrix build, run under emulation against the user's own
official firmware. Static checks that need no emulator are in test_combined.py."""

from __future__ import annotations

import struct

import pytest

pytest.importorskip("unicorn")

from emu import CC_MAP, GROUP_COUNT, PARAM_SET, PARAMS, Emu
from refscan import references

from freakpatch import mff, thumb
from freakpatch.patcher import MAIN_BASE, Patch, PatchError, apply

REGION = (0x0802_CA94, 0x0802_CC04)
SYNTH_SLOT, SYNTH_HANDLER, STUB = 0x0807_40D4, 0x0802_CA95, 0x0802_B8ED
PARAM_INIT, PARAM_INIT_CALL = 0x0800_EB10, 0x0804_3530
CC_IN = 0x0804_78A4
CC_OUT_LISTENER, LISTENER_OBJ = 0x0802_39CC, 0x2000_0C0C
SET_AND_SEND, SET_GATED = 0x0802_682C, 0x0802_473C
SEND_QUEUE, SEND_DIN, SEND_USB = 0x0803_B7BC, 0x0804_7FC4, 0x0804_7DF8
MIDI_STATE, SETTINGS = 0x2000_00E4, 0x2000_07A8
"""Settings bytes: +0x3C MIDI input channel, +0x40 send CCs, +0x41 MIDI output, +0x42 Local Control, +0x47 the
set-and-send function's gate."""
MATRIX_UI, IO_LINK, IO_SEND, LED_FRAME = 0x2000_35A4, 0x2000_05A0, 0x0802_1414, 0x0802_1AB0
"""The matrix controller (+4: LED mode, 1 = amounts), the I/O-link sender object, its queue function and stock's LED
frame builder."""
PANEL_PARAMS, PANEL_PARAM_COUNT = 0x0807_3788, 24
"""The fixed list of parameters the pot and encoder handlers drive, with their own CC senders."""
FIRST_ROW, ROWS, SOURCES = 10, 7, 5
CC_TABLE = [
    [14, 15, 20, 21, 22],
    [25, 27, 30, 31, 3],
    [85, 86, 87, 80, 89],
    [90, 0, 104, 107, 108],
    [109, 110, 111, 112, 113],
    [114, 115, 116, 117, 118],
    [119, 75, 76, 77, 78],
]
CELLS = {cc: ((FIRST_ROW + row) << 8) | src for row, ccs in enumerate(CC_TABLE) for src, cc in enumerate(ccs) if cc}
ENV_TO_CUTOFF, FILTER_AMT, CUTOFF, RELEASE_ID = 0x0D01, 0x0605, 0x0101, 0x1400
HOOKS = {  # matrix hook site -> the stock bytes it replaces
    0x0804_79D6: "c9f30723",  # ubfx r3, r9, #8, #8
    0x0802_3A02: "2d12e9b2",  # asrs r5, r5, #8; uxtb r1, r5
    0x0802_6874: "3f12f9b2",  # asrs r7, r7, #8; uxtb r1, r7
    0x0802_3C82: "db5d7f2b",  # ldrb r3, [r3, r7]; cmp r3, #0x7f
    0x0802_4756: "5b5d7f2b",  # ldrb r3, [r3, r5]; cmp r3, #0x7f
}


def payload_of(raw: bytes) -> bytes:
    update = mff.Update.from_bytes(raw)
    return mff.main_payload(update.read(update.main_name))


def signed(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def stretch(value: int) -> int:
    """Stock's 7-to-15-bit stretch of a CC value."""
    return (value << 8) | (value << 1) | (value >> 6)


def amount_of(value: int) -> int:
    """The signed matrix amount for a CC value: stock's Filter Amt formula, CC 64 = 0."""
    return 0 if value == 64 else (stretch(value) - 0x4000) * 2


@pytest.fixture(scope="module")
def patch() -> Patch:
    return Patch.load("release-matrix")


@pytest.fixture(scope="module")
def combined_payload(stock_mff: bytes, patch: Patch) -> bytes:
    return payload_of(apply(stock_mff, patch))


@pytest.fixture(scope="module")
def release_payload(stock_mff: bytes) -> bytes:
    """The hardware-tested Release build: what every non-matrix parameter must keep doing."""
    return payload_of(apply(stock_mff, Patch.load("release")))


def booted(payload: bytes, patch: Patch | None) -> Emu:
    """The parameter object as boot leaves it: the constructor through its caller's hook, if patched."""
    e = Emu(payload, construct=False)
    e.call(patch.address("matrix_boot") if patch else PARAM_INIT, PARAMS, count=3_000_000)
    return e


def send_cc(e: Emu, cc: int, value: int, local: int) -> None:
    """Run the stock MIDI input handler on one Control Change, channel 1. With Local Control on, stock stores through
    0x0803F2C4 (as on hardware); with it off, through 0x08023C9C."""
    e.write(MIDI_STATE, b"\x00")  # not 0xFF: the handler bails on 0xFF
    e.write(SETTINGS + 0x3C, b"\x7f")  # input channel: all
    e.write(SETTINGS + 0x42, bytes([local]))
    for side_effect in (0x0804_8524, 0x0804_95C0, 0x0805_5ED8, SEND_DIN, SEND_USB):  # MIDI thru, UI, MIDI out
        e.stub(side_effect)
    msg = 0x2001_0000
    e.write(msg, bytes([0xB0, cc, value, 0]))
    e.call(CC_IN, msg, count=2_000_000)


def capture_sends(e: Emu, busy: bool) -> list[bytes]:
    """Enable CC output and record every MIDI message sent: queued (busy) or sent at once."""
    e.write(SETTINGS + 0x40, b"\x01\x05\x01")  # send CCs, USB + DIN, Local Control on
    e.write(LISTENER_OBJ + 0x30, b"\x00")
    e.write(LISTENER_OBJ + 0x10, b"\xff\xff\xff")
    sent: list[bytes] = []
    e.stub(SEND_QUEUE, lambda emu: emu.set_regs(r0=1 if busy else 0))
    for send in (SEND_DIN, SEND_USB):
        e.stub(send, lambda emu: sent.append(emu.reg("r1").to_bytes(4, "little")[:3]))
    return sent


def listener_sends(e: Emu, pid: int, value: int, busy: bool) -> list[int]:
    """CC values the parameter-change listener sends (or queues) for one change."""
    sent = capture_sends(e, busy)
    event = 0x2001_0000
    e.write(event, struct.pack("<HHh", pid, 0, value))
    e.call(CC_OUT_LISTENER, LISTENER_OBJ, event)
    if busy:
        if e.read(LISTENER_OBJ + 0x30, 1) == b"\x00":
            return []
        assert e.read16(LISTENER_OBJ + 0x10) == pid
        return [e.read(LISTENER_OBJ + 0x12, 1)[0]]
    assert all(m[0] == 0xB0 for m in sent)
    assert len(sent) in (0, 2)  # one message each on USB and DIN
    return sorted({m[2] for m in sent})


# ------------------------------------------------------------------ patched file


def test_only_patch_bytes_change(stock_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    changed = {i for i in range(len(stock_payload)) if stock_payload[i] != combined_payload[i]}
    assert changed <= patch.touched()
    for part in patch.parts:
        start = part.region[0] - MAIN_BASE
        assert combined_payload[start : start + len(part.code)] == part.code


def test_hook_sites_held_the_expected_stock_instructions(stock_payload: bytes, patch: Patch) -> None:
    def at(address: int, n: int = 4) -> bytes:
        return stock_payload[address - MAIN_BASE : address - MAIN_BASE + n]

    assert thumb.branch_target(PARAM_INIT_CALL, at(PARAM_INIT_CALL)) == PARAM_INIT
    for site, stock in HOOKS.items():
        assert at(site) == bytes.fromhex(stock), hex(site)
    assert at(0x0804_79DA, 2) == bytes.fromhex("1f2b")  # cmp r3, #0x1f: runs after matrix_cc_in returns
    assert {h.site for h in patch.hooks if patch.part_of(h.symbol).region == REGION} == {PARAM_INIT_CALL, *HOOKS}
    assert struct.unpack("<I", at(SYNTH_SLOT))[0] == SYNTH_HANDLER
    assert at(STUB & ~1, 2) == bytes.fromhex("7047")  # bx lr


def test_region_is_reached_only_through_the_patch(stock_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    assert {src for src, _ in references(stock_payload, MAIN_BASE, *REGION)} == {SYNTH_SLOT}
    matrix_hooks = {h.site for h in patch.hooks if patch.part_of(h.symbol).region == REGION}
    assert {src for src, _ in references(combined_payload, MAIN_BASE, *REGION)} == matrix_hooks


def test_panel_senders_never_see_a_matrix_cell(stock_payload: bytes) -> None:
    """The eight unhooked CC senders are in the pot and encoder handlers, which only send for this fixed list."""
    raw = stock_payload[PANEL_PARAMS - MAIN_BASE :][: PANEL_PARAM_COUNT * 2]
    ids = struct.unpack(f"<{PANEL_PARAM_COUNT}H", raw)
    assert CUTOFF in ids and FILTER_AMT in ids
    assert not [pid for pid in ids if FIRST_ROW <= pid >> 8 < FIRST_ROW + ROWS]


def test_release_cc_cannot_take_a_matrix_cc(stock_mff: bytes, patch: Patch) -> None:
    with pytest.raises(PatchError, match="mod matrix"):
        apply(stock_mff, patch, release_cc=14)
    code = payload_of(apply(stock_mff, patch, release_cc=81))[0x0802_BB60 - MAIN_BASE :]
    assert code[patch.symbols["release_cc"]] == 81


# ------------------------------------------------------------------ boot


def test_boot_maps_every_cell_both_ways(combined_payload: bytes, patch: Patch) -> None:
    e = booted(combined_payload, patch)
    for cc, pid in CELLS.items():
        assert e.read(CC_MAP + cc * 2, 2) == bytes([pid & 0xFF, pid >> 8])
        assert e.read(e.read32(PARAMS + 0xEC + (pid >> 8) * 4) + (pid & 0xFF), 1) == bytes([cc])
    assert e.read32(GROUP_COUNT) == 21  # Release is still registered
    assert e.read(CC_MAP + 72 * 2, 2) == bytes([0, 20])


def test_boot_changes_nothing_else(release_payload: bytes, combined_payload: bytes, patch: Patch) -> None:
    before, after = booted(release_payload, None), booted(combined_payload, patch)
    before_map, after_map = bytearray(before.read(CC_MAP, 256)), bytearray(after.read(CC_MAP, 256))
    for cc in CELLS:
        after_map[cc * 2 : cc * 2 + 2] = before_map[cc * 2 : cc * 2 + 2]
    assert after_map == before_map
    for group in range(21):
        size = after.read(0x2000_0408 + group, 1)[0]
        before_ccs = before.read(before.read32(PARAMS + 0xEC + group * 4), size)
        after_ccs = bytearray(after.read(after.read32(PARAMS + 0xEC + group * 4), size))
        for src in range(size):
            if FIRST_ROW <= group < FIRST_ROW + ROWS and src < SOURCES and CC_TABLE[group - FIRST_ROW][src]:
                after_ccs[src] = before_ccs[src]
        assert bytes(after_ccs) == before_ccs, f"group {group}"


# ------------------------------------------------------------------ MIDI in


@pytest.mark.parametrize("local", [1, 0])
@pytest.mark.parametrize("value", [0, 1, 32, 63, 64, 65, 96, 127])
@pytest.mark.parametrize("cc", [14, 22, 80, 90, 119, 78])
def test_cc_sets_a_signed_amount(combined_payload: bytes, patch: Patch, cc: int, value: int, local: int) -> None:
    e = booted(combined_payload, patch)
    e.set_param(CELLS[cc], 0x1234)
    send_cc(e, cc, value, local)
    assert signed(e.param(CELLS[cc])) == amount_of(value)


@pytest.mark.parametrize(("value", "amount"), [(0, -0x8000), (64, 0), (127, 0x7FFE)])
def test_cc_endpoints(combined_payload: bytes, patch: Patch, value: int, amount: int) -> None:
    e = booted(combined_payload, patch)
    e.set_param(CELLS[14], 0x1234)
    send_cc(e, 14, value, 1)
    assert signed(e.param(CELLS[14])) == amount  # -100%, 0, +100%


@pytest.mark.parametrize("local", [1, 0])
def test_matches_stocks_own_filter_amt_conversion(
    stock_payload: bytes, combined_payload: bytes, patch: Patch, local: int
) -> None:
    """Stock writes CC 26 into Env -> Cutoff with the same formula the patch uses for every cell."""
    for value in range(128):
        stock = booted(stock_payload, None)
        stock.set_param(ENV_TO_CUTOFF, 0x1234)
        stock.set_param(FILTER_AMT, 0x1234)  # stock skips CC 26 when it equals Filter Amt's current value
        send_cc(stock, 26, value, local)
        ours = booted(combined_payload, patch)
        ours.set_param(CELLS[15], 0x1234)  # Wave <- Env
        send_cc(ours, 15, value, local)
        assert ours.param(CELLS[15]) == stock.param(ENV_TO_CUTOFF), value


@pytest.mark.parametrize(("cc", "pid"), [(23, CUTOFF), (105, 0x0601), (26, FILTER_AMT), (72, RELEASE_ID)])
@pytest.mark.parametrize("local", [1, 0])
def test_other_ccs_behave_as_before(
    release_payload: bytes, combined_payload: bytes, patch: Patch, cc: int, pid: int, local: int
) -> None:
    for value in (0, 1, 64, 127):
        before, after = booted(release_payload, None), booted(combined_payload, patch)
        send_cc(before, cc, value, local)
        send_cc(after, cc, value, local)
        assert after.param(pid) == before.param(pid)
        assert after.param(ENV_TO_CUTOFF) == before.param(ENV_TO_CUTOFF)


# ------------------------------------------------------------------ matrix LEDs


def stock_led_frame(e: Emu, col: int, row: int, on: bool) -> tuple[int, int]:
    """The two words the matrix controller's sweep (0x0803B00A) hands the link sender for one cell: its frame,
    built by stock's 0x08021AB0 with all three levels 0xFF (amount non-zero) or 0."""
    level = 0xFF if on else 0
    sp = e.reg("sp")
    e.set_regs(sp=sp - 0x20)
    e.write(sp - 0x20, struct.pack("<4I", row, level, level, level))
    frame = 0x2001_0100
    e.call(LED_FRAME, frame, 0xFF, 0, col)
    e.set_regs(sp=sp)
    return e.read32(frame), e.read16(frame + 4)


def led_sends(e: Emu, mode: int = 1) -> list[tuple[int, int]]:
    """Set the matrix controller's LED mode and record every frame queued on the I/O link."""
    e.write(MATRIX_UI + 4, bytes([mode]))
    sent: list[tuple[int, int]] = []

    def record(emu: Emu) -> None:
        assert (emu.reg("r0"), emu.reg("r3")) == (IO_LINK, 1)
        sent.append((emu.reg("r1"), emu.reg("r2") & 0xFFFF))

    e.stub(IO_SEND, record)
    return sent


@pytest.mark.parametrize("local", [1, 0])
@pytest.mark.parametrize("cc", [14, 22, 80, 90, 119, 78])
def test_cc_lights_the_led_as_the_sweep_does(combined_payload: bytes, patch: Patch, cc: int, local: int) -> None:
    e = booted(combined_payload, patch)
    pid = CELLS[cc]
    col, row = pid & 0xFF, (pid >> 8) - FIRST_ROW
    on, off = stock_led_frame(e, col, row, True), stock_led_frame(e, col, row, False)
    assert on[0] == 0xF7 | 0x10 << 8 | col << 16 | row << 24 and on[1] == 0xFF7F and off[1] == 0
    e.set_param(pid, 0)
    sent = led_sends(e)
    for value, expect in [(127, on), (96, None), (64, off), (64, None), (0, on), (64, off), (65, on), (63, None)]:
        send_cc(e, cc, value, local)
        assert sent == ([expect] if expect else []), value
        assert signed(e.param(pid)) == amount_of(value)
        sent.clear()


@pytest.mark.parametrize("mode", [0, 2])
def test_no_led_frame_unless_the_matrix_shows_amounts(combined_payload: bytes, patch: Patch, mode: int) -> None:
    e = booted(combined_payload, patch)
    e.set_param(CELLS[14], 0)
    sent = led_sends(e, mode)
    for value in (127, 64, 0):
        send_cc(e, 14, value, 1)
        assert signed(e.param(CELLS[14])) == amount_of(value)
    assert sent == []


@pytest.mark.parametrize("cc", [23, 26, 72])
def test_other_ccs_send_no_led_frame(combined_payload: bytes, patch: Patch, cc: int) -> None:
    """Env -> Cutoff through CC 26 included: stock writes it in its own special case, not through the hook."""
    e = booted(combined_payload, patch)
    sent = led_sends(e)
    for value in (0, 127, 64):
        send_cc(e, cc, value, 1)
    assert sent == []


# ------------------------------------------------------------------ MIDI out


@pytest.mark.parametrize("busy", [True, False])
@pytest.mark.parametrize(
    ("amount", "value"),
    [(-0x8000, 0), (-0x7FFF, 0), (-0x3F02, 32), (0, 64), (0x0306, 65), (0x7FFE, 127), (0x7FFF, 127)],
)
def test_listener_sends_the_cc_value(
    combined_payload: bytes, patch: Patch, amount: int, value: int, busy: bool
) -> None:
    e = booted(combined_payload, patch)
    assert listener_sends(e, CELLS[30], amount, busy) == [value]


@pytest.mark.parametrize("busy", [True, False])
def test_every_value_round_trips(combined_payload: bytes, patch: Patch, busy: bool) -> None:
    for value in range(128):
        e = booted(combined_payload, patch)
        send_cc(e, 110, value, 1)
        amount = signed(e.param(CELLS[110]))
        assert listener_sends(booted(combined_payload, patch), CELLS[110], amount, busy) == [value]


@pytest.mark.parametrize("busy", [True, False])
@pytest.mark.parametrize(
    ("pid", "value"), [(CUTOFF, 0x7FFF), (0x0601, 0x4081), (RELEASE_ID, 0x1234), (FILTER_AMT, 0x2000)]
)
def test_listener_sends_other_parameters_as_before(
    release_payload: bytes, combined_payload: bytes, patch: Patch, pid: int, value: int, busy: bool
) -> None:
    before = listener_sends(booted(release_payload, None), pid, value, busy)
    assert before == [value >> 8]
    assert listener_sends(booted(combined_payload, patch), pid, value, busy) == before


def test_cells_without_a_cc_send_nothing(combined_payload: bytes, patch: Patch) -> None:
    for pid in (ENV_TO_CUTOFF, 0x0A05):  # Filter Amt sends CC 26 instead; Dest has no CC
        assert listener_sends(booted(combined_payload, patch), pid, 0x1000, busy=False) == []


def set_and_send(e: Emu, pid: int, value: int) -> list[bytes]:
    sent = capture_sends(e, busy=False)
    e.write(SETTINGS + 0x47, b"\x01")
    e.call(SET_AND_SEND, PARAMS, pid, value & 0xFFFF_FFFF)
    return sent


@pytest.mark.parametrize(("amount", "value"), [(-0x7FFF, 0), (-0x4000, 32), (0, 64), (0x4000, 96), (0x7FFF, 127)])
def test_set_and_send_sends_the_cc_value(
    stock_payload: bytes, combined_payload: bytes, patch: Patch, amount: int, value: int
) -> None:
    """Stock points this function at matrix ids; with a CC it now sends them, encoded like every other path."""
    assert set_and_send(booted(stock_payload, None), CELLS[14], amount) == []  # stock: no CC, nothing sent
    sent = set_and_send(booted(combined_payload, patch), CELLS[14], amount)
    assert sent and all(m == bytes([0xB0, 14, value]) for m in sent)


def test_set_and_send_sends_other_parameters_as_before(
    release_payload: bytes, combined_payload: bytes, patch: Patch
) -> None:
    for value in (0, 0x4000, 0x7FFF):
        before = set_and_send(booted(release_payload, None), CUTOFF, value)
        assert before and set_and_send(booted(combined_payload, patch), CUTOFF, value) == before


# ------------------------------------------------------------------ Local Control off


@pytest.mark.parametrize("setter", [PARAM_SET, SET_GATED])
def test_local_off_still_writes_matrix_cells(
    stock_payload: bytes, combined_payload: bytes, patch: Patch, setter: int
) -> None:
    """Stock refuses panel writes to CC parameters with Local Control off. Matrix cells had no CC and were written;
    with their CCs they still are."""
    for payload, p in ((stock_payload, None), (combined_payload, patch)):
        e = booted(payload, p)
        e.write(SETTINGS + 0x42, b"\x00")
        args = (PARAMS, CELLS[14], 0x2000, 0) if setter == PARAM_SET else (CELLS[14], 0x2000)
        assert e.call(setter, *args, count=500_000) == 0
        assert e.param(CELLS[14]) == 0x2000


@pytest.mark.parametrize("setter", [PARAM_SET, SET_GATED])
def test_local_off_still_refuses_other_cc_parameters(combined_payload: bytes, patch: Patch, setter: int) -> None:
    e = booted(combined_payload, patch)
    e.write(SETTINGS + 0x42, b"\x00")
    args = (PARAMS, CUTOFF, 0x2000, 0) if setter == PARAM_SET else (CUTOFF, 0x2000)
    assert e.call(setter, *args, count=500_000) == 1
    assert e.param(CUTOFF) != 0x2000
