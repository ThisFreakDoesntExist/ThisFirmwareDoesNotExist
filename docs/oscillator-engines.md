# Oscillator engines

The MicroFreak's digital oscillator has 22 selectable engines plus an Idle Type in 5.0.0.2084. Each Type has a 28-byte descriptor for its name, knob labels and configuration; several Types share an engine object and vtable. Replacing an engine means putting new render code where an old engine's code was, and adjusting its vtable, descriptor and config answer as needed. That has been done publicly by [FreakSwap](related-projects.md#freakswap), whose layout is summarised below.

ROM addresses and table entries are checked against the official image; callback and event behaviour is observed in full-system emulation, not a hardware timing guarantee.

**Replacement is the practical route:** the image can grow by only 1,440 bytes and has no free space inside ([why](free-space-and-dead-code.md)). Adding a Type also requires changing the 23-entry selector and associated tables, not just adding code.

## Engine ids and descriptors

The descriptor table starts at **`0x080624F4`**, one 28-byte record per Type id, so Type *n*'s descriptor is at `0x080624F4 + n × 0x1C`. Record 0 is Idle, which uses the BasicWaves object and vtable; record 23 is past the end. Idle is not the separate inactive-bank placeholder. Group-0 Type parameter `0x0000` selects `floor(raw × 23 / 32768)` for a valid nonnegative 15-bit raw value.

| Offset | Field | Meaning |
|---|---|---|
| `+0x00` | u8 | Unresolved: `04`, `05` or `06` in this image; possibly retained metadata. |
| `+0x01` | i8 | Signed offset into the output-gain selection index, not a linear gain or dB value. |
| `+0x02` | u8 | Unresolved; zero in all records. |
| `+0x03..+0x05` | 3 × u8 | Wave, Timbre and Shape parameter codec modes. |
| `+0x06..+0x0B` | 3 × u16 | Little-endian raw defaults for those controls. |
| `+0x0C` | char* | Engine name. |
| `+0x10`, `+0x14`, `+0x18` | 3 × char* | Wave, Timbre and Shape labels. |

The engine directory combines descriptor fields and primary-vtable metadata. `U` is the unresolved descriptor byte `+0x00`, `G` is its signed gain-index offset, and `Wave` is the Wave codec mode; Timbre and Shape use `EE` for every Type. Raw defaults are at descriptor `+0x06..+0x0B`. The config word is hexadecimal, `U` and `G` are decimal, and rates, slots and interval decode the primary `+0x10` result for that Type.

| Id | Engine | Descriptor | Primary vtable | Render `+24` | Config | Mono / para kHz | Slots | Interval | U | G | Wave | Knob labels |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | Idle | `0x080624F4` | `0x08074D5C` | `0x08032054` | `00046060` | 96 / 96 | 4 | 0 | 4 | 0 | `EE` | – / – / – |
| 1 | BasicWaves | `0x08062510` | `0x08074D5C` | `0x08032054` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `EE` | Morph / Sym / Sub |
| 2 | SuperWave | `0x0806252C` | `0x08074DEC` | `0x08030124` | `00046060` | 96 / 96 | 4 | 0 | 4 | 12 | `03` | Wave / Detune / Volume |
| 3 | Wavetable | `0x08062548` | `0x08074E34` | `0x08030990` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `0F` | Table / Position / Chorus |
| 4 | Harmo | `0x08062564` | `0x08074F54` | `0x08031040` | `00046060` | 96 / 96 | 4 | 0 | 4 | 11 | `EE` | Content / Sculpting / Chorus |
| 5 | KarplusStr | `0x08062580` | `0x08074F9C` | `0x08031010` | `06046060` | 96 / 96 | 4 | 6 | 4 | 11 | `EE` | Bow / Position / Decay |
| 6 | V.Analog | `0x0806259C` | `0x08074D14` | `0x0803099C` | `00042030` | 48 / 32 | 4 | 0 | 5 | 10 | `EE` | Detune / Shape / Wave |
| 7 | Waveshaper | `0x080625B8` | `0x08074D14` | `0x0803099C` | `00043030` | 48 / 48 | 4 | 0 | 5 | 10 | `EE` | Wave / Amount / Asym |
| 8 | Two Op. FM | `0x080625D4` | `0x08074D14` | `0x0803099C` | `00043030` | 48 / 48 | 4 | 0 | 5 | 10 | `EE` | Ratio / Amount / Feedback |
| 9 | Formant | `0x080625F0` | `0x08074D14` | `0x0803099C` | `00042030` | 48 / 32 | 4 | 0 | 6 | 12 | `EE` | Interval / Formant / Shape |
| 10 | Chords | `0x0806260C` | `0x08074D14` | `0x0803099C` | `00042030` | 48 / 32 | 4 | 0 | 6 | 10 | `0A` | Type / Inv/Trsp / Waveform |
| 11 | Speech | `0x08062628` | `0x08074D14` | `0x0803099C` | `00043030` | 48 / 48 | 4 | 0 | 5 | 10 | `EE` | Type / Timbre / Word |
| 12 | Modal | `0x08062644` | `0x08074D14` | `0x0803099C` | `00032030` | 48 / 32 | 3 | 0 | 6 | 10 | `EE` | Inharm / Timbre / Decay |
| 13 | Noise | `0x08062660` | `0x08074FE4` | `0x08030FDC` | `00046060` | 96 / 96 | 4 | 0 | 4 | 11 | `EE` | Type / Rate / Balance |
| 14 | Vocoder | `0x0806267C` | `0x08074DA4` | `0x08031620` | `00043030` | 48 / 48 | 4 | 0 | 5 | 7 | `EE` | Wave / Shift / Bandwidth |
| 15 | Bass | `0x08062698` | `0x0807502C` | `0x08030BA4` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `EE` | Saturate / Fold / Noise |
| 16 | SawX | `0x080626B4` | `0x08075074` | `0x080322A4` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `EE` | SawMod / Shape / Noise |
| 17 | Harm | `0x080626D0` | `0x080750BC` | `0x080327B0` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `EE` | Spread / Rectify / Noise |
| 18 | WaveUser | `0x080626EC` | `0x08074E34` | `0x08030990` | `00046060` | 96 / 96 | 4 | 0 | 4 | 10 | `0F` | Table / Position / Bitdepth |
| 19 | Sample | `0x08062708` | `0x08074EC4` | `0x08030978` | `00046060` | 96 / 96 | 4 | 0 | 4 | 12 | `EE` | Start / Length / Loop |
| 20 | Scan Grains | `0x08062724` | `0x08074E7C` | `0x08030984` | `00046060` | 96 / 96 | 4 | 0 | 4 | 12 | `EE` | Scan / Density / Chaos |
| 21 | Cloud Grains | `0x08062740` | `0x08074E7C` | `0x08030984` | `00046060` | 96 / 96 | 4 | 0 | 4 | 12 | `EE` | Start / Density / Chaos |
| 22 | Hit Grains | `0x0806275C` | `0x08074E7C` | `0x08030984` | `00046060` | 96 / 96 | 4 | 0 | 4 | 12 | `EE` | Start / Density / Shape |

Type selection at `0x0800E748` updates the codec bytes for group-0 parameters `0x0001`, `0x0003` and `0x0005`, without replacing their descriptor flags. `0xEE` is a passthrough codec, **not** an unused marker; modes `0x01..0x7F` decode to scaled, saturated indices. Defaults are separate from current preset values; the signed gain offset is used at `0x080372A4` to select a coefficient from `0x08063018`. Copying a stock descriptor's header is useful only when its codec, defaults and gain behaviour suit the replacement.

Byte `+0x00` correlates with runtime metadata: `04` Types advertise 96 kHz mono; `05` and `06` Types advertise 48 kHz mono. All `06` Types advertise 32 kHz paraphonic; `05` Types advertise 48 kHz paraphonic except V.Analog at 32 kHz. No consumer of `+0x00` or `+0x02` was observed in the exercised paths; a legacy field, flags or an enum are possibilities, not established meanings.

Types 6–12 (V.Analog through Modal) use the **Plaits** family, adapted from Mutable Instruments' MIT-licensed code ([source](related-projects.md#mutable-instruments-plaits)). Noise (13) and Vocoder (14) do not use its outer vtable. Harmo and Harm are distinct OLED names; OLED text is sent in four-byte chunks, so `Harm` can be followed by `o`.

## Engine classes

There are **two different virtual interfaces**. Every selected oscillator uses a primary 13-method table; Types 6–12 share one such table and dispatch to seven four-method Plaits child tables. A child callback must not be called with the outer object's ABI. Table addresses point to the first method; code entries are even, while pointers stored in ROM have the Thumb bit set.

The primary table is at object `+0x00`; object `+0x04` holds a secondary address point. Its 13 pointers occupy `+0x00..+0x30`:

| Offset | Method | Call / role |
|---|---|---|
| `+0x00` | Note | `(self, note)`; note is a MIDI note byte. |
| `+0x04` | Pitch update | `(self)`; prepare pitch-dependent state. |
| `+0x08` | Pitch calculation | `(self)`; common target `0x0802FDB0`, sometimes executed inline. |
| `+0x0C` | Initialize | `(self, type, workspace, span)`; bank workspace span is `0x4000`. |
| `+0x10` | Config | `(self, type) -> u32`; the capability word below. |
| `+0x14` | Deactivate | `(self)` before selection, including shared-object Type changes. |
| `+0x18` | Parameter | `(self, id, raw, ...)`; R3 was observed as dispatch scratch. |
| `+0x1C` | Gate | `(self, gate)`; model-specific handling. |
| `+0x20` | Auxiliary | Partial state operation, forwarding or no-op; not a general getter. |
| `+0x24` | Render | `(self, block)`; signed PCM samples at block `+0`, count byte at `+0x48`. |
| `+0x28` | Lifecycle | `(self)`; the stock methods return immediately. |
| `+0x2C` | Deallocate | `(self)`; sized deallocation wrapper. |
| `+0x30` | Rate | `(self, rate_hz)`; Plaits updates a coefficient, other stock methods return. |

The used `+0x18` methods cache raw values at `self + 0x0C + 2*id`. Voice preparation at `0x0803352C` dispatches the primary methods; its `+0x24` render tail-branch is at `0x08034394`. The 16 KB workspace is **not** the entire engine state: outer objects and other per-bank state also exist outside it.

The inactive-bank placeholder is not a Type: its primary vtable is `0x08074F0C` and its render entry is `0x080300D8`.

Each primary table has a secondary header at `+0x34/+0x38` (offset-to-top `-4`, null RTTI), followed by the secondary address point at `+0x3C`. Its known rate method adjusts `self` by `-4`: `0x0802FF2C` for Plaits, `0x0802FDA8` for the other tables. Do not assume further secondary methods.

### From audio IRQ to render

SAI2 output uses circular DMA2 Stream 4; half-transfer and transfer-complete interrupts refill alternating portions of the codec buffer. The stock hardware path is:

| Stage | Address | What happens |
|---|---|---|
| DMA IRQ | `0x0802F008` → `0x0801B31C` | Stream 4 handler calls the HAL DMA interrupt handler. |
| Half / complete callbacks | `0x0801F304` / `0x0801F364` → `0x0802F0E8` / `0x0802F104` | DMA callbacks dispatch through the render-root vtable. |
| Render thunks | `0x08039A54` / `0x08039A5C` → `0x08038DF8` | Select half 0 / 1 and tail to the audio dispatcher. |
| Voice frame | `0x08036B38` | Render active banks, mix mono or paraphonic PCM, and update shared controls. |
| Per-bank preparation | `0x0803352C` | Apply pending note/gate, parameter, envelope and pitch changes; select/initialize the oscillator when needed. |
| Oscillator render | `0x08034394` → primary `+0x24` | Indirect tail-branch to the selected engine; Plaits continues through its child `+0x08`. |
| Output | return to `0x08038DF8` | Format/copy the frame into the selected codec-buffer half. |

The IRQ chain is established from the firmware; full-system emulation schedules the render boundary rather than reproducing the physical DMA interrupt. Other callbacks, including startup and rate updates, can also reach oscillator methods outside this render chain. Treat replacement rendering as real-time interrupt-path work: avoid blocking, allocation and logging; hardware deadlines, stack and interrupt nesting still need measurement.

### Selection and state lifetime

There are four preconstructed voice banks, each with its own `0x4000`-byte workspace.
The selected oscillator is a per-bank object, not the workspace itself.
Inactive banks retain the placeholder object until activation.
On a Type change, the old object's `+0x14` runs before the selected object's `+0x0C`.
This also applies when two Types share the same outer object.
The `+0x10` result configures rates, slot capacity and event cadence independently of the descriptor.
A change of rate calls primary `+0x30` on all four selected objects, including inactive placeholders.
For Plaits, `0x0802FF0C` updates a shared rate coefficient; `0x0802FDA4` is the common no-op for the other families.

Storage sharing is per bank; it does not make all models one interchangeable object:

- Idle and BasicWaves use the same outer object; Wavetable and WaveUser share another.
- Scan, Cloud and Hit Grains share an outer object; the seven Plaits Types share a separate outer object and child container.
- BasicWaves, SuperWave and Vocoder bind shared per-bank phase storage outside the workspace.
- A shared object or phase pool does not imply that switching Types preserves every field; initialization and reset are model-specific.
- Wavetable, WaveUser, Sample and Grains depend on external storage; selecting a Type does not guarantee valid assets.

During a frame, note and gate callbacks run when an event is consumed, not for every sample.
Changed oscillator parameters are dispatched through `+0x18`; each model interprets them after caching the raw value.
The frame prepares pitch and envelopes before the `+0x24` render tail-branch.
The `+0x20` auxiliary operation is model-specific and must not be treated as a universal full reset.

### Plaits child tables

The path is primary render `0x0803099C` → `0x0800D480` → `0x0805F458` → child `+0x08`. Two header words precede each child table; they are not methods or a trailing zero. `tools/ghidra/MfSeed.java` seeds indirect targets.

| Engine | Child vtable | `+0x08` render |
|---|---|---|
| Chords | `0x08078578` | `0x080589C8` |
| Two Op. FM | `0x08078590` | `0x08059220` |
| Formant | `0x080785A8` | `0x08059A10` |
| Modal | `0x080785C0` | `0x0805B024` |
| Speech | `0x080785D8` | `0x0805B20C` |
| V.Analog | `0x08078604` | `0x0805B574` |
| Waveshaper | `0x0807861C` | `0x0805C9A0` |

Child `+0x00` takes `(self, allocator)`, `+0x04` resets, and `+0x08` takes `(self, parameters, float *main, float *aux, frames, bool *already_enveloped)`; the last two arguments are on the stack. `+0x0C` is a partial reset or no-op, with no invocation observed during exercised gate/Type changes. Type changes initialize all seven children with overlapping workspace; child selection then invokes `+0x04` as needed.

## The per-engine config method

Primary slot `+0x10` returns a packed capability word, distinct from the 28-byte descriptor. The shared Plaits implementation is `0x0802FEA4` (its table slot is at `0x08074D24`); the Type argument determines its answer. Other families use their own or a shared implementation.

| Bits | Meaning |
|---|---|
| `0..7` | Mono sample rate in kHz. |
| `8..15` | Paraphonic sample rate in kHz. |
| `16..23` | Slot capacity. |
| `24..31` | Global event interval in firmware frames; zero bypasses throttling. |

The directory above gives each Type's word and decoded fields. KarplusStr's interval is global across banks, not a per-voice flag; six frames were observed as 192 codec samples with 32-sample blocks. A replacement engine may need a different config answer.

## How FreakSwap replaces an engine

FreakSwap's 38 published patches all have the same shape. Mapped to flash addresses:

| What | Size | Purpose |
|---|---|---|
| The host engine's render code | 1.5–4.8 KB | New engine code, plus its name and label strings, written over the old engine |
| The host's descriptor | 11–20 B | Codec/default/gain configuration, and pointers to the new name and labels |
| The host's child vtable | 6–11 B | Changed bytes in the four method pointers into the new code |
| `FUN_0802FEA4` | 4 B | Its first instruction becomes a `b.w` into new code that returns the new engine's config answer (not needed for Chords and Formant, whose stock answer already suits) |
| A few single bytes | 1–3 B | e.g. `0x0804DFB6` for some Chords swaps, `0x0805F66C` for Speech |
| Image checksum, ZIP CRCs | 10 B | as in [the update file format](update-file-format.md) |

Example, Bass Drum replacing V.Analog (3,344 bytes differ from stock):

```
child vtable at 0x08078604: four Thumb method pointers → new method pointers
descriptor 0x0806259C:
  header → Formant's header
  "V.Analog" "Detune" "Shape" "Wave"  →  "Bass Drum" "Attack" "Tone" "Decay"
0x0802FEA4:  push {r4}; subs r1,#6  →  b.w 0x0805C310   (new config answer)
```

Lessons from it:

- **Seven engines have been used as hosts:** Chords, Formant, Modal, Speech, Two Op. FM, V.Analog and Waveshaper. A large engine fits only into a large host: about 4.8 KB (a string model) or 3.1–3.3 KB (drums) only goes into Formant's 5.5 KB or V.Analog's 4.9 KB.
- **CPU and RAM fit.** The new code is real floating-point DSP, about 590 VFP instructions where V.Analog had about 700 in the same range, and it runs in the host's 16 KB buffer and voice slot.
- **Presets follow the slot.** A preset that used the replaced engine plays the new one with the same knob values.
- **Vocoder** is never offered as a host by FreakSwap (its rules forbid it). It is the one engine that uses the audio input.

## Replacing an engine with this toolchain

ThisFirmwareDoesNotExist's patch format (code region + hooks + edits) covers everything above: the host's render code is the region, and the child-vtable words, descriptor fields and the `0x0802FEA4` branch are edits and hooks. A sketch of the work:

1. **Pick a host** whose render code is at least as big as your engine, and that you're happy to lose. Check references with `references()` from `tests/refscan.py` ([how](free-space-and-dead-code.md#proving-code-is-unreachable-testsrefscanpy)); account for indirect calls and code/data pointers as well as direct references. Render bodies may share helpers with other engines; only overwrite what no other path uses.
2. **Write the engine.** `tools/build_patch.py` assembles one `.S` file and refuses relocations. For C or C++ DSP code, extend it to compile with `clang --target=thumbv7em-none-eabihf -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -Os -ffreestanding -fno-exceptions -fno-rtti -nostdlib` and link with `ld.lld -Ttext=<region start>` into a flat binary, so absolute addresses inside your code are resolved at build time. No libc: bring your own math (Plaits' `stmlib` has fast approximations).
3. **Match the calling convention.** For a Plaits child use the child ABI above, not the outer PCM ABI. Inspect the host's init and render methods, float ABI, object fields and expected block sizes; the child uses float main/aux buffers and normally receives 12 or 16 internal samples.
4. **Re-point the child vtable** (four word edits), **the descriptor** (codec/default/gain fields and string pointers as needed), and **hook `0x0802FEA4`** if your engine needs a different config answer. Its implementation is shared: preserve the answers for all other Types.
5. **Fit the existing state layout and workspace.** The shared per-bank workspace is 16 KB, but the child object and other state also have fixed placement. Don't add globals: there's no free RAM.
6. **Test under emulation** (`tests/emu.py`): call your render method with a correctly initialized child object and check its float buffers, then compare a stock engine's render for the same setup. An isolated call does not prove Type selection, event delivery or full audio works.
7. **Flash a diagnostic first,** as for any patch ([writing a patch](writing-a-patch.md#test-on-hardware-in-steps)).

If you port Plaits code, keep Mutable Instruments' MIT copyright notice with your patch source.

## Open questions

1. **Descriptor bytes:** the meanings and possible consumers of `+0x00` and `+0x02` remain unresolved; correlation with rates does not prove a flags layout.
2. **Child `+0x0C`:** its additional-reset operation has no observed invocation during the exercised gate and Type changes; other paths remain possible.
3. **Engine selection:** how many other UI, preset and resource paths would need changes to add a Type beyond the existing 23 records.
4. **CPU headroom:** how much more an engine may cost than its host. Needs hardware measurement.
5. **Hardware validation:** isolated method calls do not establish full-path behaviour, audio quality or safe timing on the synth.
