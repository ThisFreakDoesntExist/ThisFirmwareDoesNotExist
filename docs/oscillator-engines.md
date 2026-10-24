# Oscillator engines

The MicroFreak's digital oscillator has 22 engines in 5.0.0.2084. Each is a C++ class with a vtable, plus a 28-byte descriptor that gives the screen its name and knob labels. Replacing an engine means putting new render code where an old engine's code was, and re-pointing its vtable, descriptor and config answer. That has been done publicly by [FreakSwap](related-projects.md#freakswap), whose layout is summarised below.

**There's no room to add a 23rd engine** without removing something else: the image can grow by only 1,440 bytes and has no free space inside ([why](free-space-and-dead-code.md)). Replacement is the practical route.

## Engine ids and descriptors

The descriptor table starts at **`0x080624F4`**, one 28-byte record per engine id, so engine *n*'s descriptor is at `0x080624F4 + n × 0x1C`. Record 0 is an "Idle" placeholder and record 23 is past the end (other data).

| Offset | Encoding | Role / consumer |
|---|---|---|
| `+0x00` | u8 | Unresolved; stock values 4/5/6. |
| `+0x01` | i8 | Output-gain index offset; `0x080372A4` adds this signed byte and 1 to the existing index, then looks up `0x08063018`. |
| `+0x02` | u8 | Unresolved; zero in stock records. |
| `+0x03..+0x05` | 3 × u8 | Value-conversion selectors for Wave/Timbre/Shape. On a Type change, `0x0800E748` reads these bytes and calls `0x0800E730` to copy them into the RAM parameter descriptors for IDs `0x0001/0x0003/0x0005`, respectively. |
| `+0x06..+0x0B` | 3 × little-endian i16 | Wave/Timbre/Shape raw defaults; copied separately, including to `0x2000031C`. |
| `+0x0C` | char* | Engine name. |
| `+0x10` | char* | Wave label. |
| `+0x14` | char* | Timbre label. |
| `+0x18` | char* | Shape label. |

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

Types **6–12** share the Plaits adapter at `0x08074D14`; Type 13 uses the separate class at `0x08074FE4`. Types 15–17 were added in a later release, Type 18 provides user wavetables, and Types 19–22 arrived in 5.0.

## Engine classes: two different interfaces

All code addresses below are **even entries**; stored Thumb pointers are `address | 1`. Vtable addresses are address points, not preceding headers.

### Outer classes: all Types

The primary interface is **13 pointers / 52 bytes**, not four methods. Shared Types select different modes inside one class.

| Type(s) | Primary vtable | Initialize `+0C` | Config `+10` | Parameters `+18` | Render `+24` |
|---|---|---|---|---|---|
| 1 | `0x08074D5C` | `0x0802FF34` | `0x0802FD88` | `0x08031430` | `0x08032054` |
| 2 | `0x08074DEC` | `0x0803000C` | `0x0802FD88` | `0x08033040` | `0x08030124` |
| 3,18 | `0x08074E34` | `0x08030720` | `0x0802FD88` | `0x08030938` | `0x08030990` |
| 4 | `0x08074F54` | `0x0803084C` | `0x08030544` | `0x08031BD0` | `0x08031040` |
| 5 | `0x08074F9C` | `0x080307D8` | `0x0803051C` | `0x080319AC` | `0x08031010` |
| 6–12 | `0x08074D14` | `0x08030744` | `0x0802FEA4` | `0x0802FE14` | `0x0803099C` |
| 13 | `0x08074FE4` | `0x08030764` | `0x080304F4` | `0x08031788` | `0x08030FDC` |
| 14 | `0x08074DA4` | `0x080321D4` | `0x0802FFEC` | `0x080314EC` | `0x08031620` |
| 15 | `0x0807502C` | `0x080304A8` | `0x0802FD88` | `0x080304B0` | `0x08030BA4` |
| 16 | `0x08075074` | `0x0803043C` | `0x0802FD88` | `0x08030444` | `0x080322A4` |
| 17 | `0x080750BC` | `0x080303D0` | `0x0802FD88` | `0x080303D8` | `0x080327B0` |
| 19 | `0x08074EC4` | `0x08030674` | `0x0802FD88` | `0x080308E4` | `0x08030978` |
| 20–22 | `0x08074E7C` | `0x0803067C` | `0x0802FD88` | `0x08031210` | `0x08030984` |
| Inactive-bank placeholder | `0x08074F0C` | `0x0802FD04` | `0x0802FD88` | `0x0802FD74` | `0x080300D8` |

Type 0 is not proof of selecting the placeholder: it can retain the BasicWaves object/configuration. Inactive banks retain the placeholder and receive rate/deactivation calls.

| Slot | Arguments / role |
|---|---|
| `+00` | R0=self, R1=MIDI note byte |
| `+04` | R0=self; pitch/phase preparation |
| `+08` | R0=self; common pitch target `0x0802FDB0`, recognized and inlined by `0x0803352C` |
| `+0C` | R0=self, R1=Type, R2=workspace, R3=`0x4000` |
| `+10` | R0=self, R1=Type; packed configuration returned in R0 |
| `+14` | R0=self; deactivate on object change |
| `+18` | R0=self, R1=group-0 index, R2=raw16 bits; sampled R3 is the Thumb dispatch target, not a fourth control |
| `+1C` | R0=self, R1=gate 0/1 |
| `+20` | Model-specific state-forward/reset/no-op; return contract unresolved |
| `+24` | R0=self, R1=PCM block; sample count byte at block+`0x48`, signed16 samples at +0 |
| `+28` | R0=self; return stubs |
| `+2C` | R0=self; sized deallocation |
| `+30` | R0=self, R1=rate Hz; `0x0802FF0C` for Types 6–12, otherwise `0x0802FDA4` no-op |

Primary +`34/38` contains `-4/0`; primary +`3C` is the secondary address point installed at object +4. Its rate adjustor is `0x0802FF2C` for Types 6–12, otherwise `0x0802FDA8`; it subtracts 4 from R0 and tails to the primary rate method. These are not extra primary slots.

### Plaits children: Types 6–12 only

Each child address point has **four pointers** at `+00/+04/+08/+0C`: initialize, reset, render, additional model-specific reset. A preceding zero is not a method; a trailing zero is not a reliable delimiter (`0x0807862C` contains `0x04030200`).

| Type | Child vtable | Initialize | Reset | Render | Additional reset `+0C` |
|---|---|---|---|---|---|
| 6 | `0x08078604` | `0x0805B4DC` | `0x0805B564` | `0x0805B574` | `0x0805B568` |
| 7 | `0x0807861C` | `0x0805C950` | `0x0805C990` | `0x0805C9A0` | `0x0805C994` |
| 8 | `0x08078590` | `0x080591FC` | `0x0805921C` | `0x08059220` | `0x080599B8` |
| 9 | `0x080785A8` | `0x080599C4` | `0x08059A0C` | `0x08059A10` | `0x08058368` |
| 10 | `0x08078578` | `0x0805836C` | `0x08058494` | `0x080589C8` | `0x08058368` |
| 11 | `0x080785D8` | `0x0805B18C` | `0x0805B204` | `0x0805B20C` | `0x08058368` |
| 12 | `0x080785C0` | `0x0805B14C` | `0x0805B01C` | `0x0805B024` | `0x08058368` |

The child `+0C` slot is not an auxiliary-output-only reset:

| Target | Verified effect |
|---|---|
| `0x0805B568` | Zero four phases at state+`10/14/34/38`; other phases/history remain unchanged |
| `0x0805C994` | Set phases at state +`10/2C` to 0.5 |
| `0x080599B8` | Zero words at state+`10/14/18` |
| `0x08058368` | Return without changes |

Its precise calling circumstances remain unverified; it is distinct from outer slot `+20`.

| Boundary | ABI / format |
|---|---|
| Child initialize | R0=child state, R1=allocator; allocator +0 cursor, +4 reset base, +8 remaining bytes, +C reset size |
| Child render | R0=child state, R1=parameters, R2=float main[], R3=float auxiliary[], SP+0=frame count, SP+4=output-flag pointer; some children ignore the latter |
| Parameters | +0 trigger byte, +4 float note, +8 timbre, +C morph, +10 harmonics, +14 accent |
| Controls | Wave→harmonics, Timbre→timbre, Shape→morph; ordinary normalized controls are passed through memory, **not S0–S4** |
| Block conversion | `0x0803099C → 0x0800D480 → 0x0805F458`; float child output becomes signed16 PCM with temporal expansion |
| Tested geometry | 16 child frames → 32 outer samples; Modal paraphony 12 → 36. Read supplied counts; do not hard-code 16/32. |
| Channels | Main/auxiliary are model-dependent signals, not necessarily left/right stereo |
| Deeper DSP ABI | May use S registers: e.g. `0x0805D1BC` consumes S0–S4; the wrapper `0x0805B024` does not |
| Workspace | Outer span is 16 KiB, separate from preallocated child objects; allocator cursor/remaining size are reset before each child initialization at `0x0805F2C4`. Not the entire object's state budget. |

`0x0805F458` dispatches child render through `+08`. Chords renders at `0x080589C8`, not its initializer `0x0805836C`; Modal wraps `0x0805D1BC`, not `0x0805D1A0`. Speech renders at `0x0805B20C`, with subpaths `0x0805E554/0x0805EA80`.

## Configuration and selection

Configuration is separate from the 28-byte display record:

| Returned byte | Meaning |
|---|---|
| Bits 0–7 | Mono engine rate in kHz |
| Bits 8–15 | Paraphonic engine rate in kHz |
| Bits 16–23 | Voice-bank count |
| Bits 24–31 | Global minimum queued-event interval in firmware frames; zero disables throttling |

| Types | Configuration |
|---|---|
| 1–4, 13, 15–22 | `0x00046060` |
| 5 | `0x06046060` |
| 6, 9, 10 | `0x00042030` |
| 7, 8, 11, 14 | `0x00043030` |
| 12 | `0x00032030` |

`0x0802FEA4` handles Types 6–12; its out-of-range fallback is `0x00043030`, not the configuration of all other engines. Type 0 can reuse cached configuration. Type 5's `6` is verified for both note-on and note-off: six 32-sample frames / 192 codec samples between successive owners, globally, not a per-voice feature flag. `0x0802FF0C` stores `55.0/rate_hz` at `0x20000004`.

| Selection / dispatch | Address / rule |
|---|---|
| Type control | Parameter `0x0000`; raw RAM `0x2001D9F0`; decoded as `(signed_raw*23)>>15` |
| Control codecs/defaults | `0x0800E748`; record `0x080624F4 + Type*0x1C` |
| Object construction | `0x080359B0`; preallocated per-bank objects and Type pointer table |
| Runtime selection | `0x0803352C`; per-bank Type→object lookup, initialize/configure on change |
| Voice banks | Root `0x20004848`, first bank root+4, stride `0x59E4`, four storage banks |
| Selected pointer | Bank+`0x50AC`; bank0 absolute `0x200098F8` |
| Outer render dispatch | `0x08034394`, BX R3 through primary `+24` |
| Frame / child dispatch | `0x08036B38` / `0x0805F458` |

Adding an ID requires auditing the fixed 23-way decoding, records, object lookup and UI/preset handling; changing one descriptor or configuration answer is insufficient.

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

