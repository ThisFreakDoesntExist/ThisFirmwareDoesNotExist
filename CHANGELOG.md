# Changelog

Versions follow [semantic versioning](https://semver.org/). Every build takes the official 5.0.0.2084 file (SHA-256 `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`) and is deterministic, so each patch's output hash with default options is listed: if yours matches, it's the same file.

## 0.2.0 (unreleased)

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
