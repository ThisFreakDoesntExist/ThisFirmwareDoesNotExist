# The Release patch

A worked example of a complete patch: [`patches/release.S`](../patches/release.S) and [`patches/release.hooks.json`](../patches/release.hooks.json). This page records every stock address it uses, why it was chosen, and how it was checked.

## Design

The firmware keeps synth settings in a parameter object organised in groups. Its registration code accepts 24 groups and stock uses 20, so **Release is registered as a new group (20, id `0x1400`)** at boot, with stock's own registration function. Its value lives in 2 bytes of padding at the end of a value pool that the firmware already copies into every voice. From then on stock code does most of the work: the preset saver writes it, the MIDI CC table maps CC 72 to it and the MIDI-out code sends it, and the generic knob, name and formatting code handle it.

The patch adds only what stock can't do by itself:

| Hook | Why |
|---|---|
| Register the group at boot | one call after the 20 stock groups |
| Release time | the amp envelope and a second attack/release envelope take their release time from Release instead of Decay |
| Change detection | the voice code updates the envelope only when Decay changed; it now also counts a changed Release |
| Preset load | stock presets have no Release, so Release starts as Decay |
| Shift + knob | the firmware already has a "Shift selects an alternate parameter" rule; Dec/Rel now selects Release, in both the pot and the encoder handler |
| Screen | open the envelope popup for Release (both copies of the popup switch), format its value as a time, and draw the curve with Release's time while it's shown |
| Rename | the screen label "Dec/Rel" is stored text; it's rewritten to "Decay" |

Modulation applied to Dec/Rel scales Release in the same proportion (`R' = R · D'/D`), and Release equal to Decay gives exactly the stock value.

The code is 412 bytes, placed over the factory console's `flag`, `help` and `gpio` handlers (432 bytes), which the patch retires.

**Limit:** the envelope curve on the screen is drawn by the OLED co-processor from a single decay/release time. While the Release popup is open the patch sends Release's time, so the whole curve follows Release. The `release-matrix` build draws separate decay and release segments instead, by also patching the OLED chip's firmware (image 1): see [Separate decay and release segments](#separate-decay-and-release-segments-release-matrix).

## Provenance

Everything in this file was derived from Arturia's stock MicroFreak firmware 5.0.0.2084 only (SHA-256 of the `.mff`: `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`). The tools were Ghidra 12.1.4 headless with the scripts in [`tools/ghidra/`](../tools/ghidra/) ([setup](reverse-engineering-setup.md)), Unicorn runs of stock functions, and raw-byte scans. No third-party firmware mod was opened, diffed or used, and every hook site and design choice below was derived again from stock.

Addresses are flash addresses with the 64-byte image header stripped and the image loaded at `0x0800C000`.

**Ghidra's listing is incomplete.** About 297 KB of the 474 KB image lies inside functions it found. The raw scans below found real callers in code it never disassembled (`0x0802BD6C`, `0x08043ACE`, `0x080618CA`). Any "nothing references X" claim here therefore comes from [`tests/refscan.py`](../tests/refscan.py), which decodes every halfword as every Thumb form that carries a target, and every halfword-aligned word as a pointer. Data decoded as code can only add hits, so an empty result is a proof.

### Flash and length

- The main image payload ends at `0x0807FA60` (trailing checksum byte at `0x0807FA5F`).
- The reset handler `0x0805F848` copies `.data` from flash `0x0807F75C`, `0x2F4` bytes long, to `0x20000000`, then zeroes `.bss` from `0x200002F8` to `0x2001F230`. The stack is `0x2001F230–0x20020000`.
- **Hardware:** an image longer than stock hangs at the boot logo. Two flashes showed this, both accepted by MIDI Control Center: the old appended build (+457 bytes, 8 hooks), and the same 457 bytes appended with **no hooks** (diag B). So the area after `0x0807FA60` can't be used, and the patcher keeps the image at its stock length. Why longer images fail is unknown.

### Code region: retired console commands

The image has no usable padding. Its few zero runs sit inside data tables, and dead-function candidates from the Ghidra listing were all refuted by the raw scan:

| Candidate | Refuted by |
|---|---|
| `0x080387A4` (730 B, a second synth init) | `bl` at `0x0802BD6C` in the console `audio` handler (`audio play`). The firmware issues `"audio play"` itself (`0x08073CB0`, loaded at `0x0802D692`). |
| `0x0804CE18` | `bl` at `0x08043ACE`, `0x08043AF0` |
| `0x08043728` | pointer words at `0x080752D4…0x08075318` (jump table) |
| `0x080617AE` | `bl` at `0x080618CA` (the `strtoul` path) |

The patch therefore makes a region unreachable itself:

- The console has one handler object per top-level command, 0x20 bytes each, starting at `0x08073FD0`. Method 0 is the command entry. Commands are numbered by the name table at `0x08073CD8`: gpio 0, codec 1, cvout 2, help 3, flag 4, **audio 5**, filter 6, ioc 7, **synth 8**, boot 9, sync 10, oled 11, emc 12, mixer 13.
  - Index 5 → `0x0802BD10`, whose sub-commands are play/stop/pause/resume (table `0x08073D94`).
  - Index 8 → `0x0802CA94`, whose argument tables `note/pitch/param/gene/dump` (`0x08073E04`) and `Saw/Sqr/Tri/Sin` (`0x08073E34`) make it the synth test command.
- The firmware issues only `audio`, `conf`, `filter` and `ioc` commands itself. These are all of the image's strings that start with a command name: `audio play`, `filter mode …`, `ioc sel …` and 96 `conf …` lines.
- The `synth` handler occupies `0x0802CA94–0x0802CC04` (368 bytes). The function at `0x0802CC04` is a separate helper, tail-called from `0x0802CDBA` in the `sync` handler, and stays untouched.
- Raw scan of stock: **the only reference into `0x0802CA94–0x0802CC04` is the word at `0x080740D4`** (that handler object's method 0). This is `test_region_is_reached_only_through_the_patch`.
- The patch points `0x080740D4` at `0x0802B8ED`, a `bx lr` (`70 47`) that stock already uses as method 0 for `emc` (`0x08074154`). `synth …` on the factory console becomes a no-op, and the region is reachable only through the patch's hooks. The test checks that too, on the patched image.

#### The Release build's region: `flag`, `help`, `gpio`

The display hooks outgrew the `synth` region (372 > 368 bytes), so the Release build uses three adjacent handlers instead, and `synth` stays stock. The hardware diagnostics `diag-region`/`diag-hook` still use the `synth` region; it booted on hardware.

- `flag` (index 4, slot `0x08074054` → `0x0802BB61`), `help` (index 3, slot `0x08074034` → `0x0802BC01`), `gpio` (index 0, slot `0x08073FD4` → `0x0802BC85`) are contiguous: `0x0802BB60–0x0802BD10`, 432 bytes, ending where the `audio` handler starts. None is a command the firmware issues itself.
- The code before `0x0802BB60` ends in `pop.w {r3,r4,r5,lr}; b.w 0x0802E8D0` and a `nop` at `0x0802BB5E`, so nothing falls through into the region.
- Raw scan of stock: the only references into `0x0802BB60–0x0802BD10` are the three slots, plus `0x0802B7B2`, which is the second halfword of the `push.w` at `0x0802B7B0` (it decodes as a literal load). The patch points the three slots at the `bx lr` stub `0x0802B8ED`.

### Parameter system

- Parameter ids are `0xGGII` (group, index). Getter `FUN_08023C2C(obj, id) = *(u16 *)(obj->values[G] + I*2)`. Setter `FUN_08023C40(obj, id, v, force)` stores when changed, and notifies through `obj->vtable[0]` only when the group's notify bit (`obj+0x274+G*2`) is set.
- The object is the static `0x2001C898`, built by `FUN_0800EB10`, which is called from `FUN_0804352C`.
- The registrar is `FUN_0800E7B4(obj, values, flags, ccs, keys8, names12, n)`. **It accepts up to 24 groups (`if (obj->count < 0x18)`), and stock registers 20.** Every per-group table is sized for 24:
  - `obj+0x2C` values, `+0x8C` flags and `+0xEC` CCs (24 pointers each);
  - `+0x274` notify and `+0x2A4` stepping (24 × u16, zeroed `0x30` bytes each);
  - the globals `0x200003A8` keys, `0x20000408` sizes and `0x20000420` names.
- The registrar also fills the CC map at `obj+0x14C + cc*2` = (index, group), skipping CC 127.
- The last stock registration is the `bl` at `0x08011030` (group 19). The constructor then calls `FUN_0800E730(obj, 0, 0x16)` at **`0x0801103C`** (raw decode; Ghidra hadn't listed these calls).
- Constructed tables, read from Unicorn after running the stock constructor (`groups 20`):
  - Group 6 (EG2): Mode, Attack (CC 105), DecRel `Dec/Rel` (CC 106, meta `0x00`, flags `0x43`), Sustain (CC 29), Legato, Amount (CC 26), Snap.
  - Mapped CCs: 2, **5**, 9, 10, 12, 13, 23, 24, 26, 28, 29, 83, 91, 92, 93, 94, 102, 103, 105, 106. The previous list missed CC 5 (Glide). **CC 72 is unmapped.**
  - Flag byte 1: bit 0 saved in presets, bit 7 handled as a UI control (`FUN_080409B4`), bit 2 "Shift alternate is id+1". Bit 2 is set on 0x0001/3/5 (Wave/Timbre/Shape), 0x0201 (Rise → Fall) and 0x0402. It is clear on Dec/Rel, so stock Shift + Dec/Rel just drives Dec/Rel.
- Group names are a fixed flash table at `0x08062478`: `VCO VCF EG1 Kbd Arp LFO EG2 Gen Sys Mat Co1…Co7 SyA Seq Voc`, 4 bytes each. Entry 20 is `"?"` (`0x080624C8`, also the formatter's "no enum names" marker at `FUN_08011258`). A group-20 parameter is therefore saved under group name `"?"`.

#### Value storage: `obj+0x11DA`

- Value pool A at `obj+0x1158` is zeroed as `0x84` bytes, but groups 0, 6, 9 and 10–16 use 130 bytes. Group 16's values end at `0x2001DA72` and group 1's start at `0x2001DA74`, so **`obj+0x11DA` (`0x2001DA72`) is 2 bytes of padding**. Unicorn confirms it stays `0000`.
- No code addresses it. The literals into the object point only at `+0x1158` and `+0x11DC` (pool bounds, in `FUN_08036B38`).
- `FUN_08036B38` copies pool A word by word into each voice (current copy at `voice+0x4038`, previous at `voice+0x40BC`; word `obj+0x11D8` → `voice+0x40B8`). Release therefore rides along in the voice snapshot for free.
- In the envelope dispatcher's frame (`FUN_0803352C`, `r4`) that snapshot sits at `r4+0x4034`. Dec/Rel is at `r4+0x404C`: the Dec/Rel case at `0x08033CB0` reads group 6 index 2's meta byte, then this value. Sustain is at `0x404E` and feeds `bl 0x0800DC74`. Release is at `r4+0x40B6`, previous `+0x84`. No instruction uses `0x40B6`/`0x413A`; `0x40B4`/`0x4138` belong to pool offset `0x80`, a mod-matrix value.

#### Free RAM for the new group's flag and CC bytes

`obj+0x140…0x14B` holds the CC-table pointers for groups 21–23. They're zero after construction (Unicorn), and nothing reads them while fewer than 22 groups are registered. The patch keeps Release's meta, flags and CC there.

#### Keys and names

- Key `"Rel"` is the tail of the stock key `"DecRel"`, at `0x08062987`. Stock keys are already unaligned (for example `0x2001CFF1`), so reading 8 bytes from an odd address is normal here.
- The display name `"Release"` is in the patch code.

#### Who sees a new group

Every function that reads `obj->count` (raw search for `#0x24c]`) was checked:

| Function | Use | Group 20 |
|---|---|---|
| `FUN_080111FC` | group name → index | finds `"?"`; unknown names return `count` |
| `FUN_08054A68` | preset saver | writes `!?` then `CRel c 00 lo hi` (seen under emulation) |
| `FUN_08054E08` | preset parser | an index `>= count` is skipped, so stock firmware skips group `"?"` |
| `FUN_080543E0`, `FUN_0802C928` | broadcast every parameter to listeners | see below |
| `FUN_0803DF60` | per-group notify bits | group 20 has none |

The listeners are filled inline in `FUN_0802479C` (`obj+0x10…+0x24`). Their objects and vtables come from the static constructors in `FUN_0802452C`:

| Object | Handler | Unknown id `0x1400` |
|---|---|---|
| `0x20000A10` | `0x0804ED94` → `FUN_080558C0` | records "last touched id" for the OLED popup; `FUN_080519EC` ignores ids it doesn't know |
| `0x20003714` | `0x0803B82C` | acts on `0x408` only |
| `0x20003558` | `0x0803AB1C` | acts on 7, `0x301`, `0x306`, `0x307` only |
| `0x20000C0C` | `0x080239CC` | **MIDI CC out**: the group's CC array via `obj+0xEC` → sends CC 72 |
| `0x20000C44` | `0x08025394` | compares against a fixed list |

The value formatter `FUN_0804E404` prints unknown ids as plain numbers (`LAB_0804E58C`). The envelope popup `FUN_0804F7AC` is generic over the id. The knob setter `FUN_0802C3F4` uses only the 24-sized per-group tables.

### Envelope

| Function | Writes | Role |
|---|---|---|
| `FUN_0800DC24(env, t)` | `+0x3E`, coefficient `+0x14` | Attack time |
| `FUN_0800DC50(env, t)` | `+0x40`, then `FUN_0800D5AC` | Decay time |
| `FUN_0800DC74(env, lvl)` | `+0x58` | Sustain level |
| `FUN_0800DC8C(env, t)` | `+0x42`, coefficients `+0x28`, `+0x2C` | Release time |

Release-time call sites (every `bl`/`b.w` to `0x0800DC8C`, plus the two `movw r1,#0x602` sites):

| Site | Value | Patch |
|---|---|---|
| `0x08034682` (`FUN_0803352C`) | `D' = D + D·m·k`, the same `r7` as decay at `0x0803467A` | hook → `rel_main` |
| `0x0801447A` in `FUN_08014458`, only caller `0x080346A2` (`sxth r1,r7`) | `2·D'` for the AR envelope at `+0x1A0` (when `+0xF8 != 0`, `+0xFC == 2`) | hook the call at `0x080346A2` → `ar_main` |
| `0x08034A90` after `0x08034A3C movw r1,#0x602` → get | `min(2·get(0x602), 0x7FFF)` | `movw r1,#0x1400` |
| `0x08037C6C` after `0x08037C1C movw r1,#0x602` → get | same | `movw r1,#0x1400` |
| `0x08034938`, `0x08037790`, `0x0803882E`, `0x08038B4A` | constants (100, 500) | none |

The Dec/Rel case runs only when `cur_D != prev_D` (`0x0803418C–0x0803419A`) or the modulation flag `r10` is set (`0x08034188` → `0x08035922` → `0x08033CB0`). Hook `0x08034194` makes a changed Release count as well, and leaves `r2 = D` for `0x08034662`.

`rel_main` and `ar_main` don't assume anything about `r7` after the call. Both compute from the snapshot through `r4`, which the callee must preserve.

### Presets

- Saver `FUN_08054A68` walks groups `0..count-1`. For each it writes `0x20|len, name`, then `0x40|len, key, 0x63, meta, lo, hi` for every parameter with flag bit 0, then `0x40`, and finally a `0x20` terminator, within a 4 KB buffer.
- The parser `FUN_08054E08` has one caller, `0x08055740` in `FUN_08055644`, followed by the broadcast `FUN_080543E0`. It first resets every **stock** group from per-group defaults (hard-coded copies). Group 20 isn't reset, so `load_preset` marks Release `0xFFFF` (a value the parser can't produce: meta 0 values are ≤ `0x7FFF`) and sets Release = Dec/Rel when the preset had no Release field.

### Panel

- `conf pot PC1 1538`: the Dec/Rel pot is control `0x602`. `conf btn PH2 2052`: control `0x804` is key `Shift`.
- `FUN_08043224` stores the Shift state at `this+0x28` when control `0x804` changes (`0x08043234`).
- The panel object's vtable at `0x08074C44` holds button press (`0x0804347C`), button release (`0x08043494`), **pot** (`0x08074C54` → `FUN_08040220`) and **encoder/relative** (`0x08074C70` → `FUN_08042BC8`, which accelerates small steps ×4/×8/×16) handlers. Both pot and encoder handlers read Shift from the same `this+0x28`.
- **Pots go through `FUN_08040220`.** On hardware, the first Release build hooked only the encoder handler, and Shift + Dec/Rel still sent CC 106: a MIDI monitor logged 1,914 messages, all CC 106, none CC 72. Its Shift branch `0x08040378–0x08040394` applies flag bit 2 as `id + 1` and continues at `0x08040252`; nothing branches into `0x0804038A–0x0804038D` (the only nearby branch, `0x08040294`, targets `0x08040396`). The hook at `0x0804038A` replaces this rule with "Dec/Rel → `0x1400`, otherwise stock".
- The encoder handler's Shift branch `0x08042D5A–0x08042D74` (test at `0x08042C08`, continue `0x08042C12`) gets the same hook at `0x08042D6A`. Nothing branches into `0x08042D6C–0x08042D75`.
- The pot handler sets values through `FUN_08023C9C` → `FUN_08023C40`, which stores a CC-mapped parameter only when byte `0x200007A8+0x42` is set; it is set on hardware. `test_dec_rel_pot_end_to_end` drives the real pot handler with and without Shift.

### Screen

- **The popup's id switch exists twice.** `FUN_08052B84`, the UI tick called from the main loop, calls `FUN_080519EC` only on its first run (`this+0xF6 == 0`). After that it uses its own inlined copy of the switch: id in `r6` (`ldrh r6,[r4,#6]` at `0x08052BAC`), `movw r3,#0x503` at `0x08052BAE`, envelope case at `0x08052C1C` (`r5 = this+4`, `r4 = this`) calling `FUN_0804F7AC` at `0x08052C2A`. On hardware, a build that hooked only `FUN_080519EC` never showed Release. Both copies are hooked; nothing branches into the second halfword at `0x08052BB0`.

- A Release change reaches the OLED like any parameter change. The listener `0x20000A10` (`FUN_0804ED94`) stores id `0x1400` as the last touched parameter (`FUN_080558C0`); the same broadcast sends CC 72 out, which was seen on hardware.
- The popup dispatcher `FUN_080519EC` loads that id into `r5` at `0x08051A0E`, then compares it, starting with `movw r3,#0x503` at `0x08051A10`. Ids `0x600–0x603` reach the envelope case at `0x08051AAC` (`r6 = this+4`, `r4 = this`): it sets the timeout (`FUN_08055874(this+4, 0x14, 5000)`) and calls the envelope popup `FUN_0804F7AC`. An unknown id falls through to the exit. Hook `0x08051A10` sends `0x1400` to `0x08051AAC`.
- `FUN_0804F7AC` draws the curve from `0x601`, `0x602`, `0x603` and `0x605`, takes the title from the name table (`"Release"`), and formats the value with `FUN_0804E404(buf, id)`.
- In the formatter, Dec/Rel's branch starts at `0x0804E45A`: `ldr r0,=obj; bl get`, with `r1` still holding the caller's id, then a time format. `0x1400` would otherwise leave at `0x0804E41C` (`bhi`) and print as a raw number. Hook `0x0804E40C` (stock `movw r3,#0x603`) sends `0x1400` into that branch after replaying the three set-up instructions it skips (`sub sp,#8; mov r5,r1; mov r6,r0`).
- Nothing branches into the second halfwords of the hook sites (raw scan).
- **Renaming Dec/Rel.** The screen name of `0x602` is copied by the constructor from the flash string `"Dec/Rel\0"` at `0x0806298C` (literal at `0x0800FF40`, the only reference: raw scan). The patch rewrites those 8 bytes to `"Decay\0\0\0"`. The preset key `"DecRel"` (`0x08062984`) is separate and unchanged, so presets are unaffected.
- **Drawing the curve.** `FUN_0804F7AC` sends the top bytes of `0x601`, `0x602`, `0x603` and `0x605` (via `FUN_0804ED7C`, a raw value read) as one 4-byte message (`FUN_080557E8` → `FUN_08021414` queue), then command `0x12`/`0x2000`. The envelope curve is drawn by the OLED co-processor (its own firmware, image 1), from a single decay/release time. A separate release segment would need a change on that chip.
- The popup reads the curve's decay/release time with `bl 0x0804ED7C` at `0x0804F7C8` (`r0 = 0x602`, popup object in `r7` since `0x0804F7B0`, its id at `[r7,#6]`). `FUN_0804ED7C` reads the same parameter object (`0x2001C898`, literal `0x0804ED90`), so id `0x1400` returns Release. The patch's `curve_time` replaces that call and asks for `0x1400` while the popup shows Release.
- Under emulation the stock formatter prints Release exactly as it prints Dec/Rel at the same value: 0 ms, 504 ms, 1.7 s, 6.0 s, 25.0 s for `0`, `0x800`, `0x2345`, `0x5000` and `0x7FFF`.

#### Separate decay and release segments (`release-matrix`)

The `release` build keeps `curve_time` above. `release-matrix` replaces it with four same-length edits and no new code, two in each image ([`patches/release-matrix.hooks.json`](../patches/release-matrix.hooks.json): `drop_hooks` and `edits`). Found and verified in the MicroFreak emulator. **Not yet run on hardware.**

The OLED chip draws the curve in `FUN_080082D4(a, d, s, f)` (OLED image addresses, payload base `0x08000000`): attack width `a/4`, then `r6 = d/4` (`0x080082E8`) is used for both the decay width (`0x08008334`, `adds r4, r4, r6`) and the release width (`0x0800836E`, `adds r1, r4, r6`). Sustain height comes from `s`. `f`, the 4th byte (`0x605`, Filter Amt), is never read: it only lands on the stack through the function's `push {r1, r2, r3, ...}`, at `[sp, #8]`.

| Image | Address | Stock | Patched | Effect |
|---|---|---|---|---|
| main | `0x0804F7C8` | `bl 0x0804ED7C` | unchanged (no `curve_time` hook) | slot 2 is always Decay |
| main | `0x0804F7E0` | `movw r0, #0x605` | `movw r0, #0x1400` | slot 4 is always Release, in the same scale as Decay |
| OLED | `0x08008342` | `uxth r1, r1` (`89 b2`) | `ldr r6, [sp, #8]` (`02 9e`) | `r6` = the pushed 4th byte |
| OLED | `0x0800835E` | `uxth r1, r1` (`89 b2`) | `lsrs r6, r6, #2` (`b6 08`) | `r6` = release width `f/4` |

- Both `uxth r1, r1` are redundant: `r1` holds a small positive coordinate and the next instruction is a `strh r1, [r0, #4]`, which truncates anyway.
- By `0x08008342` the decay is drawn (`r4` holds `a/4 + d/4`) and `r6` has no use left except the release width at `0x0800836E`.
- `[sp, #8]` is safe: the function writes only `[sp, #0..7]` as scratch and never moves `sp`.
- The release end is `x = a/4 + d/4 + f/4 + 0x21`, the same range as stock (where `d/4` is added twice).
- The patched OLED image keeps its length (81,712 bytes) and gets a fresh checksum in header byte 1 and its last byte, as the main image does. `info.json` and the other images are unchanged.
- Emulator: as Release turns, the popup packets go `00 2e 12 0b` → `00 2e 12 61` with Decay held in slot 2. A Decay-0 popup keeps a 25 s release tail; a Release-0 popup keeps the 25 s decay curve. The built file's popups are pixel-identical to the emulator's in-memory patch of fp7.
- Ship both halves or neither. With the main edits alone, the stock OLED ignores slot 4, so the Release popup no longer redraws the curve at all.
- **Hardware unknowns:** whether an update flashes the OLED chip when its image keeps the stock file name, and whether the chip accepts the changed image. The 4.0.1 → 5.0.0 update did change the OLED image (name and checksum both). Re-flashing the official 5.0.0 `.mff` restores the stock OLED image.

### MIDI CC

The CC map is built by the registrar (above). CC-in goes through `FUN_080478A4` → map → setter. CC-out uses the listener `FUN_080239CC`. Release needs no MIDI hook of its own.
