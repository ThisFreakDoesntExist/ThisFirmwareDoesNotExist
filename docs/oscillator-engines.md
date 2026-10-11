# Oscillator engines

The MicroFreak's digital oscillator has 22 engines in 5.0.0.2084. Each is a C++ class with a vtable, plus a 28-byte descriptor that gives the screen its name and knob labels. Replacing an engine means putting new render code where an old engine's code was, and re-pointing its vtable, descriptor and config answer. That has been done publicly by [FreakSwap](related-projects.md#freakswap), whose layout is summarised below.

**There's no room to add a 23rd engine** without removing something else: the image can't grow and has no free space ([why](free-space-and-dead-code.md)). Replacement is the practical route.

## Engine ids and descriptors

The descriptor table starts at **`0x080624F4`**, one 28-byte record per engine id, so engine *n*'s descriptor is at `0x080624F4 + n × 0x1C`. Record 0 is an "Idle" placeholder and record 23 is past the end (other data).

```
+0x00  u32    flags / layout        e.g. ee000a05
+0x04  u32    packed defaults       e.g. 3fbfeeee
+0x08  u32    packed defaults       e.g. 00003fbf
+0x0C  char*  engine name           "V.Analog"
+0x10  char*  knob 1 label (Wave)   "Detune"
+0x14  char*  knob 2 label (Timbre) "Shape"
+0x18  char*  knob 3 label (Shape)  "Wave"
```

The full table, read from the stock image:

| Id | Descriptor | Words +0x00 / +0x04 / +0x08 | Name | Knob labels |
|---|---|---|---|---|
| 0 | `0x080624F4` | `ee000004 0000eeee 00000000` | Idle | – / – / – |
| 1 | `0x08062510` | `ee000a04 0000eeee 00000000` | BasicWaves | Morph / Sym / Sub |
| 2 | `0x0806252C` | `03000c04 0000eeee 3fff3fff` | SuperWave | Wave / Detune / Volume |
| 3 | `0x08062548` | `0f000a04 0000eeee 00000000` | Wavetable | Table / Position / Chorus |
| 4 | `0x08062564` | `ee000b04 0000eeee 1fff0000` | Harmo | Content / Sculpting / Chorus |
| 5 | `0x08062580` | `ee000b04 2666eeee 4ccc0000` | KarplusStr | Bow / Position / Decay |
| 6 | `0x0806259C` | `ee000a05 3fbfeeee 00003fbf` | V.Analog | Detune / Shape / Wave |
| 7 | `0x080625B8` | `ee000a05 3fbfeeee 00003fbf` | Waveshaper | Wave / Amount / Asym |
| 8 | `0x080625D4` | `ee000a05 2726eeee 00003e3d` | Two Op. FM | Ratio / Amount / Feedback |
| 9 | `0x080625F0` | `ee000c06 2120eeee 67e76d6c` | Formant | Interval / Formant / Shape |
| 10 | `0x0806260C` | `0a000a06 7fffeeee 00000000` | Chords | Type / Inv/Trsp / Waveform |
| 11 | `0x08062628` | `ee000a05 7fffeeee 2dad3d3c` | Speech | Type / Timbre / Word |
| 12 | `0x08062644` | `ee000a06 201feeee 64632d2c` | Modal | Inharm / Timbre / Decay |
| 13 | `0x08062660` | `ee000b04 2aaaeeee 3fff7fff` | Noise | Type / Rate / Balance |
| 14 | `0x0806267C` | `ee000705 0000eeee 40004000` | Vocoder | Wave / Shift / Bandwidth |
| 15 | `0x08062698` | `ee000a04 0000eeee 00000000` | Bass | Saturate / Fold / Noise |
| 16 | `0x080626B4` | `ee000a04 0000eeee 00000000` | SawX | SawMod / Shape / Noise |
| 17 | `0x080626D0` | `ee000a04 0000eeee 00000000` | Harm | Spread / Rectify / Noise |
| 18 | `0x080626EC` | `0f000a04 0000eeee 00000000` | WaveUser | Table / Position / Bitdepth |
| 19 | `0x08062708` | `ee000c04 0000eeee 00007fff` | Sample | Start / Length / Loop |
| 20 | `0x08062724` | `ee000c04 6000eeee 00004000` | Scan Grains | Scan / Density / Chaos |
| 21 | `0x08062740` | `ee000c04 0000eeee 00004000` | Cloud Grains | Start / Density / Chaos |
| 22 | `0x0806275C` | `ee000c04 0000eeee 40004000` | Hit Grains | Start / Density / Shape |

The first three words look like a byte layout plus 16-bit default or scaling values (`3fbf`, `7fff`, `4000` are knob-range values; `ee` looks like "unused"). Their exact meaning wasn't decoded. A safe choice for a replacement is to copy the words of a stock engine whose knobs behave like yours, which is what FreakSwap does.

Several engines in the 6–13 block are adapted from Mutable Instruments **Plaits**, which is MIT-licensed ([source](related-projects.md#mutable-instruments-plaits)). The exact list wasn't checked. Engines 15–17 (Bass, SawX, Harm) were added in a later release, 18 with user wavetables, and 19–22 with 5.0.

## Engine classes

Each engine is a C++ class whose vtable is 24 bytes: a zero word, four method pointers, and a trailing zero. The render functions have **no direct callers**; they're reached only through these vtables, which is why a default Ghidra pass misses them (`tools/ghidra/MfSeed.java` finds them).

| Engine | vtable | Render-sized code |
|---|---|---|
| Chords | `0x08078578` | `0x0805836C…` |
| Two Op. FM | `0x08078590` | `0x08059220…` |
| Formant | `0x080785A8` | `FUN_08059A10` (5,506 B) |
| Modal | `0x080785C0` | `0x0805B01C…`, `0x0805D1A0…` |
| Speech | `0x080785D8` | `0x0805F453…`, `0x08079438…` |
| V.Analog | `0x08078604` | `FUN_0805B574` (4,948 B) |
| Waveshaper | `0x0807861C` | `FUN_0805C9A0` (1,940 B) |

- `0x08058368` is a shared default method in the Chords, Formant, Modal and Speech vtables.
- The active engine gets a **16 KB work buffer** through `init(2, buf, 0x4000)`, called through the vtable word at `+0x0C`. That arena is the engine's whole state budget.
- The vtables of the other engines haven't been mapped. A good way to find them: list every 24-byte run `0, p1, p2, p3, p4, 0` where each `p` is an odd pointer into code, then match each against the engine-selection code.

## The per-engine config method

`FUN_0802FEA4` is a virtual method (a data pointer to it sits at `0x08074D24`). Given an engine id it returns a packed 4-byte value, for ids 6–12:

| Ids | Returns |
|---|---|
| 6 V.Analog, 9 Formant, 10 Chords | `0x00042030` |
| 12 Modal | `0x00032030` |
| 7, 8, 11, and anything else | `0x00043030` |

The fields weren't decoded. A replacement engine may need a different answer here.

## How FreakSwap replaces an engine

FreakSwap's 38 published patches all have the same shape. Mapped to flash addresses:

| What | Size | Purpose |
|---|---|---|
| The host engine's render code | 1.5–4.8 KB | New engine code, plus its name and label strings, written over the old engine |
| The host's descriptor | 11–20 B | New flag/default words, and pointers to the new name and labels |
| The host's vtable | 6–11 B | The four method pointers re-pointed into the new code |
| `FUN_0802FEA4` | 4 B | Its first instruction becomes a `b.w` into new code that returns the new engine's config answer (not needed for Chords and Formant, whose stock answer already suits) |
| A few single bytes | 1–3 B | e.g. `0x0804DFB6` for some Chords swaps, `0x0805F66C` for Speech |
| Image checksum, ZIP CRCs | 10 B | as in [the update file format](update-file-format.md) |

Example, Bass Drum replacing V.Analog (3,344 bytes differ from stock):

```
vtable 0x08078600:  0, 0805b4dd, 0805b565, 0805b575, 0805b569, 0
                →   0, 0805c293, 0805c2b1, 0805c2e1, 0805c2ef, 0
descriptor 0x0806259C:
  ee000a05 3fbfeeee 00003fbf  →  ee000c06 2120eeee 67e76d6c   (Formant's words)
  "V.Analog" "Detune" "Shape" "Wave"  →  "Bass Drum" "Attack" "Tone" "Decay"
0x0802FEA4:  push {r4}; subs r1,#6  →  b.w 0x0805C310   (new config answer)
```

Lessons from it:

- **Only 7 of the 22 engines have been used as hosts:** Chords, Formant, Modal, Speech, Two Op. FM, V.Analog and Waveshaper. A large engine fits only into a large host: about 4.8 KB (a string model) or 3.1–3.3 KB (drums) only goes into Formant's 5.5 KB or V.Analog's 4.9 KB.
- **CPU and RAM fit.** The new code is real floating-point DSP, about 590 VFP instructions where V.Analog had about 700 in the same range, and it runs in the host's 16 KB buffer and voice slot.
- **Presets follow the slot.** A preset that used the replaced engine plays the new one with the same knob values.
- **Vocoder** is never offered as a host by FreakSwap (its rules forbid it). It is the one engine that uses the audio input.

## Replacing an engine with this toolchain

ThisFirmwareDoesNotExist's patch format (code region + hooks + edits) covers everything above: the host's render code is the region, and the vtable words, descriptor words and the `FUN_0802FEA4` branch are edits and hooks. A sketch of the work:

1. **Pick a host** whose render code is at least as big as your engine, and that you're happy to lose. Its render body is your code region. Prove the region is reachable only through that engine's vtable with `references()` from `tests/refscan.py` ([how](free-space-and-dead-code.md#proving-code-is-unreachable-testsrefscanpy)). Note that the render body may share helpers with other engines; only overwrite what nothing else calls.
2. **Write the engine.** `tools/build_patch.py` assembles one `.S` file and refuses relocations. For C or C++ DSP code, extend it to compile with `clang --target=thumbv7em-none-eabihf -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -Os -ffreestanding -fno-exceptions -fno-rtti -nostdlib` and link with `ld.lld -Ttext=<region start>` into a flat binary, so absolute addresses inside your code are resolved at build time. No libc: bring your own math (Plaits' `stmlib` has fast approximations).
3. **Match the calling convention.** Find out from the host's methods whether floats are passed in `s` registers (hard-float ABI) or core registers before you write the method signatures. Read the host's `init` and render methods in Ghidra: argument registers, the output buffer layout and the block size. This is the main open question below.
4. **Re-point the vtable** (four word edits), **the descriptor** (word edits for the three layout words and the four string pointers; the strings live in your region), and **hook `FUN_0802FEA4`** if your engine needs a different config answer.
5. **Keep the work inside 16 KB of state** from the `init` buffer. Don't add globals: there's no free RAM.
6. **Test under emulation** (`tests/emu.py`): call your render method on a fake voice and check the output buffer, then compare a stock engine's render for the same setup to confirm you understood the interface.
7. **Flash a diagnostic first,** as for any patch ([writing a patch](writing-a-patch.md#test-on-hardware-in-steps)).

If you port Plaits code, keep Mutable Instruments' MIT copyright notice with your patch source.

## Open questions

1. **Method signatures:** the order and arguments of the four vtable methods (only `init(2, buf, 0x4000)` through `+0x0C` is known), the render block size, the output format, and the float ABI.
2. **Descriptor words:** what each byte of `+0x00`, `+0x04` and `+0x08` controls.
3. **The config value** from `FUN_0802FEA4`: what its fields mean, and why ids outside 6–12 get the default.
4. **Engine selection:** where the engine id is turned into a vtable and descriptor, and whether the number of engines (22) is hard-coded anywhere else, such as the UI or preset parser.
5. **Vtables for the other 15 engines.**
6. **CPU headroom:** how much more an engine may cost than its host. Needs hardware measurement.
