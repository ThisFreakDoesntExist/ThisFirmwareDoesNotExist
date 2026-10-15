# Flash writes

The MicroFreak keeps state that a patch must never damage: a per-unit calibration block in internal flash, the bootloader's boot-status words next to it, and the user's presets and global settings in external flash. This page lists every place the firmware writes to either flash, what each writer does and when it runs, and how to make sure a patch stays away from them.

Main-image addresses follow the [conventions](README.md#conventions). The bootloader isn't in the update file, so its addresses (in [the bootloader](#the-bootloader)) are marked separately.

## Summary

| Flash | Area | Written by | When | Damage if it goes wrong |
|---|---|---|---|---|
| Internal | Calibration block, `0x08008000` (512 B, sector 2) | main image | at boot only if the block is blank; factory calibration commands | the synth's own calibration is lost; filter, resonance and VCA drift |
| Internal | Boot-status words in the same block | bootloader | during a firmware update | the synth stays in update mode until it's flashed again |
| Internal | Main image, sectors 3–7 (`0x0800C000–0x0807FFFF`) | bootloader | during a firmware update | recoverable: flash the official file |
| External (QUADSPI) | Preset slot sectors | main image | saving a preset | that preset |
| External (QUADSPI) | Global settings, `0xFFF000` | main image | every preset save | Utility settings revert to defaults |

A patch that adds no flash access of its own and doesn't hook or edit the functions below leaves all of this exactly as stock does.

## Internal flash

### The calibration block (`0x08008000`)

Sector 2 of the internal flash holds a single 512-byte block, written at the factory for each unit. Each section is guarded by the magic `0xA55A`.

| Offset | Size | Contents | Read by |
|---|---|---|---|
| `+0x00` | 17 B | unit string (magic at `+0x16`) | `FUN_08045E18` at boot, used as the USB serial number (inferred) |
| `+0x60` | 5 × 16 B | calibration records `pitch`, `cutoff`, `press`, `reso`, `vca`: `u16 index, offset, gain, x`, magic at `+0x0E` | `FUN_08023504` (`reso` and `vca`, at runtime) |
| `+0xB0` | 48 B | boot-status pairs, one per update target | the bootloader ([below](#the-bootloader)) |
| `+0xE0` | 129 × u16 | cutoff CV table (magic at `+0x1E4`) | `FUN_080234E8`, copied to RAM `0x20001718` at boot |

Verified under emulation and against the block read from a real unit. **The values are specific to each synth**: never ship, share or overwrite them, and never put code or data in sector 2. It sits below `0x0800C000`, so a patch built with `freakpatch` can't reach it with its own bytes; it can only reach it by calling, or changing, the code below.

### Writers in the main image

| Function | Name | What it does | When it runs | Status |
|---|---|---|---|---|
| `FUN_08045BDC` | calibration check | Checks the block's magics. If they're missing, erases the block and programs the firmware's defaults. | every boot (called at `0x08024852`); on a calibrated synth it writes nothing | verified under emulation |
| `0x0801B550` | `HAL_FLASH_Program` | Programs internal flash through the FLASH registers; the calibration check writes through it. | from the writers on this page | verified (behaviour); name inferred from ST HAL |
| `FUN_08045E78` | calibration store | Saves the calibration object (at RAM `0x20003550`) back to the block | console filter calibration: `FUN_080235A0` calls it after the last cutoff point (`0x7F`) | verified under emulation |
| `FUN_08045E58`, `FUN_08045F08` | record get/set | Read and update a calibration record, from the console's `pitch`/`cutoff`/`press`/`reso`/`vca` commands (`FUN_080235C4`, `FUN_080235F0`) | console only | inferred that the set path reaches the store |

None of these run in normal use on a calibrated synth. The console commands are factory test tools (see [the factory test console](main-image.md#factory-test-console)), and the firmware never issues them itself.

## External flash (QUADSPI)

The 16 MB serial flash (an ISSI IS25LP128) holds presets, samples and user wavetables. The main firmware reads it through memory-mapped quad reads and writes it with 4 KB sector erases (ISSI command `0xD7`) followed by page programs.

| Area | Address | Contents |
|---|---|---|
| Preset slot N (1–512) | `0x80000 + N·0x1000` | a 32-byte header (`u32 bank, u16 prog, u16 cat, u8, char name[14]`) and the preset body in the saver's format ([presets](main-image.md#presets)); an unused slot stays erased |
| Global settings | `0xFFF000` | the Utility settings, held in RAM at `0x200007A8` while running; erased flash means defaults |

| Function | What it does | When it runs | Status |
|---|---|---|---|
| `FUN_08054A68` | preset saver: serialises the preset and writes the slot and the global-settings sector (2 sector erases and 17 page programs for one save) | holding **Save** for more than a second | verified under emulation |
| `FUN_08045710` | reads the global-settings sector (one 4 KB read) | boot | verified under emulation |

Global setting `0x3F` is memory protect (`0` off, `1` slots 1–128, the default, `2` all). Saving to a protected slot shows "Memory Protect ON". Verified under emulation.

If a patch adds a parameter, the stock saver writes it with no extra code, and stock firmware skips it on load ([Release patch](release-patch.md#parameter-system)). That is the safe way to persist new state; don't write a sector of your own.

## The bootloader

The bootloader (`0x08000000–0x0800BFFF`) isn't in the update file and can't be changed by a patch. What follows was read from a unit's own flash, for this page only; no bootloader bytes are published here or anywhere in this repository. Addresses are bootloader addresses.

| Function | What it does | Status |
|---|---|---|
| `0x08001694` (main) | Boots the main image only if both boot-status words in the calibration block (`+0xB0` and `+0xB8`, each followed by magic `0xA55A`) read `0x5AA5`. Otherwise it stays in update mode. | verified under emulation |
| `FUN_080013B4` | Rewrites a boot-status word: copies the whole 16 KB sector 2 to RAM, erases it and programs it back | verified under emulation |
| `0x08001F08` (DFU Erase) | Erases sectors 3–7 for a main-image update | verified under emulation |
| `FUN_08000D08` (DFU Write) | Programs the update into `0x0800C000` onwards, 64 bytes per block | verified under emulation |

Two consequences:

- **An interrupted update is recoverable.** The bootloader marks the image "in progress" before erasing and "valid" only at the end, so the synth falls back to update mode. Hold **Shift + Arp + Oct** at power-on and flash the official file ([recovery](update-file-format.md#recovery)).
- **Don't cut power during an update.** Because `FUN_080013B4` erases sector 2 to change a status word, the calibration block briefly exists only in RAM. Losing power at that moment would probably lose the calibration with it. (Inferred from the code path; not tested, and please don't.)

## Keeping a patch away from flash

1. **Don't call the writers** above, `HAL_FLASH_Program`, or the QUADSPI driver from your code.
2. **Don't hook or edit inside them**, or inside their callers on the boot path (`FUN_08045BDC` and its call site `0x08024852`). A wrong branch there could run the erase on every boot.
3. **Don't touch the FLASH registers** (`0x40023C00`, RM0390) or the QUADSPI registers (`0xA0001000`). Reading presets through the memory-mapped window is safe; issuing commands isn't.
4. **Persist through stock code.** Register a parameter and let the preset saver write it, as the [Release patch](release-patch.md) does.
5. **Retiring console commands is fine,** and removes some writers along with them. The [free space](free-space-and-dead-code.md#making-space-retiring-console-commands) page lists which handlers can go. Retiring the filter or calibration commands means the synth can't be recalibrated from the console while the patch is installed; flashing the official file brings them back.
6. **Prove it under emulation** before flashing (below).

### Checking under emulation

Run the patched image and trap three things, each with a control that shows the trap works:

| Trap | Fires on | Control that must trip it |
|---|---|---|
| any write to the FLASH registers | unlock, erase, program | a boot with a blank calibration block (`FUN_08045BDC` writes defaults) |
| any store to `0x08000000–0x0807FFFF` | a direct write into flash | a test store to `0x08008000` |
| a QUADSPI command that is write-enable (`0x06`), a page program or an erase | preset and settings writes | a preset save (`FUN_08054A68`) |

A patch passes when its own code paths (boot, the feature, a preset save with the feature in use) trip only the QUADSPI trap during the save, with the same erases and programs as stock. `tests/emu.py` runs single functions without peripherals, so a trap there means mapping the two register blocks yourself and failing the test on any write.

## Publishing this kind of work

This repository's [ground rules](writing-a-patch.md#ground-rules) and [fine print](../README.md#the-fine-print) apply. For flash in particular:

- **Fine to publish:** addresses, structure layouts, function descriptions, magic numbers and defaults, and your own code. These are facts about how the firmware behaves, written in your own words.
- **Never publish:** firmware or bootloader bytes, a patched `.mff`, a calibration block or unit string, or a dump of anyone's external flash. A calibration block also identifies the unit it came from.
- Keep the work independent. Derive it from the official firmware and your own synth, not from other people's modified firmware.
