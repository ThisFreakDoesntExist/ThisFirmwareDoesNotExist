# ThisFirmwareDoesNotExist: MicroFreak firmware notes

ThisFirmwareDoesNotExist's map of Arturia's stock MicroFreak firmware **5.0.0.2084** (update file SHA-256 `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`), for people who want to write their own patches.

Working with a coding agent? [AGENTS.md](../AGENTS.md) holds the rules every change keeps and the steps from idea to a tested patch.

Read them in this order:

1. [Update file format](update-file-format.md): what's inside an `.mff`, and how to rebuild a valid one.
2. [Main image](main-image.md): the CPU, the memory map, and the subsystems a patch is likely to touch.
3. [Free space and dead code](free-space-and-dead-code.md): the two hard constraints, and where room for new code comes from.
4. [Writing a patch](writing-a-patch.md): from an idea to a file that's safe to flash.
5. [Flash writes](flash-writes.md): every place the firmware writes internal or external flash, and how to keep a patch away from them.
6. [Oscillator engines](oscillator-engines.md): how engines are described and dispatched, and how to replace one.
7. [The Release patch](release-patch.md): a complete worked example with every address justified.
8. [The mod matrix over MIDI CC](matrix-cc.md): a second patch, and how two patches combine into one build.
9. [Voice modes](voice-modes.md): Delay, Duo, mode notices and a tempo-synced cycling envelope; how to make a new voice mode, build patches in series, and save space.
10. [The screen and LEDs](screen-and-leds.md): how the OLED and matrix LEDs are fed, and what both patches change there.
11. [Spice and Dice](spice-and-dice.md): how the arp and sequencer randomisers work.
12. [Reverse-engineering setup](reverse-engineering-setup.md): the tools used to produce all of this.
13. [Related projects](related-projects.md): other open-source MicroFreak work.

## Conventions

- **Addresses** are flash addresses of the main image, with its 64-byte header stripped and the payload loaded at `0x0800C000`. `FUN_xxxxxxxx` names a function by its entry address, as Ghidra does.
- A Thumb **function pointer** has bit 0 set (`0x0802B8ED` points at the code at `0x0802B8EC`).
- **Parameter ids** are written `0xGGII`: group `GG`, index `II` (`0x602` is group 6, index 2, the Dec/Rel knob).
- Each fact is marked as **verified** (checked from the bytes, under emulation or on hardware) or **inferred** (a reading of the evidence that wasn't checked directly). Unmarked tables of addresses are verified.
- Everything here was derived from the official firmware alone, except the bootloader section of [flash writes](flash-writes.md#the-bootloader), which describes the bootloader read from a unit (no bytes published). Corrections are welcome: say how you checked.
