"""The voice-modes build: release-matrix plus Delay, Duo, the mode notices and the tempo-synced cycling envelope,
partly appended after the stock image."""

from __future__ import annotations

import hashlib
import struct

import pytest
from refscan import references

from freakpatch import mff, thumb
from freakpatch.patcher import APPEND_BASE, MAIN_BASE, MAIN_END, OLED_BASE, Part, Patch, PatchError, apply, grown

VOICE_MODES_SHA256 = "55e89bb8fdebeec6f39ea5131f6e36e786ef71ab347d2489afa182cb70ff24b6"
"""v4 (2026-10-20): v3 (`dca1a913…`, flashed and tested on hardware 2026-10-17) plus the spread page's OLED title and
the Cyc-Env Sync notice. Emulator-verified."""
OLED_TITLE = 0x0800_8D40
"""The spread page's title in the OLED chip's image."""
STOCK_END = 0x0807_FA5F
CONSOLE_NOP = 0x0802_B8ED
RETIRED = {  # console handler: (region, its vtable word, scanner noise inside other code)
    "codec": ((0x0802_BE90, 0x0802_C132), 0x0807_4094, {0x0802_BE40}),  # 2nd halfword of ldr.w at 0x0802BE3E
    "cvout": ((0x0802_BD94, 0x0802_BE90), 0x0807_4134, set()),
    "gpio": ((0x0802_C2F4, 0x0802_C3E2), 0x0807_3FF4, {0x0802_C154}),  # 2nd halfword of ldr.w at 0x0802C152
    "flag": ((0x0802_D44C, 0x0802_D530), 0x0807_40B4, set()),
}


@pytest.fixture(scope="module")
def patch() -> Patch:
    return Patch.load("voice-modes")


@pytest.fixture(scope="module")
def out(stock_mff: bytes, patch: Patch) -> bytes:
    return apply(stock_mff, patch)


def _payload(raw: bytes) -> bytes:
    update = mff.Update.from_bytes(raw)
    return mff.main_payload(update.read(update.main_name))


def _word(payload: bytes, address: int) -> int:
    return struct.unpack_from("<I", payload, address - MAIN_BASE)[0]


def test_build_is_the_v4_file(out: bytes) -> None:
    assert hashlib.sha256(out).hexdigest() == VOICE_MODES_SHA256


def test_image_grows_only_by_the_appended_code(stock_mff: bytes, out: bytes) -> None:
    update = mff.Update.from_bytes(out)
    image = update.read(update.main_name)
    payload = _payload(out)
    assert len(_payload(stock_mff)) == STOCK_END - MAIN_BASE
    assert len(image) % 16 == 0 and MAIN_BASE + len(payload) + 1 <= MAIN_END
    assert payload[STOCK_END - MAIN_BASE] == 0  # zero fill to the first 16-byte boundary
    assert payload[-7:] == b"\xff" * 7  # padding after the last appended code


def test_everything_release_matrix_changes_is_unchanged(stock_mff: bytes, out: bytes) -> None:
    """The base features keep their bytes: Release, the matrix CCs and their LED refresh, the curve's OLED edits. The
    OLED image differs from the base only by the spread page's title."""
    base_raw = apply(stock_mff, Patch.load("release-matrix"))
    base, new = mff.Update.from_bytes(base_raw), mff.Update.from_bytes(out)
    stock, base_main, new_main = _payload(stock_mff), _payload(base_raw), _payload(out)
    changed = [i for i in range(len(stock)) if base_main[i] != stock[i]]
    assert changed and all(new_main[i] == base_main[i] for i in changed)
    oled = base.image_name(mff.OLED_IMAGE_PREFIX)
    old, now = mff.main_payload(base.read(oled)), mff.main_payload(new.read(oled))
    assert len(now) == len(old)
    title = OLED_TITLE - OLED_BASE
    assert {i for i in range(len(old)) if old[i] != now[i]} <= set(range(title, title + 14))
    assert old[title - 1 : title + 14] == b" Unison Spread\0"
    assert now[title - 1 : title + 14] == b" Spread/Detune\0"  # the centring space stays


def test_cyc_env_posts_its_notice_through_the_displays(patch: Patch) -> None:
    """Cyc-env's toggle jumps to the displays' first routine, post_notice, at the address it was built against."""
    display = next(p for p in patch.parts if p.region[0] == 0x0807_FE00)
    assert display.code and patch.parts.index(display) == 4
    cvout = next(p for p in patch.parts if p.region[0] == 0x0802_BD94)  # cyc-env's toggle lives here
    assert any(
        thumb.branch_target(cvout.region[0] + i, cvout.code[i : i + 4]) == 0x0807_FE00
        for i in range(0, len(cvout.code) - 3, 2)
    )


def test_chained_sites_reach_stock_through_every_part(stock_mff: bytes, patch: Patch, out: bytes) -> None:
    """Each chain hook's stock instruction branches to its declared target, and each wrapper's next word holds the
    part it wraps: Paraphonic Duo -> Delay -> stock, main loop cyc-env -> Duo -> Delay -> stock."""
    stock, payload = _payload(stock_mff), _payload(out)
    for hook in patch.hooks:
        site = hook.site - MAIN_BASE
        assert thumb.branch_target(hook.site, payload[site : site + 4]) == patch.address(hook.symbol)
    chained = {
        0x0803_CA5C: [0x0804_33F0, 0x0803_F1E2],
        0x0803_9DA4: [0x0803_A824],
        0x0800_DD90: [0x0801_25A4, 0x0801_522C],
        0x0804_ED7C: [0x0804_F5AC, 0x0804_F5DC],
    }
    for target, sites in chained.items():
        for site in sites:
            assert thumb.branch_target(site, stock[site - MAIN_BASE :]) == target
    duo, delay, cyc = (patch.parts[i].region[0] for i in (3, 2, 5))
    assert duo == 0x0802_BE90 and delay == 0x0807_FA60 and cyc == 0x0807_FF98
    assert _word(payload, duo) == patch.address("para_btn") | 1  # btn_next
    assert _word(payload, duo + 4) == patch.address("echo_tick") | 1  # tick_next
    assert _word(payload, duo + 8) == patch.address("notice") | 1  # notice_fn, filled by mode-display
    tick_next = 0x0802_C2F4  # cyc-env's sync_tick section starts with its next word
    assert _word(payload, tick_next) == patch.address("duo_tick") | 1


@pytest.mark.parametrize("name", RETIRED)
def test_retired_console_handlers(stock_mff: bytes, out: bytes, name: str) -> None:
    """Stock reaches each handler only through its vtable word (plus explained scanner noise), which now points at
    the console's shared `bx lr`."""
    (lo, hi), slot, noise = RETIRED[name]
    stock = _payload(stock_mff)
    assert {src for src, _ in references(stock, MAIN_BASE, lo, hi)} == {slot} | noise
    assert _word(stock, slot) == lo | 1
    assert _word(_payload(out), slot) == CONSOLE_NOP


def test_menu_label_renamed_in_place(stock_mff: bytes, out: bytes) -> None:
    at = 0x0807_624C - MAIN_BASE
    assert _payload(stock_mff)[at : at + 14] == b"Unison Spread\0"
    assert _payload(out)[at : at + 14] == b"Spread/Detune\0"


def test_grown_pads_to_16_bytes_and_stays_in_the_region(patch: Patch) -> None:
    stock = bytes(STOCK_END - MAIN_BASE)
    payload = grown(stock, patch)
    assert len(payload) == 475_119 and (0x40 + len(payload) + 1) % 16 == 0
    assert grown(stock, Patch.load("release-matrix")) == stock
    last_byte = Patch("x", "", (Part((0x0807_FFF8, 0x0807_FFFF), bytes(7), {}),), (), (), {})
    assert MAIN_BASE + len(grown(stock, last_byte)) + 1 == MAIN_END
    too_far = Patch("x", "", (Part((0x0807_FFFC, 0x0808_0000), bytes(4), {}),), (), (), {})
    with pytest.raises(PatchError, match="passes"):
        grown(stock, too_far)
    assert APPEND_BASE == STOCK_END + 1
