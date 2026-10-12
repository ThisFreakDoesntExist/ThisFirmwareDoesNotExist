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
- **Filter Amt is a matrix cell.** The MIDI input handler special-cases `0x605` (Filter Amt, CC 26) at `0x08047A00`: besides `0x605` itself it writes **`0x0D01`, Env → Cutoff**, as `(v15 − 0x4000) × 2`, with a CC value of exactly 64 written as 0 (`0x08047AA6`). That is the only signed conversion stock has, and this patch uses the same one for every cell. Env → Cutoff keeps CC 26 and gets no second CC.

## MIDI in, stock

`FUN_080478A4` handles a Control Change at `0x080479AE`:

```c
cc = data1 & 0x7F;  v = data2 & 0x7F;
v15 = (v << 8) | (v << 1) | (v >> 6);            // 0..127 -> 0..0x7FFF
id  = *(u16 *)(OBJ + 0x14C + cc * 2);            // (index, group); group 0x1F = unmapped
if (group(id) == 0x1F) -> other listeners (0x08047AC8)
if ((s16)get(id) != v15) { convert(id, &v15); store(id, v15); }   // 0x0804762C, then 0x0803F2C4 or 0x08023C9C
```

`0x0804762C` converts the value by the parameter's meta byte only when flag bit `0x20` is set. No stock parameter sets it and the matrix amounts don't, so unsigned `v15` would be stored: CC 0 = 0%, CC 64 = +50%, no negative amounts. The emulator confirms this when a CC is mapped by hand.

## MIDI out, stock

The listener `0x080239CC` (object `0x20000C0C`) runs when a parameter changes. It reads the group's CC byte through `OBJ + 0xEC + group * 4`, skips `0x7F`, and queues `value >> 8` (`asrs r5, r5, #8` at `0x08023A02`). For a signed amount that's wrong in the same way.

## The patch

| Hook | Site | Was | Does |
|---|---|---|---|
| `matrix_boot` | `0x08043530` | `bl 0x0800EB10`, the constructor's only call (`FUN_0804352C`) | Calls the constructor, then for every cell in `matrix_ccs` writes `OBJ + 0x14C + cc*2 = (index, group)` (in) and the group's CC byte (out) |
| `matrix_cc_in` | `0x080479D6` | `ubfx r3, r9, #8, #8` | Redoes it; if `r9` is a matrix amount, `r8 = (r8 − 0x4000) × 2`, or 0 for CC 64. Stock's `cmp r3, #0x1F` runs next, then compares and stores the converted value |
| `matrix_cc_out` | `0x08023A02` | `asrs r5, r5, #8; uxtb r1, r5` | For a matrix amount `r5 = (value + 0x8000) >> 9`, otherwise stock's shift; then `r1 = uxtb r5` |

- `(value + 0x8000) >> 9` is the exact inverse of the input conversion: every CC value 0–127 comes back out unchanged (`test_every_value_round_trips`).
- `lr` is free at both MIDI sites: each function pushed it on entry and makes other calls before returning. `matrix_cc_in` clobbers only `r12`, which nothing reads before the next call. `matrix_cc_out` uses `r1`, which the displaced `uxtb` overwrites anyway, and keeps `r2`, which is live.
- Release is registered inside the constructor (its hook at `0x0801103C`), so the CC map is complete when `matrix_boot` writes into it.
- **No RAM is needed.** The CC map and the per-group CC arrays already exist and hold "none" for these cells.

### Region

The code (180 bytes) goes over the factory console's `synth` handler, `0x0802CA94–0x0802CC04` (368 bytes), retired by pointing its slot `0x080740D4` at the stock `bx lr` stub `0x0802B8ED`. That region was raw-scan clean and booted on hardware in the `diag-region` and `diag-hook` builds ([free space](free-space-and-dead-code.md#making-space-retiring-console-commands)). `test_region_is_reached_only_through_the_patch` checks that the patched image reaches it only through the three hooks.

### CCs

| Row | CyclEnv | Env | LFO | Press | Key/Arp |
|---|---|---|---|---|---|
| Pitch | 14 | 15 | 20 | 21 | 22 |
| Wave | 25 | 27 | 30 | 31 | 3 |
| Timbre | 85 | 86 | 87 | 88 | 89 |
| Cutoff | 90 | *26 (stock, Filter Amt)* | 104 | 107 | 108 |
| Assign 1 | 109 | 110 | 111 | 112 | 113 |
| Assign 2 | 114 | 115 | 116 | 117 | 118 |
| Assign 3 | 119 | 75 | 76 | 77 | 78 |

None of these is a stock CC or the Release default (72), and none has a fixed MIDI meaning: bank select, mod wheel, data entry, volume, expression, pedals, RPN/NRPN and channel mode are all avoided. The patcher refuses a `--release-cc` that's in this table.

## Combined builds

A patch spec with `"combine": [...]` is built from other single-region specs: each part keeps its own region, code and symbols, and `build_patch.py` refuses overlapping regions, two parts patching one site, or a symbol exported twice. The shipped JSON lists the parts under `"parts"`. Single-region patches are unchanged, so `release.json` and the hardware-tested Release file are byte for byte as before.

## Not yet checked

- On hardware: the screen and matrix LEDs when a CC changes a cell, and whether loading a preset now sends the matrix CCs too (the **Knob Send CCs** setting gates every outgoing CC).
- Whether stock's unmapped-CC listeners (`0x08047AC8`, objects at `0x20000C10`/`0x20000C14`) act on any of the chosen CCs. A mapped CC no longer reaches them. These objects are built at run time, so this needs a booted firmware (MicrofreakEmulator) or hardware.
- The three `Dest` parameters (index 5) have no CC. Mapping them would let a DAW change where Assign 1–3 point.
- CC resolution is 7 bits (128 steps, about 1.6% each).
