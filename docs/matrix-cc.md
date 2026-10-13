# The mod matrix over MIDI CC

[`patches/matrix_cc.S`](../patches/matrix_cc.S) and [`patches/matrix-cc.hooks.json`](../patches/matrix-cc.hooks.json) put every mod-matrix amount on its own MIDI CC, in both directions. The shipped build is **`release-matrix`**: the [Release patch](release-patch.md) and this, together in one file ([`patches/release-matrix.hooks.json`](../patches/release-matrix.hooks.json)). `matrix-cc` on its own exists too.

**Status: tested on hardware** (build SHA-256 `e7d1f7e8806ecbf30a451dea3de489da432f9616269a4c5077742d53640cf30a`), see [hardware results](#hardware-results). The default `release` build stays the Release patch alone.

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

The alternative, matching how the panel knobs behave under Local Off (send the CC, don't apply it, let the DAW echo it back), would need a sender for that case: the listener above only runs with Local Control on. It isn't implemented.

## Why incoming CCs don't light the matrix

**Observed on hardware:** a matrix CC changes the sound at once, but the matrix LED and screen stay as they were until the matrix cursor passes that cell. **Stock does the same.** CC 26 changes Filter Amt and, through it, Env → Cutoff (`0x0D01`), but the Cutoff / Env LED doesn't change; scrolling over the cell lights it. Turning the physical Filter Amt knob lights it at once. Stock also shows no popup for any incoming CC (checked with CC 23, Cutoff).

**Why:** the panel and MIDI reach a parameter by different paths, and only the panel path tells the display.

| Path | What runs | Display |
|---|---|---|
| Panel knob or matrix screen | the pot/encoder handler or the matrix screen (`FUN_0803AE90`) sets the value, then `0x0803AE30(obj, id)` **broadcasts** a change event to the six listeners at `obj+0x10…+0x24` | the UI listener `0x20000A10` (handler `0x0804ED94`) records the parameter and the UI tick draws its popup and LEDs |
| Incoming CC | the MIDI handler stores through `0x0803F2C4` (Local Control on) or `0x08023C9C` (off), then the plain setter `0x08023C40` | the setter notifies only groups whose notify bit (`obj+0x274 + group*2`) is set. Only group 0 has one, so a matrix group (10–16), Filter Amt's group 6 and Cutoff's group 1 notify nobody |

The sound follows anyway because the voices read the stored values themselves (value pool A is copied into every voice, see the [Release patch](release-patch.md#value-storage-obj0x11da)). The matrix LEDs come back when the matrix controller's tick (`0x0803AFB0`, run from the main loop at `0x08024F42`) redraws around the cursor, which is why scrolling over a cell fixes it.

**Under emulation** (booted firmware, patched image): after an incoming CC 14 the main CPU sends **0 bytes** to the I/O chips. Broadcasting the same change with `0x0803AE30` sends 176 bytes, all from the UI listener `0x20000A10`; the other five listeners (including MIDI CC out) send nothing. Decoded, they're the screen popup: `CycEnv`, `Pitch`, `100`, `Click to browse`, `Matrix Amount`. That's byte for byte what the matrix screen sends when you edit the cell by hand. The matrix LED chip isn't modelled on that link, so whether those frames also carry the LEDs wasn't visible.

**A fix, not implemented:** after storing a matrix CC, notify only the UI listener `0x20000A10` (never the CC-out listener, so nothing echoes back). That should light the LEDs, but it also pops up "Matrix Amount" on every incoming CC, which stock never does for any parameter and which would flicker constantly under DAW automation. An LED-only refresh needs the LED path reverse-engineered first.

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

None is mapped to a stock parameter or is the Release CC, and none is one MIDI gives a fixed meaning (`RESERVED_CCS` in `patcher.py`: bank select, mod wheel, data entry, volume, pan, expression, the 14-bit LSBs, pedals, portamento control, high-resolution velocity (88), effect depths, RPN/NRPN, channel mode). The patcher checks the table on every build, and refuses a `--release-cc` that's in it. **But 14 of them are read by an unmapped-CC handler in stock**: see below.

### CCs stock already listens to

A CC with no parameter isn't necessarily ignored. The MIDI handler passes it to two handler objects (`0x08047AC8`), and one of them acts on some CCs. Mapping a CC to the matrix takes it away from that handler.

**Method.** On the booted firmware (stock image, emulated), each CC was sent once with value 0 and once with 127 from the same snapshot, and all of SRAM was compared between the two runs. The emulator is deterministic, so a CC that's ignored changes only the stack and two MIDI-parser bytes (`0x2001DD17`, `0x2001E0A6`). Controls: mod wheel (1), volume (7) and expression (11) come out ignored; sustain (64) also changes `0x20003937`; the mapped CCs 9 and 23 change hundreds of bytes.

| CCs | Stock, unmapped |
|---|---|
| 3, 14, 15, 20, 21, 22, 25, 27, 30, 31, 85, 86, 87, 89, 90, 104, 107, 108, 109, 110 (matrix) | ignored |
| 16, 17, 18, 19, 71, 73, 74, 33–63 (not used by the patch) | ignored |
| **75–82, 111–118** (matrix uses 75–78, 80, 111–118) | **stored**: one float per CC in a 16-slot table |
| **119** (matrix: Assign 3 ← CyclEnv) | **stored**: sets all 16 slots |
| 70 (not used) | stored: an on/off byte |

**The handler**, `0x0803056C…0x0803065A`, reached from `0x08047AC8` (a memory-write watch caught it writing):

- CC 75–82 → slot 0–7, CC 111–118 → slot 8–15 (CC 83–110 skip it): the value, scaled, goes as a float to `0x2001C7C8 + 0x48 + slot × 8`. For example, CC 75 = 100 writes `0x3EA00140`. The other word of a slot holds a coefficient (0.05 seen), probably smoothing.
- CC 119 writes the same float to all 16 slots.
- CC 70 sets byte `+0x39` of the object: 1 for value 64, 2 for 127, else 0.
- If byte `+0x3A` is set, it also marks the object changed (`+0xC8`, `+0x40`, `+0x3C`).

The object at `0x2001C7C8` is used from 13 places, among them voice-level DSP (`0x08031618`). **What it is wasn't identified.** Sixteen per-CC levels with an "all" CC and a switch suggests the Vocoder's 16 bands, but that's a guess, and it wasn't tested on hardware or in audio. With the patch, CCs 75–78, 80, 111–119 no longer reach it.

**Replacing the 14** with CCs stock ignores is possible: 16, 17, 18, 19, 71, 73 (74 is MPE's per-note timbre CC, best avoided), plus eight from 33–63. Those are MIDI's 14-bit LSB slots, which `RESERVED_CCS` currently excludes and which a controller sends only when set up for 14-bit control.

## Verified

- **Unit emulation** (`tests/test_matrix_cc.py`), running the stock functions with the patch in place: every cell's mapping at boot and nothing else changed; incoming CCs through both store paths (Local Control on and off), matching stock's own Filter Amt conversion for all 128 values; outgoing CCs from the listener (queued and immediate) and from set-and-send; Local Off writes; every other parameter unchanged against the hardware-tested Release build.
- **Whole firmware** (a local, unpublished emulator of the full booted firmware), a booted synth from a snapshot: a matrix amount set the way the matrix screen sets it goes out on USB as `B0 0E 00/20/40/60/7F` for −100/−50/0/+50/+100%; stock sends nothing. With Local Off it is stored and nothing is sent, as in stock. Set-and-send sends the same values (before the fix it sent `80`, `C0`, `00`, `40`, `7F`). The snapshot was booted on stock firmware, so the probe wrote `matrix_boot`'s table entries itself.

## Hardware results

The default `release-matrix` build, flashed on a MicroFreak with 5.0.0.2084, driven and recorded over USB MIDI and an audio interface:

| Check | Result |
|---|---|
| Boot, Decay and Shift + Decay (Release) | as with the Release build |
| CC 14 = 96 into Pitch ← CyclEnv | stored as +51.2% (computed: 51.18%); CC 14 = 32 shows −49.6% (computed: −49.6%) |
| Sound follows an incoming matrix CC | yes, at once: holding C3, CC 14 = 64 gives a steady 131 Hz, CC 14 = 127 and = 0 give heavy pitch modulation |
| Matrix screen and LEDs follow an incoming matrix CC | no: they update when the matrix cursor next passes the cell. **Stock does the same** for its own MIDI write to a matrix cell (CC 26 → Env → Cutoff), and shows no popup for any incoming CC (checked with CC 23) |
| Turning a matrix amount on the panel | CC 14 goes out 64 → 127 → 0 in single steps, nothing else interleaved |
| Loading presets | no CCs sent |
| Local Control off | matrix amounts still change on the panel; no CC is sent (keyboard notes are) |
| Stock knobs | Cutoff (23), Filter Amt (26), Sustain (29), Release (72), Attack (105), Decay (106) send their CCs over their full range |

## Combined builds

A patch spec with `"combine": [...]` is built from other single-region specs: each part keeps its own region, code and symbols. `build_patch.py` refuses overlapping regions, two parts patching overlapping bytes, a part patching inside another part's code region, a symbol or option declared twice, and more than one CC table. The shipped JSON lists the parts under `"parts"`. Single-region patches are unchanged, so `release.json` and the hardware-tested Release file are byte for byte as before. `test_build.py` checks every shipped JSON, combined ones included, against a fresh build of its specs.

## Not yet checked

- Redrawing the matrix LEDs after an incoming CC without the screen popup (stock's broadcast `0x0803AE30` to the UI listener `0x20000A10` redraws, but always as the full "Matrix Amount" popup, which stock never shows for incoming CCs).
- What the 16-slot CC table at `0x2001C7C8 + 0x48` is (CC 75–82, 111–118, 119, 70), and whether losing CC 75–78, 80, 111–119 to the matrix breaks it, for example on the Vocoder ([above](#ccs-stock-already-listens-to)). If it matters, remap those 14.
- What settings byte `+0x47` is (it gates set-and-send; the surrounding code loops over four tracks, likely the sequencer's modulation lanes).
- The three `Dest` parameters (index 5) have no CC. Mapping them would let a DAW change where Assign 1–3 point.
- CC resolution is 7 bits (128 steps, about 1.6% each).
