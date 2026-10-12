# The mod matrix over MIDI CC

[`patches/matrix_cc.S`](../patches/matrix_cc.S) and [`patches/matrix-cc.hooks.json`](../patches/matrix-cc.hooks.json) put every mod-matrix amount on its own MIDI CC, in both directions. The shipped build is **`release-matrix`**: the [Release patch](release-patch.md) and this, together in one file ([`patches/release-matrix.hooks.json`](../patches/release-matrix.hooks.json)). `matrix-cc` on its own exists too.

**Status: verified under emulation, not yet flashed.** The default `release` build is still the hardware-tested one.

## What the matrix is in the firmware

The matrix is seven ordinary parameter groups, one per destination row, read from the stock constructor under Unicorn:

| Group | Name | Row | Indices 0–4 | Index 5 |
|---|---|---|---|---|
| 10 (`0x0A`) | Co1 | Pitch | amounts for CyclEnv, Env, LFO, Press, Key/Arp | `Dest` |
| 11 (`0x0B`) | Co2 | Wave | same | `Dest` |
| 12 (`0x0C`) | Co3 | Timbre | same | `Dest` |
| 13 (`0x0D`) | Co4 | Cutoff | same | `Dest` |
| 14–16 | Co5–Co7 | Assign 1–3 | same | `Dest` |

- The 35 amounts all have flag byte `0x43` (saved in presets, a knob parameter, like Cutoff) and CC `127`, which the registrar treats as "no CC". So they're already in presets: only MIDI is missing.
- **Values are signed 16-bit:** 0 is no modulation, `-0x8000…0x7FFE` is −100…+100%.
- `FUN_08011464(?, source, row)` is stock's own cell → id function: `0x0A00 + row × 0x100 + source`. The matrix screen (`FUN_0803AE90`, `FUN_0803B364`, `FUN_0803B478`) sets amounts through the UI setter `0x08023C9C`.
- **Filter Amt is a matrix cell.** The MIDI input handler special-cases `0x605` (Filter Amt, CC 26) at `0x08047A00`: besides `0x605` itself it writes **`0x0D01`, Env → Cutoff**, as `(v15 − 0x4000) × 2`, with a CC value of exactly 64 written as 0 (`0x08047AA6`). That is the only signed conversion stock has, and this patch uses the same one for every cell. Env → Cutoff keeps CC 26 and gets no second CC.

## MIDI in, stock

`FUN_080478A4` handles a Control Change at `0x080479AE`:

```c
cc = data1 & 0x7F;  v = data2 & 0x7F;
v15 = (v << 8) | (v << 1) | (v >> 6);            // 0..127 -> 0..0x7FFF
id  = *(u16 *)(OBJ + 0x14C + cc * 2);            // (index, group); group 0x1F = unmapped
if (group(id) == 0x1F) -> other listeners (0x08047AC8)
if ((s16)get(id) != v15) { convert(id, &v15); store(id, v15); }   // 0x0804762C, then 0x0803F2C4 (Local on) or 0x08023C9C
```

`0x0804762C` converts the value by the parameter's meta byte only when flag bit `0x20` is set. No stock parameter sets it and the matrix amounts don't, so unsigned `v15` would be stored: CC 0 = 0%, CC 64 = +50%, no negative amounts.

## MIDI out, stock

A parameter's CC is sent from ten places. Each first checks that the parameter's CC byte (`OBJ + 0xEC + group * 4`, then `[index]`) isn't `0x7F`, then computes the data byte as `value >> 8` (`asrs v, v, #8; uxtb r1, v`, or `sbfx` at one site), unsigned. A signed matrix amount would go out wrong: −50% as `0xC0`, a status byte. Which of the ten can see a matrix cell:

| Sender | Where | Matrix cells? |
|---|---|---|
| Parameter-change listener `0x080239CC` (object `0x20000C0C`) | `0x08023A02` | **Yes**: panel edits through `0x08023C9C`, preset loads. Gated on Send CCs, MIDI out and Local Control on |
| Set-and-send `0x0802682C` | `0x08026874` | **Yes**: stock already points it at matrix ids (`0x08026B9C` clamps ids `0x0A00…0x1005`). Gated on settings byte `+0x47` |
| Pot handler `0x08040220`, encoder handler `0x08042BC8`, `0x0803F7DC`, `0x080409B4` and its helper `0x080407E8` | `0x0803FA28`, `0x0803FD36`, `0x0804030A`, `0x080404C8`, `0x08040820`, `0x08040C9E`, `0x08042CEC`, `0x08042EF4` | **No**: these drive only the 24 parameters of the fixed panel list at `0x08073788` (looked up through object `0x20000C44`), which holds no matrix cell (`test_panel_senders_never_see_a_matrix_cell`). Any other id falls through to the plain setter (`0x0804027E` in the pot handler) |

Ten sites were found by disassembling the whole image and listing every load of a CC-byte pointer (`[…, #0xec]`) followed by a `0x7F` check.

## Local Control off, stock

With Local Control off (settings byte `+0x42` = 0), the setters `0x08023C40` (for panel writes, source 0) and `0x0802473C` refuse to store a parameter whose CC byte isn't `0x7F`: only MIDI may set it. Stock matrix cells have no CC, so they were always written. Giving them CCs would make the matrix dead locally with Local Off, so the patch keeps them exempt: with Local Off, matrix edits apply on the synth and send nothing, exactly as in stock.

## The patch

| Hook | Site | Was | Does |
|---|---|---|---|
| `matrix_boot` | `0x08043530` | `bl 0x0800EB10`, the constructor's only call (`FUN_0804352C`) | Calls the constructor, then for every cell in `matrix_ccs` writes `OBJ + 0x14C + cc*2 = (index, group)` (in) and the group's CC byte (out) |
| `matrix_cc_in` | `0x080479D6` | `ubfx r3, r9, #8, #8` | Redoes it; if `r9` is a matrix id, `r8 = (r8 − 0x4000) × 2`, or 0 for CC 64. Stock's `cmp r3, #0x1F` runs next, then compares and stores the converted value |
| `matrix_cc_out` | `0x08023A02` | `asrs r5, r5, #8; uxtb r1, r5` (listener, `r3` = id) | For a matrix id `r5 = ((value >> 8) + 128) >> 1`, which equals `(value + 0x8000) >> 9`; then `r1 = uxtb r5` |
| `matrix_send_cc` | `0x08026874` | `asrs r7, r7, #8; uxtb r1, r7` (set-and-send, `r5` = id) | The same |
| `matrix_local` | `0x08023C82` | `ldrb r3, [r3, r7]; cmp r3, #0x7F` (setter, `r4` = group) | A matrix group reads as "no CC" for the Local-Off check |
| `matrix_local2` | `0x08024756` | `ldrb r3, [r3, r5]; cmp r3, #0x7F` (setter, `r6` = group) | The same |

- Only matrix *amounts* reach these hooks with a CC (`Dest` and Env → Cutoff keep "no CC"), so "is this a matrix amount?" is just `id − 0x0A00 < 0x700`.
- The output conversion is the exact inverse of the input conversion: every CC value 0–127 comes back out unchanged (`test_every_value_round_trips`, on both the queued and the immediate-send path).
- Every hook is a `bl` at a point where `lr` holds nothing live: each function saved it on entry, and nothing reads it before writing it again. The input hook clobbers only `r12`; the output hooks use `r1`, which the displaced `uxtb` sets anyway; the Local-Off hooks use `r12`, unused in those functions.
- Release is registered inside the constructor (its hook at `0x0801103C`), so the CC map is complete when `matrix_boot` writes into it.
- **No RAM is needed.** The CC map and the per-group CC arrays already exist and hold "none" for these cells.

### Region

The code (216 bytes) goes over the factory console's `synth` handler, `0x0802CA94–0x0802CC04` (368 bytes), retired by pointing its slot `0x080740D4` at the stock `bx lr` stub `0x0802B8ED`. That region was raw-scan clean and booted on hardware in the `diag-region` and `diag-hook` builds ([free space](free-space-and-dead-code.md#making-space-retiring-console-commands)). `test_region_is_reached_only_through_the_patch` checks that the patched image reaches it only through the six hooks.

### CCs

| Row | CyclEnv | Env | LFO | Press | Key/Arp |
|---|---|---|---|---|---|
| Pitch | 14 | 15 | 20 | 21 | 22 |
| Wave | 25 | 27 | 30 | 31 | 3 |
| Timbre | 85 | 86 | 87 | 80 | 89 |
| Cutoff | 90 | *26 (stock, Filter Amt)* | 104 | 107 | 108 |
| Assign 1 | 109 | 110 | 111 | 112 | 113 |
| Assign 2 | 114 | 115 | 116 | 117 | 118 |
| Assign 3 | 119 | 75 | 76 | 77 | 78 |

None is a stock CC or the Release CC, and none is one MIDI gives a fixed meaning (`RESERVED_CCS` in `patcher.py`: bank select, mod wheel, data entry, volume, pan, expression, the 14-bit LSBs, pedals, portamento control, high-resolution velocity (88), effect depths, RPN/NRPN, channel mode). The patcher checks the table on every build, and refuses a `--release-cc` that's in it.

## Verified

- **Unit emulation** (`tests/test_matrix_cc.py`), running the stock functions with the patch in place: every cell's mapping at boot and nothing else changed; incoming CCs through both store paths (Local Control on and off), matching stock's own Filter Amt conversion for all 128 values; outgoing CCs from the listener (queued and immediate) and from set-and-send; Local Off writes; every other parameter unchanged against the hardware-tested Release build.
- **Whole firmware** (a local, unpublished emulator of the full booted firmware), a booted synth from a snapshot: a matrix amount set the way the matrix screen sets it goes out on USB as `B0 0E 00/20/40/60/7F` for −100/−50/0/+50/+100%; stock sends nothing. With Local Off it is stored and nothing is sent, as in stock. Set-and-send sends the same values (before the fix it sent `80`, `C0`, `00`, `40`, `7F`). The snapshot was booted on stock firmware, so the probe wrote `matrix_boot`'s table entries itself.

## Combined builds

A patch spec with `"combine": [...]` is built from other single-region specs: each part keeps its own region, code and symbols. `build_patch.py` refuses overlapping regions, two parts patching overlapping bytes, a part patching inside another part's code region, a symbol or option declared twice, and more than one CC table. The shipped JSON lists the parts under `"parts"`. Single-region patches are unchanged, so `release.json` and the hardware-tested Release file are byte for byte as before. `test_build.py` checks every shipped JSON, combined ones included, against a fresh build of its specs.

## Not yet checked

- On hardware: the matrix screen and LEDs when a CC changes a cell, and whether loading a preset now sends the matrix CCs (the listener runs on preset loads; Send CCs gates it).
- Whether stock's unmapped-CC listeners (`0x08047AC8`, objects at `0x20000C10`/`0x20000C14`) act on any of the chosen CCs. A mapped CC no longer reaches them.
- What settings byte `+0x47` is (it gates set-and-send; the surrounding code loops over four tracks, likely the sequencer's modulation lanes).
- The three `Dest` parameters (index 5) have no CC. Mapping them would let a DAW change where Assign 1–3 point.
- CC resolution is 7 bits (128 steps, about 1.6% each).
