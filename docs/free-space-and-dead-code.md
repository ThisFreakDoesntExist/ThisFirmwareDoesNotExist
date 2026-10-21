# Free space and dead code

Two constraints shape every patch to the main image. Both were learned the hard way.

## Constraint 1: the image grows only in whole words

The stock main payload ends at `0x0807FA5F`, where its checksum byte is flashed. The bootloader erases and accepts up to `0x0807FFFF` (sectors 3–7, 475,136 bytes), so 1,440 bytes after the stock image are usable, as long as the image is padded.

The history, because it explains the rule:

- **Two hangs.** The first version of the Release patch appended its code there. MIDI Control Center accepted the file, and the synth hung at the boot logo. A second test appended the same 457 bytes **with no hooks at all** (diag B), so none of it could ever run, and it hung too. For a while that looked like "any image longer than stock fails", and every patch was made to fit inside the stock length.
- **The cause.** The bootloader receives the image over USB in 64-byte blocks and programs it in whole 32-bit words. At the end it checks a running XOR of what it programmed against what it received. When the last block's length isn't a multiple of 4, the 1–3 bytes past its end come from whatever the USB receive buffer held, the check fails, and the bootloader never marks the image valid. The synth stays in update mode, which looks like a hang at the logo. Both failing images ended on a 41-byte block. (Read from a unit's bootloader and run under emulation; see [flash writes](flash-writes.md#the-bootloader). No bootloader bytes are published.)
- **The fix, on hardware.** The same 457 bytes padded to a whole number of words (diag C) booted (2026-10-15). The stock image is a multiple of 16 bytes too, header and checksum byte included.

So `patcher.apply()` pads an image with appended code until header, payload and checksum byte are a multiple of 16 bytes, and refuses one that passes `0x08080000`. The rules for appended parts:

- Appended code starts at `0x0807FA60` (`APPEND_BASE`, the first 16-byte boundary after stock) or later. The one byte in front of it is zero; any other gap, and the padding, is `0xFF` (erased flash).
- A part whose `region` starts at or above `APPEND_BASE` is appended, and its region may end at `0x0807FFFF` at most: the last byte goes to the checksum.
- `verify()` checks that the image grew by exactly the appended code, fill and padding, and that nothing else changed.

The `voice-modes` build appends three parts (the delay voice, the mode notices and part of cyc-env sync) and was tested on hardware; see [voice modes](voice-modes.md#layout) for how the 1,440 bytes are used. Little of it is left, so the next sections still matter.

## Constraint 2: there is no free space inside it

- **No padding.** The image is packed tight. Its few runs of zeros sit inside data tables.
- **"Dead" functions usually aren't.** A disassembler's listing reports functions with no callers, but that listing is incomplete: Ghidra's analysis covers only about 297 KB of the 474 KB image, and it misses real callers in code it never decoded. Every candidate below was refuted by a scan of the raw bytes:

| Candidate (Ghidra: no callers) | Actually reached from |
|---|---|
| `0x080387A4` (730 B, a second synth/audio init) | a `bl` at `0x0802BD6C` in the console `audio` handler (`audio play`), and the firmware issues `audio play` itself at boot |
| `0x0804CE18` | `bl` at `0x08043ACE` and `0x08043AF0` |
| `0x08043728` | pointer words at `0x080752D4…0x08075318` (a jump table) |
| `0x080617AE` | `bl` at `0x080618CA` (the `strtoul` path) |

Also, 184 functions have no direct callers simply because they're reached through vtables or pointer tables. The oscillator engines' render functions are an example.

A scan that counts every reference form also found almost nothing beyond the console handlers below: one 178-byte function, `FUN_0802EE74`, reached only from the `oled` console handler that Release retires (so it's free in any build with Release), and a few scraps of 1–12 bytes. Without `cbz`/`cbnz` and `tbb`/`tbh` decoding, three live UI handlers and a switch case looked dead, so decode both if you write your own scan.

## Proving code is unreachable: `tests/refscan.py`

`references(payload, base, lo, hi)` lists every way the image could reach `[lo, hi)` from outside it. It decodes **every halfword offset** as every Thumb form that carries a target (`bl`/`b.w`, `b<c>.w`, `b`, `b<c>`, `cbz`/`cbnz`, literal `ldr`/`ldrb`/`ldrh`/`ldrd`/`vldr`, `adr`), and **every halfword-aligned word** as a pointer.

Decoding data as code can only add false hits, never hide a real one. So **an empty result is a proof** that nothing in the image refers into the range. Hits must then be explained one by one; the usual false hit is the second halfword of a `push.w` (`2D E9 xx xx`) or `ldr.w` (`DF F8 xx xx`) that happens to decode as a literal load or `adr`.

Two limits to keep in mind:

- It proves there's no *static* reference. Code reached through an address computed at run time (a base plus an offset) would be missed; none has been seen in this firmware, but check the neighbourhood of a region for jump tables.
- A region must also not be entered by **fall-through**: check that the instruction before it is an unconditional branch, return or literal pool.

## Making space: retiring console commands

The factory test console (see [main image](main-image.md#factory-test-console)) has one handler object per top-level command, `0x20` bytes each from `0x08073FD0`, with the command entry at word `+0x04` (the slot). **The firmware itself issues only `audio`, `conf`, `filter` and `ioc` commands**, at every boot. The others exist for factory test.

To retire a command, point its slot at a stub that does nothing. Stock already has one: `0x0802B8ED`, a `bx lr` that the last handler object (slot `0x08074154`) uses as its entry. After that edit, the raw scan shows the handler's code can be reached only through the patch's own hooks, so the space is free for new code. The command just becomes a no-op on the factory console.

**The slots aren't in name-table order.** The dispatcher (`0x0802CF6C`) maps each name to its handler object separately. The table below follows the dispatcher, traced under emulation. Earlier versions of this page named the slots by name-table position, which put six names on the wrong handlers and listed `filter` as free.

| Command | Slot | Handler span | Bytes | Raw scan of stock | Status |
|---|---|---|---|---|---|
| sync | `0x08074054` | `0x0802BB60–0x0802BC00` | 160 | slot + `push.w` noise at `0x0802B7B2` | **used by Release** |
| oled | `0x08074034` | `0x0802BC00–0x0802BC84` | 132 | slot only | **used by Release** |
| boot | `0x08073FD4` | `0x0802BC84–0x0802BD10` | 140 | slot only | **used by Release** |
| synth | `0x080740D4` | `0x0802CA94–0x0802CC04` | 368 | slot only | **used by matrix-cc**; proven on hardware by the `diag-*` builds |
| codec | `0x08074094` | `0x0802BE90–0x0802C132` | 674 | slot + `ldr.w` noise at `0x0802BE40` (inside `cvout`) | **used by voice-modes** (Duo) |
| cvout | `0x08074134` | `0x0802BD94–0x0802BE90` | 252 | slot only | **used by voice-modes** (cyc-env) |
| gpio | `0x08073FF4` | `0x0802C2F4–0x0802C3E2` | 238 | slot + `ldr.w` noise at `0x0802C154` (inside `filter`) | **used by voice-modes** (cyc-env). The handler's first 238 bytes; the span after it holds shared functions. |
| flag | `0x080740B4` | `0x0802D44C–0x0802D530` | 228 | slot only | **used by voice-modes** (cyc-env); ends where the panel-link handler starts |
| audio | `0x08074074` | `0x0802BD10–0x0802BD94` | 132 | | **issued at boot: keep** |
| filter | `0x080740F4` | `0x0802C140–0x0802C2F4` | 436 | | **issued at boot: keep** |
| ioc | `0x08074114` | `0x0802CD14–0x0802D44C` | | | **issued at boot: keep** |
| — | `0x08074014` | `0x0802B8E8` | 4 | slot only | a stub no name reaches; nothing to gain |
| — | `0x08074154` | `0x0802B8EC` | 2 | | the shared `bx lr` stub itself, which no name reaches: **don't touch** |
| help, emc, mixer | — | — | — | | reach no handler |

`tests/test_voice_modes.py` checks the four handlers voice-modes uses: on stock, each is reached only through its slot and the noise listed.

With Release, matrix-cc and voice-modes, every retirable handler is in use. A new feature needs space from a smaller patch, `FUN_0802EE74`, or a feature you leave out; [voice modes](voice-modes.md#space) lists what a size pass found.

Before using any region:

1. Re-run `references()` over exactly the bytes you'll overwrite, on the stock image, and explain every hit.
2. Re-run it on the patched image: the only references should be your hooks.
3. Check that nothing falls through into the region.
4. Flash a diagnostic build first (region written, no hooks), as the `diag-region` patch does for `synth`.

## RAM

SRAM is just as full. Places found so far:

- **Padding inside the parameter object.** Value pool A at `obj+0x1158` is zeroed as `0x84` bytes, and its last two bytes (`obj+0x11DA`, `0x2001DA72`) aren't used by any group. The Release patch stores its value there, and because the firmware copies the whole pool into every voice, the value reaches the voices for free.
- **Unused per-group table slots.** The parameter object sizes its tables for 24 groups and stock registers 20, so the slots for groups 21–23 (`obj+0x140…0x14B`, CC-table pointers) are zero and never read while fewer than 22 groups exist. Each new group consumes one slot, so plan accordingly.
- **The engine work buffer.** A replacement oscillator engine can use the host engine's 16 KB arena (see [oscillator engines](oscillator-engines.md)).
- **Between the heap and the stack.** `.bss` ends at `0x2001F230`, where the heap starts; after boot it holds one 88-byte block. The stack grows down from `0x20020000` and was never seen below `0x2001FAE0` in emulation. Voice-modes keeps its state in `0x2001F300–0x2001F4DF` ([voice modes](voice-modes.md#ram)). USB interrupts weren't emulated, so leave a wide margin above the deepest stack seen.

Prove a RAM location unused the same way: raw-scan for literals and immediate offsets that could reach it, and watch it under emulation.
