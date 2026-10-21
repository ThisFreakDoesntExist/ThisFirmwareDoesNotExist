# Changelog

Versions follow [semantic versioning](https://semver.org/). Every build takes the official 5.0.0.2084 file (SHA-256 `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`) and is deterministic, so each patch's output hash with default options is listed: if yours matches, it's the same file.

## 0.3.0 (unreleased)

### Added

- `--patch voice-modes`: `release-matrix` plus four features ([docs](docs/voice-modes.md)).
  - **Delay:** hold Paraphonic 0.5 s and each note echoes 3 times on other voices, a dotted 1/8 apart, quieter each time.
  - **Duo:** Shift + Paraphonic from Unison gives two notes on two detuned voices each. "Unison Spread" reads "Spread/Detune" in the Utility menu and on the spread page (an OLED image edit).
  - **Mode notices:** a 3 s page naming the voice mode a Paraphonic gesture turned on or off.
  - **Cycling-envelope sync:** Shift + Mode locks Rise and Fall to the tempo in the LFO's divisions, shows "Cyc-Env Sync ON/OFF", and the mode LED blinks on the beat.
- Patch format: parts appended after the stock image, the image padded so the bootloader accepts it ([why](docs/free-space-and-dead-code.md#constraint-1-the-image-grows-only-in-whole-words)). Also several sections per source, direct `call` / `jump` to fixed addresses, chained hooks, `word` hooks, and combined specs built from combined specs ([writing a patch](docs/writing-a-patch.md#several-regions-appending-and-chains)).

### Fixed

- Docs: the factory console's handler names follow the dispatcher, not the name table. The Release region is `sync`, `oled` and `boot`, and the region the docs listed as a free `boot` handler is `filter`, which runs at every boot ([free space](docs/free-space-and-dead-code.md#making-space-retiring-console-commands)).

### Unchanged

- `release`, `release-matrix` and `matrix-cc` build byte for byte as in 0.2.0.

### Builds

| Patch | SHA-256 | Hardware |
|---|---|---|
| `release` | `282ec291a73e89800c52872e4446664e350818978824e1e89003bdadda7d4834` | tested |
| `release-matrix` | `303bed10214f5b704b6d7bed4ed52af1f4e948967abcb838f2916cbbee05444a` | tested |
| `voice-modes` | `55e89bb8fdebeec6f39ea5131f6e36e786ef71ab347d2489afa182cb70ff24b6` | v4, emulator-verified; v3 (`dca1a913…`, without the spread title and the Cyc-Env notice) tested ([plan](docs/voice-modes.md#hardware)) |
| `matrix-cc` | `20ae48a42607c512e34922e1170a7a15b609aa3d4c7dd97d895cfdff0d4c833e` | not flashed on its own |

## 0.2.0 (2026-10-13)

### Added

- `--patch release-matrix`: the Release patch plus the mod matrix over MIDI CC, in one build ([docs](docs/matrix-cc.md)).
  - The 34 matrix amounts without a stock CC get one, in and out. CC 0 / 64 / 127 = −100% / 0 / +100%.
  - An incoming matrix CC lights or clears that cell's LED, with no popup ([the LED refresh](docs/matrix-cc.md#the-led-refresh)).
  - The envelope popup draws Decay and Release as separate curve segments, by also patching the OLED chip's image ([details](docs/release-patch.md#separate-decay-and-release-segments-release-matrix)).
- `--patch matrix-cc`: the mod matrix over MIDI CC on its own.
- `freakpatch --version`.
- Patch format: `half` edits, edits to the OLED image (`"image": "oled"`), and combined builds from several patches ([writing a patch](docs/writing-a-patch.md#the-spec)).
- Docs: [The screen and LEDs](docs/screen-and-leds.md), [Spice and Dice](docs/spice-and-dice.md), and decompiling every function at once in the [reverse-engineering setup](docs/reverse-engineering-setup.md).

### Unchanged

- The default `release` build is byte for byte the 0.1.0 file.

### Known issues

- CCs 75–78, 80 and 111–119 are also read by a stock handler for something with 16 slots, possibly the Vocoder's bands. With `release-matrix` or `matrix-cc` they go to the matrix instead. Untested ([details](docs/matrix-cc.md#ccs-stock-already-listens-to)).

### Builds

| Patch | SHA-256 | Hardware |
|---|---|---|
| `release` | `282ec291a73e89800c52872e4446664e350818978824e1e89003bdadda7d4834` | tested ([checklist](docs/writing-a-patch.md#test-on-hardware-in-steps)) |
| `release-matrix` | `303bed10214f5b704b6d7bed4ed52af1f4e948967abcb838f2916cbbee05444a` | tested ([results](docs/matrix-cc.md#led-refresh-on-hardware)) |
| `matrix-cc` | `20ae48a42607c512e34922e1170a7a15b609aa3d4c7dd97d895cfdff0d4c833e` | not flashed on its own |

## 0.1.0

### Added

- `freakpatch`, with the Release patch: Dec/Rel sets Decay only, Shift + Decay sets Release, which has its own MIDI CC (72 by default, `--release-cc`) and is saved in presets ([docs](docs/release-patch.md)).

### Builds

| Patch | SHA-256 | Hardware |
|---|---|---|
| `release` | `282ec291a73e89800c52872e4446664e350818978824e1e89003bdadda7d4834` | tested |
