# Related projects

Other open-source MicroFreak work, and what each one adds to the picture.

## FreakSwap

**[doriamxyz/FreakSwap](https://github.com/doriamxyz/FreakSwap)**: an unofficial static browser tool that replaces **one** stock oscillator engine with one of 11 engines adapted from Mutable Instruments Plaits and stmlib.

- **Local only.** The user's firmware is read in the browser and never uploaded.
- **Patch format `MFLP0001`:** an 8-byte magic, the base file size (must be 941,572, the whole 5.0.0.2084 `.mff`), a range count, then `{u32 offset, u32 length, bytes}` ranges. Offsets are into the whole `.mff`, which works because ZIP members are stored ([format](update-file-format.md#container)).
- **Three hash gates:** the base must be the official 5.0.0.2084 file, the patch must match its catalog hash, and the result must match a catalog hash, so every output is a known file.
- **38 prebuilt patches**, each one engine into one host slot. Only 7 engines serve as hosts (Chords, Formant, Modal, Speech, Two Op. FM, V.Analog, Waveshaper), and Vocoder is never replaced.
- The engines carry Mutable Instruments' MIT notice. The engine source isn't in the repository, only compiled patch bytes.

[Oscillator engines](oscillator-engines.md#how-freakswap-replaces-an-engine) maps what each FreakSwap patch rewrites. ThisFirmwareDoesNotExist's patches and FreakSwap each require the untouched official file, so their outputs can't be stacked as-is. The Release patch changes console, parameter, envelope, panel and screen code, and FreakSwap changes engine code and tables, so a combined build looks plausible, but nobody has checked the overlap or tested one.

## mf-utils

**[dcower/mf-utils](https://github.com/dcower/mf-utils)**: a Python toolkit from the 3.0.x firmware era (`firmware.py`, `wavetables.py`, `wavetabula.py`) that extracts the factory wavetables from an `.mff` to WAV, replaces them, and smooths cycle edges.

It was the earliest public documentation of the format: `.mff` is a ZIP of `info.json` plus images, header byte 0 is the image number, and header byte 1 is repeated as the last byte (it treats that byte as an opaque "magic"; it's actually the XOR-8 checksum). Its wavetable geometry, 16 tables × 32 cycles × 256 int16 samples, still holds.

It doesn't load 4.x or 5.x files. The wavetable image was renamed (`userwavetable_factory_…`), its header gained a flash address and length (byte 0 is now `0x81`), its checksum isn't repeated at the end, and 64 KB of per-slot metadata now precede the samples ([details](update-file-format.md#the-wavetable-image)). Since 4.x these are user wavetable slots that MIDI Control Center can replace directly, so custom tables no longer need a firmware mod.

## Mutable Instruments Plaits

**[pichenettes/eurorack](https://github.com/pichenettes/eurorack)** (`plaits/`, `stmlib/`): Émilie Gillet's open-source Eurorack firmware, MIT-licensed. Several MicroFreak oscillator engines are adapted from Plaits, and it's the natural source for new engines: the DSP is written for a Cortex-M4F, in fixed-size blocks, with no heap. Keep its copyright notice with anything you port.

## feakk/Microfreak

**[feakk/Microfreak](https://github.com/feakk/Microfreak)**: a collection of content for the MicroFreak, including preset files such as the device's default Init preset. Useful as known-good preset data when testing preset loading and saving.

## Tools

- **[Ghidra](https://ghidra-sre.org/)**: disassembly and decompilation ([setup](reverse-engineering-setup.md)).
- **[Unicorn](https://www.unicorn-engine.org/)**: CPU emulation for running single stock functions in tests.
- **[uv](https://docs.astral.sh/uv/)**: runs the patcher and tests without manual environment setup.
