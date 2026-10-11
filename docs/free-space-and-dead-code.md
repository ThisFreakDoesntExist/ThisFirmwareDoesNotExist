# Free space and dead code

Two constraints shape every patch to the main image. Both were learned the hard way.

## Constraint 1: the image can't grow

The main image ends at `0x0807FA60`, and the flash after it looks free (1,440 bytes up to `0x08080000`). **It isn't usable.**

The first version of the Release patch appended its code there. MIDI Control Center accepted the file, and the synth hung at the boot logo. A second test appended the same 457 bytes **with no hooks at all**, so none of it could ever run, and it hung too. Any main image longer than stock fails to boot, whatever it contains. Why is unknown; the bootloader may check the length, or the updater may write a fixed size.

So everything must fit inside the stock length. `patcher.verify()` refuses to write a longer image.

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

## Proving code is unreachable: `tests/refscan.py`

`references(payload, base, lo, hi)` lists every way the image could reach `[lo, hi)` from outside it. It decodes **every halfword offset** as every Thumb form that carries a target (`bl`/`b.w`, `b<c>.w`, `b`, `b<c>`, `cbz`/`cbnz`, literal `ldr`/`ldrb`/`ldrh`/`ldrd`/`vldr`, `adr`), and **every halfword-aligned word** as a pointer.

Decoding data as code can only add false hits, never hide a real one. So **an empty result is a proof** that nothing in the image refers into the range. Hits must then be explained one by one; the usual false hit is the second halfword of a `push.w` (`2D E9 xx xx`) or `ldr.w` that happens to decode as a literal load.

Two limits to keep in mind:

- It proves there's no *static* reference. Code reached through an address computed at run time (a base plus an offset) would be missed; none has been seen in this firmware, but check the neighbourhood of a region for jump tables.
- A region must also not be entered by **fall-through**: check that the instruction before it is an unconditional branch, return or literal pool.

## Making space: retiring console commands

The factory test console (see [main image](main-image.md#factory-test-console)) has one handler object per top-level command, `0x20` bytes each from `0x08073FD0`, with the command entry at word `+0x04`. **The firmware itself issues only `audio`, `conf`, `filter` and `ioc` commands.** The others exist for factory test.

To retire a command, point its entry word at a stub that does nothing. Stock already has one: `0x0802B8ED`, a `bx lr` that the `emc` command uses as its entry. After that edit, the raw scan shows the handler's code can be reached only through the patch's own hooks, so the space is free for new code. The command just becomes a no-op on the factory console.

Every top-level handler, with a raw scan of the span from its entry to the next known function. "Clean" means the only reference into the span is the command's own table slot, once scanner noise is explained.

| Command | Slot | Span | Bytes | Raw scan | Status |
|---|---|---|---|---|---|
| gpio | `0x08073FD4` | `0x0802BC84–0x0802BD10` | 140 | slot only | **used by the Release patch** |
| help | `0x08074034` | `0x0802BC00–0x0802BC84` | 132 | slot only | **used by the Release patch** |
| flag | `0x08074054` | `0x0802BB60–0x0802BC00` | 160 | slot + `push.w` noise at `0x0802B7B2` | **used by the Release patch** |
| synth | `0x080740D4` | `0x0802CA94–0x0802CC04` | 368 | slot only | **free**; proven on hardware by the `diag-*` builds |
| oled | `0x08074134` | `0x0802BD94–0x0802BE90` | 252 | slot only (plus `ldr.w` noise into `filter`) | **free**; raw-scan clean, not yet flashed |
| boot | `0x080740F4` | `0x0802C140–0x0802C2F4` | 436 | slot + `push.w` noise at `0x0802BD96`, `0x0802BE92` | **free**; raw-scan clean, not yet flashed |
| codec | `0x08073FF4` | `0x0802C2F4–0x0802CA94` | 1,952 | many `bl` from all over the image | **not free as a span**: it contains shared functions. The handler itself is smaller; find its real end before using any of it. |
| sync | `0x08074114` | `0x0802CD14–0x0802D44C` | 1,848 | many `bl` | **not free as a span** (shared functions; also tail-calls `0x0802CC04`) |
| cvout | `0x08074014` | `0x0802B8E8` | 4 | slot only | a stub already, nothing to gain |
| emc | `0x08074154` | `0x0802B8EC` | 2 | — | the shared `bx lr` stub itself: **don't touch** |
| audio, filter, ioc | | | | | **issued by the firmware itself: keep** |
| mixer | — | — | — | — | in the name table but has no handler object |

So, beyond the Release patch's 432 bytes (412 used), about **1,056 more bytes** are available in three separate regions: `synth` (368), `boot` (436) and `oled` (252). They aren't contiguous. The current patch format takes one code region per patch; using several means either extending `Patch` to accept a list of regions, or splitting a patch into pieces that branch to each other.

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

Prove a RAM location unused the same way: raw-scan for literals and immediate offsets that could reach it, and watch it under emulation.
