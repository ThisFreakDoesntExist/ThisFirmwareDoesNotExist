# The main image (5.0.0.2084)

Arturia's `nanowave_main__fw5_0_0_2084__2023_05_30.bin`: 473,696 bytes of Thumb-2 code and data, loaded at `0x0800C000`.

## MCU

**Inferred: STM32F446, a Cortex-M4F with 512 KB flash and 128 KB SRAM.**

| Evidence | Value | Status |
|---|---|---|
| Initial stack pointer | `0x20020000`, the top of 128 KB SRAM | verified |
| Load base | `0x0800C000`; the 48 KB below holds the bootloader | verified by pointer/string correlation |
| Highest flash pointer in the image | below `0x08080000`, consistent with 512 KB flash | verified |
| Vector table | Zero entries at IRQ 61, 62, 79, 80, 82, 83, 85, 86, 88, 89, 90: exactly the slots the F446 reference manual (RM0390) marks reserved | verified (table), inferred (part) |
| Peripherals | SAI1 (`0x40015800`), SAI2 (`0x40015C00`), DMA2, QUADSPI, USB OTG FS | verified |
| Floating point | about 10,700 VFP instructions | verified (pattern count) |
| Library | ST HAL: the DMA IRQ handler at `0x0801B31C` matches `HAL_DMA_IRQHandler`; I2C writes go through a `HAL_I2C_Mem_Write`-shaped call at `0x0801C0CC` | inferred from structure |

## Memory map

| Region | Range | Notes |
|---|---|---|
| Bootloader | `0x08000000–0x0800BFFF` | Not in the update file |
| Main firmware | `0x0800C000–0x0807FA5F` | Code and data. The trailing checksum byte is at `0x0807FA5F`. |
| Flash after the image | `0x0807FA60–0x0807FFFF` | 1,440 bytes, but **not usable**: a longer image hangs at boot ([why](free-space-and-dead-code.md#constraint-1-the-image-cant-grow)) |
| `.data` | flash `0x0807F75C`, `0x2F4` bytes → RAM `0x20000000` | copied by the reset handler `0x0805F848` |
| `.bss` | `0x200002F8–0x2001F230` | zeroed by the reset handler |
| Stack | `0x2001F230–0x20020000` | |
| External serial flash (QUADSPI) | 16 MB | Presets (4 KB each), samples, user wavetables |

SRAM is practically fully allocated: the highest address the code references is `0x2001FEE7`. New code must find RAM in padding or unused table slots, as the Release patch does.

## Interrupts in use

The default handler is `0x0805F89C`; 75 vectors point to it. IRQ names follow the F446 table.

| IRQ | Peripheral | Handler |
|---|---|---|
| — | Reset | `0x0805F848` |
| SVC / PendSV / SysTick | scheduler hooks | `0x08025490` / `0x08025494` / `0x08025498` |
| 6 | EXTI0 | `0x08025710` |
| 14, 15, 17 | DMA1 Stream 3, 4, 6 | `0x080254CC`, `0x0802551C`, `0x080254A8` |
| 37, 38, 39 | USART1, 2, 3 (links to the I/O chips and MIDI DIN, inferred) | `0x08058214`, `0x080582BC`, `0x08058364` |
| 40 | EXTI15_10 | `0x080256BC` |
| 45, 46 | TIM8 TRG/COM/TIM14, TIM8 CC | `0x0802569C`, `0x0802555C` |
| 50 | TIM5 | `0x08025674` |
| 56 | DMA2 Stream 0 (likely ADC) | `0x080254B4` |
| **60** | **DMA2 Stream 4: SAI2 Block A transmit (audio out)** | `0x0802F008` → `HAL_DMA_IRQHandler` |
| 67 | USB OTG FS | `0x080254C0` |
| **69** | **DMA2 Stream 6: SAI2 Block B receive (audio in)** | `0x0802F28C` → `HAL_DMA_IRQHandler` |
| 70 | DMA2 Stream 7 | `0x08025528` |
| 92 | QUADSPI | `0x08025550` |

## Audio path

```
oscillator engine (float DSP, 4 voices)
        │
  SAI2 Block A  (master TX, 16-bit, circular DMA2 S4 ch3, IRQ prio 5)
        │  96,000 Hz
  I2C codec @ 0x18  (TLV320AIC3x-class: inferred)
        │
  analog filter → analog VCA → outputs   (hardware)
        ▲
  SAI2 Block B  (slave RX: mic / vocoder input, DMA2 S6)
```

- **Init:** `FUN_08038AB0` (synth init) calls the audio init `FUN_0802F3BC(handle, 0, 0, 96000, 16, 2)`. The rate constant at `0x08038DA8` is `0x00017700` = 96,000, and the same value goes to every voice's set-sample-rate method.
- **PLL:** `FUN_0802F3BC` programs the audio PLL one way for 11,025/22,050/44,100 Hz (N = 429) and another for all other rates (N = 344), then configures SAI2 for 16-bit data on both blocks.
- **DMA:** `FUN_0802F13C` sets up transmit DMA in **circular** mode (half-word, memory to peripheral, high priority, IRQ 60 at priority 5): a ping-pong buffer refilled from the half-transfer and transfer-complete callbacks. A 256-entry buffer is registered through `FUN_0802F04C(handle, buf, 0x100)`; whether the unit is samples or frames wasn't confirmed.
- **Codec (inferred TI TLV320AIC3x family):** register writes go to I2C address `0x18`; the setup routine `FUN_0802F91C` writes registers up to `0x6D`. The output-gain helper `FUN_0802F908(dev, idx, gain)` writes `gain<<4 | 0x09` to one of the registers in the table at `0x08074CE4` (51, 58, 65, 72, 86, 93), which are the AIC3x output-level registers.
- **The filter and VCA are analog** and sit after the DAC. Firmware can't process audio after the filter.

## Voices and RAM

`FUN_08038AB0` loops over **4 voice objects, `0x59E4` (23,012) bytes each**: 92,048 bytes, about 70% of SRAM. For each voice it gets a per-voice resource from `FUN_0804DE50(…, i)`, sets envelope defaults (`FUN_0800DC24(v, 500)` attack, `FUN_0800DC50(v, 0)` decay, `FUN_0800DC74(v, 0x7FFF)` sustain, `FUN_0800DC8C(v, 500)` release), and calls the set-sample-rate method with 96,000.

The active oscillator engine gets a **16 KB work buffer** through its `init(2, buf, 0x4000)` method. See [oscillator engines](oscillator-engines.md).

### Envelope setters

| Function | Writes | Role |
|---|---|---|
| `FUN_0800DC24(env, t)` | `+0x3E`, coefficient `+0x14` | Attack time |
| `FUN_0800DC50(env, t)` | `+0x40`, then `FUN_0800D5AC` | Decay time |
| `FUN_0800DC74(env, lvl)` | `+0x58` | Sustain level |
| `FUN_0800DC8C(env, t)` | `+0x42`, coefficients `+0x28`, `+0x2C` | Release time |

The envelope always had a release stage; stock just feeds it the Dec/Rel value. The voice update `FUN_0803352C` recomputes the envelope only when Dec/Rel changed (`0x0803418C–0x0803419A`) or modulation is active.

## Parameters

Every synth setting is a parameter in one static object at `0x2001C898`, built at boot by `FUN_0800EB10` (called from `FUN_0804352C`).

- **Ids** are `0xGGII` (group, index). Getter `FUN_08023C2C(obj, id)` returns `*(u16 *)(obj->values[G] + I*2)`. Setter `FUN_08023C40(obj, id, v, force)` stores when the value changed and notifies listeners.
- **Groups** are registered by `FUN_0800E7B4(obj, values, flags, ccs, keys8, names12, n)`. It accepts up to **24 groups; stock registers 20**, and every per-group table is sized for 24. That leaves four free group slots for new parameters. (Verified: the Release patch registers group 20.)
- **Group names** (4 bytes each, `0x08062478`): `VCO VCF EG1 Kbd Arp LFO EG2 Gen Sys Mat Co1 Co2 Co3 Co4 Co5 Co6 Co7 SyA Seq Voc`, then `"?"` for entry 20.
- **Keys and display names:** each parameter has a short internal key (saved in presets) and a display name, for example `DecRel` / `Dec/Rel`, `PrstVol` / `Preset Vol`, `UniSprd` / `UniSpread`, `GateLen` / `Gate Len`.
- **Flag byte 1:** bit 0 = saved in presets, bit 2 = "Shift selects id + 1", bit 7 = handled as a UI control.
- **MIDI CCs:** the registrar fills a CC map at `obj+0x14C + cc*2` = (index, group). Stock maps CCs 2, 5, 9, 10, 12, 13, 23, 24, 26, 28, 29, 83, 91, 92, 93, 94, 102, 103, 105 and 106. Incoming CCs go through `FUN_080478A4`; the listener `FUN_080239CC` sends CCs out when a mapped parameter changes. A newly registered parameter with a CC gets both directions for free.
- **Group 6 (EG2, the amp envelope):** Mode, Attack (CC 105), Dec/Rel (CC 106), Sustain (CC 29), Legato, Amount (CC 26), Snap.

[The Release patch](release-patch.md#parameter-system) lists every function that reads the group count and what each does with an unknown group.

## Presets

- The saver `FUN_08054A68` walks every registered group and writes `0x20|len, group name`, then `0x40|len, key, 0x63, meta, lo, hi` for each saved parameter, then `0x40`, with a final `0x20` terminator, in a 4 KB buffer.
- The parser `FUN_08054E08` (one caller, `0x08055740`) first resets every stock group to hard-coded defaults, then loads fields by group name and key. A group name it doesn't know is skipped, so **presets with extra groups still load on stock firmware**.

## Panel

- The panel layout comes from 96 `conf` lines the firmware runs at boot (from `0x0807416C`): `conf pot PC1 1538` maps the Dec/Rel pot to control `0x602`, `conf btn PH2 2052` maps Shift to control `0x804`, and so on.
- The panel object's vtable at `0x08074C44` holds the button-press (`0x0804347C`), button-release (`0x08043494`), **pot** (`FUN_08040220`, absolute knob positions) and **encoder** (`FUN_08042BC8`, relative moves) handlers. **Both** knob handlers carry their own copy of the Shift rule. Hook both.
- Shift state is stored at `this+0x28` by `FUN_08043224`.

## Screen

- Parameter changes reach the screen through a listener (`FUN_0804ED94` → `FUN_080558C0`) that records the last touched parameter id.
- The UI tick `FUN_08052B84`, called from the main loop, turns that id into a popup. **Its id switch exists twice:** in the dispatcher `FUN_080519EC`, which the tick calls only on its first run, and inlined in the tick itself, which is the copy that runs from then on. Hook the inlined copy (and the dispatcher for completeness).
- The envelope popup `FUN_0804F7AC` draws the curve from `0x601`, `0x602`, `0x603` and `0x605` and formats the value with `FUN_0804E404(buf, id)`, the generic value formatter.
- The OLED co-processor draws the curve itself, from a 4-byte message of those four values (`FUN_080557E8` → queue `FUN_08021414`, then command `0x12`).
- Display names are copied from flash strings at boot, so renaming a control is a same-length string edit (the Release patch renames `"Dec/Rel"` to `"Decay"`).
- The boot screen string `Firmware version\n%d.%d.%d.%d` is at `0x080757AC`.

## Menus and sequencer

- Menus are grouped as Preset-Voice, Preset-Modulations, Preset-Scale, Preset-Seq/Arp, Preset-Vocoder, and Utility-Global/-Preset/-Midi/-Sync/-CV/Gate/-Controls/-Global Scale/-Master Tuning/-Mic./-Misc.
- The sequencer has one note track with patterns A/B, up to 64 steps, and four modulation lanes.
- **Built-in sequence patterns:** a list of ten pattern names at `0x08073A04` (`FUN_08028718` returns the count, `FUN_0802871C` name *i*). `FUN_08028264(seq)` writes one into a sequence slot (`0x412` bytes: 64 steps × 16 bytes plus a header): index 0 clears the slot, index 1 writes a 16-step chromatic test run, and indices 2–9 copy notes (`0x080739DC`), gate flags (`0x080739B4`) and lengths (`0x080739A8`). Case `0x16` of the command dispatcher `FUN_0805228C` reports the list, probably to MIDI Control Center over SysEx. Whether a player can reach these from the panel wasn't established.

## Factory test console

A command shell used for factory test and calibration. It's a large source of reclaimable code; see [free space and dead code](free-space-and-dead-code.md#making-space-retiring-console-commands).

- **Top-level commands** are numbered by the name table at `0x08073CD8`: gpio 0, codec 1, cvout 2, help 3, flag 4, audio 5, filter 6, ioc 7, synth 8, boot 9, sync 10, oled 11, emc 12, mixer 13.
- **Handler objects:** 13 objects of `0x20` bytes from `0x08073FD0` (indices 0–12; `mixer` has none). Word `+0x04` of each object is method 0, the command entry.
- **Sub-command and argument strings** (near `0x08074900–0x08074BF0` and in tables such as `0x08073D94` play/stop/pause/resume, `0x08073E04` note/pitch/param/gene/dump, `0x08073E34` Saw/Sqr/Tri/Sin, `0x08073F7C` pitch/cutoff/press/reso/vca, `0x08073FAC` mv/raw/cal) cover audio, filter calibration, codec routing, panel tests (`led`, `pot`, `btn`, `enc`), flash tests and logging.
- **The firmware issues only `audio`, `conf`, `filter` and `ioc` commands itself:** these are all of the image's strings that start with a command name (`audio play` at `0x08073CB0`, `filter mode …`, `ioc sel …`, and the 96 `conf …` lines).

## 4.0.1.1376 vs 5.0.0.2084

| | 4.0.1 | 5.0.0 |
|---|---|---|
| Load base / SP / vectors | `0x0800C000` / `0x20020000` | same |
| Code end | `0x08079D50` | `0x0807FA60` |
| Flash after the image | about 25 KB | 1,440 B |
| Highest RAM referenced | `0x2001FEE9` | `0x2001FEE7` |
| Functions found (seeded Ghidra pass) | 1,181 | 1,247 |

5.0 adds the Sample engine and the three granular engines (most of the growth), Env Snap, keyboard sensitivity, a linear curve, and the Preset-/Utility- menu reorganisation.

## Open questions

Good first projects for a contributor:

1. **Render callback:** which function fills the SAI2 transmit buffer? Trace the half/complete transfer callbacks from the DMA handle at `0x200045D4`. This is the hook point for any audio effect.
2. **CPU headroom** per audio block. Needs hardware: toggle a GPIO in the callback, or read the DWT cycle counter over SWD.
3. **Codec part number:** needs board inspection.
4. **Engine descriptor fields** and the per-engine config value (see [oscillator engines](oscillator-engines.md#open-questions)).
5. **RAM map:** where each subsystem's buffers sit, to find memory for a delay line or other state.
6. **The OLED image:** how the envelope curve message is drawn, for a true A-D-S-R curve.
