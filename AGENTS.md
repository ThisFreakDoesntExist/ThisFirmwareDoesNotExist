# AGENTS.md

`freakpatch` patches the user's own official Arturia MicroFreak 5.0.0.2084 update file. This repository ships **patches, never firmware**: our assembly, the addresses it hooks, and the SHA-256 of the one file it accepts.

## Hard rules

These keep the project legal to publish. Every change keeps all of them.

1. **Only our bytes are committed.** Code we wrote, addresses, and short strings we wrote. Firmware, bootloader bytes, a patched `.mff`, decompiled listings and dumps of stock data stay on your machine (`*.mff` and `*.bin` are gitignored). Reuse a stock string or table by its address.
2. **Facts come from the official file**: its bytes, running it under emulation, or the synth. Never from other people's modified firmware.
3. **Patches never write flash** ([flash writes](docs/flash-writes.md)). New state lives in RAM, or in a real parameter that the stock preset saver stores.
4. **Builds are deterministic.** A shipped build's SHA-256 goes in `CHANGELOG.md`; a change that alters an existing build's hash is a new version.
5. **Contributors are credited by handle.** Docs, code comments and commits name no private person, home path or private project; say "the user" or "on hardware".

## Making a patch

1. Read [docs/README.md](docs/README.md) in its order, at least through [writing a patch](docs/writing-a-patch.md). [Voice modes](docs/voice-modes.md) shows the full workflow for a multi-part feature.
2. Pick space: a retired console handler or the area after the stock image ([free space](docs/free-space-and-dead-code.md)). Prove it unreachable with `tests/refscan.py`, and explain every hit.
3. Write `patches/NAME.S` and `patches/NAME.hooks.json`. Every hook and edit records what it replaces in `was`.
4. `uv run python tools/build_patch.py patches/NAME`, then add `NAME` to `PATCHES` in `src/freakpatch/cli.py`.
5. Test with the user's official file: `FREAKPATCH_STOCK_MFF=/path/to/official.mff uv run pytest`. Done when every test passes, including a new `tests/test_NAME.py` that checks the build's SHA-256 and that each hook site's stock instruction is what `was` claims.
6. `uv run ruff check . && uv run ruff format --check src tools tests`.
7. Hand hardware testing to the user, in the steps of [test on hardware in steps](docs/writing-a-patch.md#test-on-hardware-in-steps). Record the result in the docs as verified on hardware, in emulation, or inferred.

## Emulation

`tests/emu.py` runs **single stock functions** under Unicorn: enough to check a hook's registers and a handler's result. Full-system behaviour (sound, screen, LEDs, timing) was checked in a separate, unpublished emulator or on the synth; the docs say which for each fact.
