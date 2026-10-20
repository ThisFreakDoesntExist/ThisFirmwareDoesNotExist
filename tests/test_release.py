"""The Release patch, checked statically and run under emulation against the user's own official firmware."""

from __future__ import annotations

import hashlib
import struct

import pytest

pytest.importorskip("unicorn")

from emu import (
    CC_MAP,
    DECAY_ID,
    GROUP_COUNT,
    GROUP_KEYS,
    GROUP_NAMES,
    GROUP_SIZES,
    PARAM_SET,
    PARAMS,
    RELEASE,
    RELEASE_ID,
    RETURN,
    Emu,
)
from refscan import references

from freakpatch import mff, thumb
from freakpatch.patcher import MAIN_BASE, Patch, PatchError, apply

ENV_RELEASE, AR_RELEASE, PRESET_PARSE, PRESET_SAVE = 0x0800_DC8C, 0x0801_4458, 0x0805_4E08, 0x0805_4A68
ENV = 0x2001_0000
VOICE = 0x2000_8000
SNAP_D, SNAP_R, PREV = 0x404C, 0x40B6, 0x84
REGION = (0x0802_BB60, 0x0802_BD10)
CONSOLE_SLOTS = {0x0807_4054: 0x0802_BB61, 0x0807_4034: 0x0802_BC01, 0x0807_3FD4: 0x0802_BC85}  # sync, oled, boot
STUB = 0x0802_B8ED
SCAN_NOISE = 0x0802_B7B2
"""Second halfword of the stock `push.w` at 0x0802B7B0; it decodes as a literal load into the region."""

STOCK_CALLS = {  # hook site -> what stock called there
    0x0801_103C: 0x0800_E730,
    0x0803_4682: ENV_RELEASE,
    0x0803_46A2: AR_RELEASE,
    0x0805_5740: PRESET_PARSE,
    0x0804_F7C8: 0x0804_ED7C,  # envelope popup: Dec/Rel value for the curve
}


def payload_of(raw: bytes) -> bytes:
    update = mff.Update.from_bytes(raw)
    return mff.main_payload(update.read(update.main_name))


@pytest.fixture
def emu(patched_payload: bytes) -> Emu:
    return Emu(patched_payload)


# ------------------------------------------------------------------ patched file


def test_image_keeps_stock_length(stock_mff: bytes, patched_mff: bytes) -> None:
    before, after = mff.Update.from_bytes(stock_mff), mff.Update.from_bytes(patched_mff)
    assert len(after.read(after.main_name)) == len(before.read(before.main_name))
    assert len(patched_mff) == len(stock_mff)


def test_only_patch_bytes_change(stock_payload: bytes, patched_payload: bytes, release_patch: Patch) -> None:
    changed = {i for i in range(len(stock_payload)) if stock_payload[i] != patched_payload[i]}
    assert changed <= release_patch.touched()
    start = REGION[0] - MAIN_BASE
    assert patched_payload[start : start + len(release_patch.code)] == release_patch.code


@pytest.mark.parametrize(("site", "target"), STOCK_CALLS.items())
def test_bl_sites_were_stock_calls(stock_payload: bytes, site: int, target: int) -> None:
    assert thumb.branch_target(site, stock_payload[site - MAIN_BASE :]) == target


def test_other_sites_held_the_expected_stock_instructions(stock_payload: bytes) -> None:
    def at(address: int, n: int = 4) -> bytes:
        return stock_payload[address - MAIN_BASE : address - MAIN_BASE + n]

    assert at(0x0803_4194) == bytes.fromhex("a25ee35e")  # ldrsh r2,[r4,r2]; ldrsh r3,[r4,r3]
    assert at(0x0803_4190, 4) == thumb.movw(3, 0x40D0) and at(0x0803_418C) == thumb.movw(2, SNAP_D)
    assert at(0x0804_2D6A) == bytes.fromhex("5c07") + at(0x0804_2D6C, 2)  # lsls r4,r3,#29; bpl.w
    assert at(0x0804_2D70, 4) == bytes.fromhex("0135adb2")  # adds r5,#1; uxth r5,r5
    for site in (0x0803_4A3C, 0x0803_7C1C):
        assert at(site) == thumb.movw(1, DECAY_ID)
    for slot, handler in CONSOLE_SLOTS.items():
        assert struct.unpack("<I", at(slot))[0] == handler
    assert at(STUB & ~1, 2) == bytes.fromhex("7047")  # bx lr
    assert at(0x0806_298C, 8) == b"Dec/Rel\0"


def test_region_is_reached_only_through_the_patch(
    stock_payload: bytes, patched_payload: bytes, release_patch: Patch
) -> None:
    assert stock_payload[SCAN_NOISE - 2 - MAIN_BASE :][:2] == bytes.fromhex("2de9")  # push.w
    stock = {src for src, _ in references(stock_payload, MAIN_BASE, *REGION)} - {SCAN_NOISE}
    assert stock == set(CONSOLE_SLOTS)  # before: only the three console table slots
    patched = {src for src, _ in references(patched_payload, MAIN_BASE, *REGION)} - {SCAN_NOISE}
    assert patched == {h.site for h in release_patch.hooks}  # after: only the hooks


def test_decay_is_renamed(emu: Emu, stock_payload: bytes) -> None:
    def names(e: Emu) -> tuple[bytes, bytes]:
        return e.cstr(e.read32(GROUP_NAMES + 6 * 4) + 2 * 12), e.cstr(e.read32(GROUP_KEYS + 6 * 4) + 2 * 8)

    assert names(emu) == (b"Decay", b"DecRel")  # screen name changes; the preset key does not
    assert names(Emu(stock_payload)) == (b"Dec/Rel", b"DecRel")


HARDWARE_TESTED_SHA256 = "282ec291a73e89800c52872e4446664e350818978824e1e89003bdadda7d4834"
"""The default Release build, byte for byte the file that passed the hardware checklist."""


def test_output_is_the_hardware_tested_file(patched_mff: bytes) -> None:
    assert hashlib.sha256(patched_mff).hexdigest() == HARDWARE_TESTED_SHA256


def test_patched_file_is_refused(patched_mff: bytes, release_patch: Patch) -> None:
    with pytest.raises(PatchError, match="not the official"):
        apply(patched_mff, release_patch)


def test_release_cc_option(stock_mff: bytes, release_patch: Patch) -> None:
    code = payload_of(apply(stock_mff, release_patch, release_cc=75))[REGION[0] - MAIN_BASE :]
    assert code[release_patch.symbols["release_cc"]] == 75
    for taken in (5, 106):  # Glide and Dec/Rel
        with pytest.raises(PatchError):
            apply(stock_mff, release_patch, release_cc=taken)


@pytest.mark.parametrize("name", ["diag-region", "diag-hook"])
def test_diagnostics_build(stock_mff: bytes, stock_payload: bytes, name: str) -> None:
    patch = Patch.load(name)
    new = payload_of(apply(stock_mff, patch))
    changed = {i for i in range(len(stock_payload)) if stock_payload[i] != new[i]}
    assert changed <= patch.touched()
    assert len(new) == len(stock_payload)


def test_diag_hook_behaves_as_stock(stock_mff: bytes, stock_payload: bytes) -> None:
    stock = Emu(stock_payload)
    diag = Emu(payload_of(apply(stock_mff, Patch.load("diag-hook"))))
    assert diag.read(PARAMS, 0x1300) == stock.read(PARAMS, 0x1300)
    assert diag.read(0x2000_03A8, 0xD8) == stock.read(0x2000_03A8, 0xD8)


# ------------------------------------------------------------------ registration


def test_release_is_parameter_group_20(emu: Emu, stock_payload: bytes) -> None:
    assert emu.read32(GROUP_COUNT) == 21
    assert emu.read(GROUP_SIZES + 20, 1) == b"\x01"
    assert emu.cstr(emu.read32(GROUP_KEYS + 20 * 4)) == b"Rel"
    assert emu.cstr(emu.read32(GROUP_NAMES + 20 * 4)) == b"Release"
    assert emu.read32(PARAMS + 0x2C + 20 * 4) == RELEASE
    flags, ccs = emu.read32(PARAMS + 0x8C + 20 * 4), emu.read32(PARAMS + 0xEC + 20 * 4)
    assert emu.read(flags, 2) == bytes([0x00, 0x43])  # same meta and flags as Dec/Rel
    assert emu.read(ccs, 1) == bytes([72])
    assert emu.read(CC_MAP + 72 * 2, 2) == bytes([0, 20])
    # groups 0-19 come out exactly as stock builds them
    stock = Emu(stock_payload)
    assert stock.read32(GROUP_COUNT) == 20
    for table in (0x2C, 0x8C, 0xEC):
        assert emu.read(PARAMS + table, 80) == stock.read(PARAMS + table, 80)
    assert emu.read(GROUP_SIZES, 20) == stock.read(GROUP_SIZES, 20)
    stock_map, our_map = stock.read(CC_MAP, 256), bytearray(emu.read(CC_MAP, 256))
    our_map[144:146] = stock_map[144:146]
    assert bytes(our_map) == stock_map


def test_release_cc_option_reaches_cc_map(stock_mff: bytes, release_patch: Patch) -> None:
    emu = Emu(payload_of(apply(stock_mff, release_patch, release_cc=75)))
    assert emu.read(CC_MAP + 75 * 2, 2) == bytes([0, 20])
    assert emu.read(CC_MAP + 72 * 2, 2)[1] != 20


def test_stock_getter_and_setter_reach_release(emu: Emu) -> None:
    emu.release = 0x1234
    assert emu.param(RELEASE_ID) == 0x1234
    emu.call(PARAM_SET, PARAMS, RELEASE_ID, 0x4321, 1)
    assert emu.release == 0x4321


@pytest.mark.parametrize("site", [0x0803_4A3C, 0x0803_7C1C])
def test_ar_getter_sites_read_release(emu: Emu, site: int) -> None:
    emu.release, emu.set_param(DECAY_ID, 0x1111)
    emu.release = 0x2222
    emu.set_regs(lr=RETURN | 1)
    emu.run(site, site + 10)  # movw r1; ldr r0,=params; bl get
    assert emu.reg("r0") & 0xFFFF == 0x2222


# ------------------------------------------------------------------ envelope


def voice(emu: Emu, d: int, r: int, d_prev: int | None = None, r_prev: int | None = None) -> None:
    emu.write16(VOICE + SNAP_D, d)
    emu.write16(VOICE + SNAP_R, r)
    emu.write16(VOICE + SNAP_D + PREV, d if d_prev is None else d_prev)
    emu.write16(VOICE + SNAP_R + PREV, r if r_prev is None else r_prev)


def release_time(emu: Emu, symbol: str, target: int, release_patch: Patch, d_mod: int) -> int:
    emu.set_regs(r0=ENV, r1=d_mod, r4=VOICE, r5=5, r6=6, r7=7, lr=0x0803_4687)
    emu.run(release_patch.address(symbol), target)
    assert (emu.reg("r0"), emu.reg("lr"), emu.reg("r4"), emu.reg("r5"), emu.reg("r7")) == (
        ENV,
        0x0803_4687,
        VOICE,
        5,
        7,
    )
    return emu.reg("r1")


@pytest.mark.parametrize(("symbol", "target"), [("rel_main", ENV_RELEASE), ("ar_main", AR_RELEASE)])
@pytest.mark.parametrize(
    ("d", "r", "d_mod", "expected"),
    [
        (0x2000, 0x2000, 0x2468, 0x2468),  # R == D: exactly stock
        (0x2000, 0x2000, 0x9000, 0x9000),  # ...even for out-of-range stock values
        (0x2000, 0x6000, 0x2000, 0x6000),  # unmodulated
        (0x2000, 0x6000, 0x3000, 0x7FFF),  # modulation scales Release the same way, clamped
        (0x4000, 0x1000, 0x2000, 0x0800),
        (0x4000, 0x1000, 0x0000, 0x0000),
        (0x0000, 0x3000, 0x0000, 0x3000),  # Decay at 0: Release unmodulated
        (0x2000, 0xFFFF, 0x2468, 0x2468),  # preset load in progress: stock
    ],
)
def test_release_time(
    emu: Emu, release_patch: Patch, symbol: str, target: int, d: int, r: int, d_mod: int, expected: int
) -> None:
    voice(emu, d, r)
    assert release_time(emu, symbol, target, release_patch, d_mod) == expected


@pytest.mark.parametrize(
    ("d", "d_prev", "r", "r_prev", "changed"),
    [
        (0x1000, 0x1000, 0x2000, 0x2000, False),
        (0x1000, 0x0F00, 0x2000, 0x2000, True),
        (0x1000, 0x1000, 0x2000, 0x2100, True),
        (-5, -5, 0x2000, 0x2000, False),
    ],
)
def test_diff_check(emu: Emu, stock_payload: bytes, d: int, d_prev: int, r: int, r_prev: int, changed: bool) -> None:
    def run(e: Emu) -> dict[str, int]:
        voice(e, d & 0xFFFF, r, d_prev & 0xFFFF, r_prev)
        e.set_regs(r0=0xA0, r1=0xA1, r2=SNAP_D, r3=SNAP_D + PREV, r4=VOICE, r5=0xA5, r12=0xAC, lr=0xA0A1)
        e.run(0x0803_4194, 0x0803_4198)
        return e.regs()

    after = run(emu)
    assert after["r2"] == d & 0xFFFFFFFF
    assert (after["r3"] != after["r2"]) == changed
    stock = run(Emu(stock_payload, construct=False))
    keep = {k for k in after if k not in ("r3",)}
    assert {k: after[k] for k in keep} == {k: stock[k] for k in keep}
    if r == r_prev:
        assert after["r3"] == stock["r3"]


@pytest.mark.parametrize(
    ("pid", "flag", "expected"),
    [
        (DECAY_ID, 0x43, RELEASE_ID),  # Shift + Dec/Rel -> Release
        (0x0201, 0x47, 0x0202),  # Shift + Rise -> Fall, as stock
        (0x0001, 0xCF, 0x0002),
        (0x0601, 0x43, 0x0601),  # no alternate: unchanged, as stock
        (0x0603, 0x43, 0x0603),
    ],
)
@pytest.mark.parametrize(("site", "continue_at"), [(0x0804_038A, 0x0804_0252), (0x0804_2D6A, 0x0804_2C12)])
def test_shift_alternate(
    emu: Emu, stock_payload: bytes, site: int, continue_at: int, pid: int, flag: int, expected: int
) -> None:
    def run(e: Emu) -> dict[str, int]:
        e.set_regs(r0=0xA0, r1=0xA1, r2=0xA2, r3=flag, r5=pid, r6=0xA6, r12=0xAC, lr=0xA0A1)
        e.run(site, continue_at)
        return e.regs()

    after = run(emu)
    assert after["r5"] == expected
    stock = run(Emu(stock_payload, construct=False))
    if pid != DECAY_ID:
        assert after["r5"] == stock["r5"]
    keep = {k for k in after if k not in ("r4", "r5")}
    assert {k: after[k] for k in keep} == {k: stock[k] for k in keep}


POT_HANDLER, PANEL, SET_ENABLE = 0x0804_0220, 0x2001_4000, 0x2000_07A8 + 0x42
"""Stock pot handler (absolute knob positions) and a scratch panel object; Shift is held at +0x28."""


@pytest.mark.parametrize("shift", [0, 1])
def test_dec_rel_pot_end_to_end(emu: Emu, shift: int) -> None:
    emu.set_param(DECAY_ID, 0x1000)
    emu.release = 0x1000
    emu.write(PANEL, bytes(0x40))
    emu.write(PANEL + 0x28, bytes([shift]))
    emu.write(SET_ENABLE, b"\x01")  # set at run time on hardware; the setter ignores CC-mapped knobs without it
    emu.call(POT_HANDLER, PANEL, DECAY_ID, 0x6000)
    if shift:
        assert (emu.param(DECAY_ID), emu.release) == (0x1000, 0x6000)
    else:
        assert (emu.param(DECAY_ID), emu.release) == (0x6000, 0x1000)


# ------------------------------------------------------------------ screen

POPUP_SWITCHES = {  # name: (hook site, continue, envelope case, register holding the id)
    "ui tick": (0x0805_2BAE, 0x0805_2BB2, 0x0805_2C1C, "r6"),  # the live path
    "dispatcher": (0x0805_1A10, 0x0805_1A14, 0x0805_1AAC, "r5"),  # the tick's first run
}
FORMAT, FORMAT_SITE, FORMAT_CONTINUE, FORMAT_DEC_REL = 0x0804_E404, 0x0804_E40C, 0x0804_E410, 0x0804_E45A
TEXT = 0x2001_5000


def test_display_sites_held_the_expected_stock_instructions(stock_payload: bytes) -> None:
    for site, _, case, _ in POPUP_SWITCHES.values():
        assert stock_payload[site - MAIN_BASE :][:4] == thumb.movw(3, 0x503)
        assert stock_payload[case - MAIN_BASE + 0xE :][:4] == thumb.bl(case + 0xE, 0x0804_F7AC)  # envelope popup
    assert stock_payload[FORMAT_SITE - MAIN_BASE :][:4] == thumb.movw(3, 0x603)


@pytest.mark.parametrize("switch", POPUP_SWITCHES)
@pytest.mark.parametrize("pid", [RELEASE_ID, 0x0602, 0x0503, 0x0300, 0x1300])
def test_popup_dispatch(emu: Emu, stock_payload: bytes, switch: str, pid: int) -> None:
    site, continue_at, env_case, id_reg = POPUP_SWITCHES[switch]

    def run(e: Emu, until: int) -> dict[str, int]:
        e.set_regs(
            **({"r0": 0xA0, "r1": 0xA1, "r2": 0xA2, "r3": 0xA3, "r4": 0xA4, "r5": 0xA5, "r6": 0xA6} | {id_reg: pid})
        )
        e.set_regs(r12=0xAC, lr=0xA0A1)
        e.run(site, until)
        return e.regs()

    if pid == RELEASE_ID:  # Release opens the envelope popup, with the switch's registers intact
        before = {"r4": 0xA4, "r5": 0xA5, "r6": 0xA6, id_reg: pid, "sp": emu.reg("sp"), "lr": 0xA0A1}
        after = run(emu, env_case)
        assert {k: after[k] for k in before} == before
    else:  # everything else continues exactly as stock
        assert run(emu, continue_at) == run(Emu(stock_payload, construct=False), continue_at)


@pytest.mark.parametrize("pid", [RELEASE_ID, 0x0602, 0x0603, 0x0101])
def test_format_dispatch(emu: Emu, stock_payload: bytes, pid: int) -> None:
    def run(e: Emu, until: int) -> dict[str, int]:
        e.set_regs(r0=TEXT, r1=pid, r2=0xA2, r3=0xA3, r4=pid, r5=0xA5, r6=0xA6, r12=0xAC, lr=0xA0A1)
        e.run(FORMAT_SITE, until)
        return e.regs()

    if pid == RELEASE_ID:  # Release joins Dec/Rel's branch after the setup it skipped
        sp = emu.reg("sp")
        after = run(emu, FORMAT_DEC_REL)
        assert (after["sp"], after["r1"], after["r5"], after["r6"]) == (sp - 8, RELEASE_ID, RELEASE_ID, TEXT)
    else:
        assert run(emu, FORMAT_CONTINUE) == run(Emu(stock_payload, construct=False), FORMAT_CONTINUE)


CURVE_SITE, POPUP = 0x0804_F7C8, 0x2001_5100


@pytest.mark.parametrize(("shown", "expected"), [(RELEASE_ID, 0x6000), (DECAY_ID, 0x2000), (0x0601, 0x2000)])
def test_curve_follows_the_popup(emu: Emu, shown: int, expected: int) -> None:
    emu.set_param(DECAY_ID, 0x2000)
    emu.release = 0x6000
    emu.write16(POPUP + 6, shown)
    emu.set_regs(r0=DECAY_ID, r7=POPUP, r4=0xA4, r5=0xA5, r6=0xA6, lr=0xA0A1)
    emu.run(CURVE_SITE, CURVE_SITE + 4)  # the hooked call returns to the next instruction
    assert emu.reg("r0") & 0xFFFF == expected
    assert (emu.reg("r4"), emu.reg("r5"), emu.reg("r6"), emu.reg("r7")) == (0xA4, 0xA5, 0xA6, POPUP)


def format_text(e: Emu, pid: int) -> bytes:
    e.write(TEXT, bytes(32))
    e.call(FORMAT, TEXT, pid, count=500_000)
    return e.cstr(TEXT)


@pytest.mark.parametrize("value", [0, 0x0800, 0x2345, 0x5000, 0x7FFF])
def test_release_shows_as_a_time(emu: Emu, stock_payload: bytes, value: int) -> None:
    emu.set_param(DECAY_ID, value)
    emu.release = value
    shown = format_text(emu, RELEASE_ID)
    assert shown == format_text(emu, DECAY_ID)  # same text as Dec/Rel at the same value
    stock = Emu(stock_payload)
    stock.set_param(DECAY_ID, value)
    assert format_text(emu, DECAY_ID) == format_text(stock, DECAY_ID)  # Dec/Rel itself unchanged
    assert shown and shown != str(value).encode()  # a formatted time, not the raw number


# ------------------------------------------------------------------ presets

BUFFER, STREAM, HEADER, PRESET = 0x2001_2000, 0x2001_3000, 0x2001_3200, 0x2001_3300


def field(name: bytes, value: int) -> bytes:
    return bytes([0x40 | len(name)]) + name + bytes([0x63, 0x00, value & 0xFF, value >> 8])


def group(name: bytes, *fields: bytes) -> bytes:
    return bytes([0x20 | len(name)]) + name + b"".join(fields) + b"\x40"


def parse(emu: Emu, preset: bytes, entry: int) -> int:
    emu.write(BUFFER, preset)
    emu.write32(STREAM, 0)
    emu.write32(STREAM + 4, len(preset))
    emu.write32(STREAM + 8, BUFFER)
    return emu.call(entry, PARAMS, STREAM, HEADER)


def load(emu: Emu, release_patch: Patch, tagged: bytes) -> int:
    return parse(emu, bytes(32) + tagged + b"\x20", release_patch.address("load_preset"))


def test_preset_without_release_gets_decay(emu: Emu, release_patch: Patch) -> None:
    emu.release = 0x5555
    assert load(emu, release_patch, group(b"EG2", field(b"DecRel", 0x2345))) == 0
    assert (emu.param(DECAY_ID), emu.release) == (0x2345, 0x2345)


def test_preset_with_release_keeps_it(emu: Emu, release_patch: Patch) -> None:
    load(emu, release_patch, group(b"EG2", field(b"DecRel", 0x2000)) + group(b"?", field(b"Rel", 0x6000)))
    assert (emu.param(DECAY_ID), emu.release) == (0x2000, 0x6000)


def test_release_equal_to_previous_value_still_loads(emu: Emu, release_patch: Patch) -> None:
    emu.release = 0x6000
    load(emu, release_patch, group(b"EG2", field(b"DecRel", 0x2000)) + group(b"?", field(b"Rel", 0x6000)))
    assert emu.release == 0x6000


def save(emu: Emu) -> bytes:
    """Run the stock preset saver, with its flash and slot bookkeeping stubbed out."""
    emu.write(BUFFER, b"\xee" * 0x1000)
    emu.write(PRESET, bytes(0x40))
    emu.stub(0x0804_4FDC, lambda e: e.set_regs(r0=BUFFER))
    emu.stub(0x0804_4FE0, lambda e: e.set_regs(r0=0))
    for address in (0x0802_84BC, 0x0804_5238, 0x0804_5444):
        emu.stub(address)
    emu.call(PRESET_SAVE, PRESET, count=2_000_000)
    data = emu.read(BUFFER, 0x1000)
    return data[: data.index(b"\x20\xee") + 1]


def test_stock_saver_writes_release(emu: Emu) -> None:
    emu.set_param(DECAY_ID, 0x0800)
    emu.release = 0x1ABC
    saved = save(emu)
    assert group(b"?", field(b"Rel", 0x1ABC)) + b"\x20" == saved[-len(group(b"?", field(b"Rel", 0))) - 1 :]


def test_saved_preset_round_trips(emu: Emu, release_patch: Patch) -> None:
    emu.set_param(DECAY_ID, 0x0800)
    emu.set_param(0x0603, 0x1234)
    emu.release = 0x1ABC
    saved = save(emu)
    emu.set_param(DECAY_ID, 0)
    emu.set_param(0x0603, 0)
    emu.release = 0
    assert parse(emu, saved, release_patch.address("load_preset")) == 0
    assert (emu.param(DECAY_ID), emu.param(0x0603), emu.release) == (0x0800, 0x1234, 0x1ABC)


def test_stock_firmware_loads_patched_preset(emu: Emu, stock_payload: bytes) -> None:
    emu.set_param(DECAY_ID, 0x0800)
    emu.set_param(0x0603, 0x1234)
    emu.release = 0x1ABC
    saved = save(emu)
    stock = Emu(stock_payload)
    assert parse(stock, saved, PRESET_PARSE) == 0  # 0: reached the terminator
    assert (stock.param(DECAY_ID), stock.param(0x0603)) == (0x0800, 0x1234)
    # a stock group after the unknown one still loads
    tail = group(b"?", field(b"Rel", 0x6000)) + group(b"EG2", field(b"Sustain", 0x0777))
    assert parse(stock, bytes(32) + tail + b"\x20", PRESET_PARSE) == 0
    assert stock.param(0x0603) == 0x0777
