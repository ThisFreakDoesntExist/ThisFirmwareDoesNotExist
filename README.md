# ThisFirmwareDoesNotExist

**ThisFirmwareDoesNotExist presents `freakpatch`**: community firmware patches for the **Arturia MicroFreak**. Bring your own copy of Arturia's official update file, and `freakpatch` hands back a slightly freakier one, on your own computer. Nothing gets uploaded.

Want to go further than one knob? ThisFirmwareDoesNotExist also documents the stock firmware, so you can write your own patches.

> Not affiliated with or endorsed by Arturia. Custom firmware is at your own risk, and may affect your warranty (see [the fine print](#the-fine-print)). Flashing the official update file always restores stock.

**This repository contains no Arturia code or firmware.** It holds only ThisFirmwareDoesNotExist's own machine code (with its assembly source), the addresses where that code hooks in, and the SHA-256 of the one official file it accepts. You bring the firmware; `freakpatch` does the surgery and writes the patched file next to it.

## Full Vibe?

Absolutely. Claude Code did all the work. I won't lie. I read the code. Tested it. Understood it, but the work is all Claude Codes over maybe 1-2 sessions with Opus 5.5. If you hate it, fair enough. But I want to be transparent. Firmware is _not_ my day job. But my aim is for this to open up a pool of more intelligent, more creative, and more hardware aware folk to take a stap at doing some fun stuff with the Microfreak.

## The patches

The MicroFreak's amp envelope makes one knob, **Dec/Rel**, do two jobs. Decay and release have been sharing it for years. This patch gives them separate rooms:

- The knob sets **Decay** only, and the screen calls it Decay.
- **Shift + Decay** sets **Release**. The screen shows Release with its own time, in the same envelope popup as Attack, Decay and Sustain, and draws the curve with the Release time.
- Release responds to MIDI **CC 72** (MIDI's standard "Release Time") and is sent out on it. `--release-cc` picks another free CC.
- Release is **saved in presets**. Presets saved on stock firmware load with Release = Decay and sound exactly as before. Presets saved with the patch still load on stock firmware, which ignores the extra field. MIDI Control Center backup and restore works.
- Modulation applied to Decay scales Release in the same proportion.

On stock firmware the mod matrix has exactly one MIDI CC. Filter Amt (CC 26), which is really the Env to Cutoff spot in the matrix. The rest of the matrix you can't automate at all. `--patch release-matrix` fixes that. You get the Release patch plus a CC for the other 34 matrix amounts, in and out.

- CC 0 is -100%, 64 is 0, 127 is +100%. Same math the firmware already uses for Filter Amt.
- Turn a matrix amount on the synth and it sends the CC. Send the CC and the amount changes.
- The matrix LEDs don't update when a CC comes in. You hear the change right away, but the LED won't show it until you scroll over that spot in the matrix. Stock does the same thing with Filter Amt, so I left it alone. MIDI changes the value but never tells the screen to redraw. More on that in [docs/matrix-cc.md](docs/matrix-cc.md#why-incoming-ccs-dont-light-the-matrix).

Could it do more? Sure. But thats your job and the point of this repo!

Tested on hardware with 5.0.0.2084 ([results](docs/matrix-cc.md#hardware-results)).

### Matrix CC map

Rows are destinations, columns are sources. Stock doesn't map any of these to a parameter, none clash with Release on 72, and none are CCs MIDI already reserves for something (mod wheel, sustain, bank select, that kind of thing). If one clashes with your setup, open an issue. `--release-cc` won't let you pick one of these.

| Destination / Source | CyclEnv |             Env | LFO | Press | Key/Arp |
| -------------------- | ------: | --------------: | --: | ----: | ------: |
| Pitch                |      14 |              15 |  20 |    21 |      22 |
| Wave                 |      25 |              27 |  30 |    31 |       3 |
| Timbre               |      85 |              86 |  87 |    80 |      89 |
| Cutoff               |      90 | 26 (Filter Amt) | 104 |   107 |     108 |
| Assign 1             |     109 |             110 | 111 |   112 |     113 |
| Assign 2             |     114 |             115 | 116 |   117 |     118 |
| Assign 3             |     119 |              75 |  76 |    77 |      78 |

**Heads up, this might break the Vocoder.** 14 of these CCs (75–78, 80, 111–119) aren't totally free. Stock firmware quietly listens to CC 75–82 and 111–118 for something with 16 slots, and CC 119 sets all 16 at once. My best guess is the Vocoder's 16 bands, but that's a guess. With this patch those CCs go to the matrix instead, so whatever stock used them for won't get them anymore. Untested. Details in [docs/matrix-cc.md](docs/matrix-cc.md#ccs-stock-already-listens-to).

## Use

You need Python 3.11 or newer, and something to feed it: the official update file `microfreak_Firmware_Update_5.0.0.2084.mff`. Download it from Arturia's MicroFreak resources page, or use the copy MIDI Control Center keeps (on macOS: `/Library/Arturia/MIDI Control Center/Firmware/`).

With [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/ThisFreakDoesntExist/ThisFirmwareDoesNotExist.git
cd ThisFirmwareDoesNotExist
uv run freakpatch ~/Downloads/microfreak_Firmware_Update_5.0.0.2084.mff
# wrote ~/Downloads/microfreak_Firmware_Update_5.0.0.2084_release.mff
```

Or install it as a command you can run from anywhere:

```sh
uv tool install ./ThisFirmwareDoesNotExist   # or: pipx install ./ThisFirmwareDoesNotExist
freakpatch microfreak_Firmware_Update_5.0.0.2084.mff
```

Or with plain Python and no dependencies to install:

```sh
cd ThisFirmwareDoesNotExist
PYTHONPATH=src python3 -m freakpatch path/to/microfreak_Firmware_Update_5.0.0.2084.mff -o microfreak_release.mff
```

| Option           | Meaning                                                                                                                                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-o OUT.mff`     | where to write the patched file (default: next to the input, named `<input>_<patch>.mff`)                                                                                                                                                                           |
| `--release-cc N` | MIDI CC for Release instead of 72. Must be 1–119 and not one of the CCs the stock firmware already uses.                                                                                                                                                            |
| `--patch NAME`   | `release` (default), `release-matrix` (Release plus the mod matrix over MIDI CC), `matrix-cc` (the matrix alone), or one of the hardware diagnostics `diag-region` / `diag-hook` (see [docs/writing-a-patch.md](docs/writing-a-patch.md#test-on-hardware-in-steps)) |
| `--list`         | describe the available patches                                                                                                                                                                                                                                      |

`freakpatch` is a picky eater. It accepts **only** the official 5.0.0.2084 file (SHA-256 `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`). It refuses anything else, including a file it has already patched: one freaking per file. It also checks its own output: same length as stock, and nothing changed except the bytes the patch declares.

No surprises in the output either: it's deterministic. The default Release build has SHA-256 `282ec291a73e89800c52872e4446664e350818978824e1e89003bdadda7d4834`, byte for byte the file that passed the hardware checklist ([docs/writing-a-patch.md](docs/writing-a-patch.md#test-on-hardware-in-steps)). Building with another `--release-cc` gives a different hash.

### Flash it

1. Open MIDI Control Center with the MicroFreak connected over USB.
2. Run the firmware update and pick the **patched** `.mff`.
3. When it's done, turn the knob: Decay on its own, then Shift + Decay for Release. Enjoy the long tails.

**Changed your mind?** Run the same update with the official file and you're back to stock.

**If the synth doesn't start** (it sits at the boot logo, looking embarrassed): hold **Shift + Arp + Oct** while powering on, then update from the official file in MIDI Control Center. No harm done.

### The fine print

- **Don't share patched `.mff` files.** Share this repository instead and let people patch their own copy. A patched file is a modified version of Arturia's firmware, and Arturia's software licence (chapter 23 of the MicroFreak manual) forbids modifying it "for the purpose of distribution, assignment or resale". That rule is why this repository ships patches, not firmware. Keep it that way.
- **Warranty.** Arturia's warranty doesn't cover problems caused by modification. Flash the official file before sending the synth in for service, or before asking Arturia support for help, so they're looking at stock firmware.

## For firmware developers

[`docs/`](docs/README.md) is a working map of the stock 5.0.0.2084 main firmware, written so you can build your own patches:

| Document                                                       | What's in it                                                                                                   |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [Update file format](docs/update-file-format.md)               | The `.mff` container, image headers, checksums, the wavetable image                                            |
| [Main image](docs/main-image.md)                               | MCU, memory map, interrupts, audio path, voices, parameters, presets, panel, screen, factory console           |
| [Free space and dead code](docs/free-space-and-dead-code.md)   | Why the image can't grow, why "dead" functions usually aren't, which console handlers can be retired for space |
| [Writing a patch](docs/writing-a-patch.md)                     | The patch format, hooks and edits, building, testing under emulation, flashing safely                          |
| [Oscillator engines](docs/oscillator-engines.md)               | Engine IDs, the descriptor table, engine classes, and how to replace an engine                                 |
| [The Release patch](docs/release-patch.md)                     | Every address the Release patch uses and how it was derived and checked: a worked example                      |
| [The mod matrix over MIDI CC](docs/matrix-cc.md)               | The matrix as stock stores it, the six hooks, the CC table, the LED refresh, combined builds                   |
| [The screen and LEDs](docs/screen-and-leds.md)                 | How the OLED and matrix LEDs are fed, the envelope curve on the OLED chip, and what the patches change there   |
| [Spice and Dice](docs/spice-and-dice.md)                       | How the arp and sequencer randomisers work, and where to dig further                                           |
| [Reverse-engineering setup](docs/reverse-engineering-setup.md) | Headless Ghidra scripts and the raw-byte reference scanner                                                     |
| [Related projects](docs/related-projects.md)                   | Other open-source MicroFreak tools and where they fit                                                          |

### Repository layout

| Path                            | Contents                                                                                                                                                                                |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/freakpatch/`               | The `freakpatch` CLI and library: `mff.py` (update container), `thumb.py` (Thumb-2 branch encoders), `patcher.py` (hash gate, apply, self-check), `cli.py`                              |
| `src/freakpatch/patches/*.json` | Built patches: our code bytes, symbols, hook sites, edits                                                                                                                               |
| `patches/`                      | Patch sources: `release.S` + `release.hooks.json`, `matrix_cc.S` + `matrix-cc.hooks.json`, the combined `release-matrix.hooks.json`, and the diagnostics `diag.S` + `diag-*.hooks.json` |
| `tools/build_patch.py`          | Assembles a patch with clang into the shipped JSON                                                                                                                                      |
| `tools/ghidra/`                 | Headless Ghidra scripts for exploring the stock image                                                                                                                                   |
| `tests/`                        | Unit tests, a Unicorn harness that runs single stock functions (`emu.py`), and the raw-byte reference scanner (`refscan.py`)                                                            |

### Develop

```sh
uv sync
uv run pytest                                      # firmware tests need the official file, see below
uv run python tools/build_patch.py patches/release # needs clang with the Thumb target
uv run ruff check . && uv run ruff format --check .
```

Tests that read or emulate firmware use the file named by `FREAKPATCH_STOCK_MFF`, or MIDI Control Center's copy on macOS, and are skipped if neither is there. They run the real stock constructor, knob handler, preset saver and parser, and screen code with the patch in place.

Contributions are welcome, especially new patches and corrections to the docs. Please keep the ground rules: derive everything from Arturia's official firmware, never commit firmware or bytes copied from it, and keep the main image at its stock length.

## Credits

- **[ThisFreakDoesntExist](https://github.com/ThisFreakDoesntExist):** project direction, and every flash, recovery and listening test on real hardware.
- **[Claude Code](https://claude.com/claude-code):** firmware analysis, the patches, `freakpatch`, the tests and these docs.

## License

[MIT](LICENSE). The MicroFreak firmware itself belongs to Arturia and isn't covered by this license or included here.
