# ThisFirmwareDoesNotExist: MicroFreak firmware notes

ThisFirmwareDoesNotExist's map of Arturia's stock MicroFreak firmware **5.0.0.2084** (update file SHA-256 `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`), for people who want to write their own patches.

Read them in this order:

1. [Update file format](update-file-format.md): what's inside an `.mff`, and how to rebuild a valid one.
2. [Main image](main-image.md): the CPU, the memory map, and the subsystems a patch is likely to touch.
3. [Free space and dead code](free-space-and-dead-code.md): the two hard constraints, and where room for new code comes from.
4. [Writing a patch](writing-a-patch.md): from an idea to a file that's safe to flash.
5. [Oscillator engines](oscillator-engines.md): how engines are described and dispatched, and how to replace one.
6. [The Release patch](release-patch.md): a complete worked example with every address justified.
7. [Spice and Dice](spice-and-dice.md): how the arp and sequencer randomisers work.
8. [Reverse-engineering setup](reverse-engineering-setup.md): the tools used to produce all of this.
9. [Related projects](related-projects.md): other open-source MicroFreak work.

## Conventions

- **Addresses** are flash addresses of the main image, with its 64-byte header stripped and the payload loaded at `0x0800C000`. `FUN_xxxxxxxx` names a function by its entry address, as Ghidra does.
- A Thumb **function pointer** has bit 0 set (`0x0802B8ED` points at the code at `0x0802B8EC`).
- **Parameter ids** are written `0xGGII`: group `GG`, index `II` (`0x602` is group 6, index 2, the Dec/Rel knob).
- Each fact is marked as **verified** (checked from the bytes, under emulation or on hardware) or **inferred** (a reading of the evidence that wasn't checked directly). Unmarked tables of addresses are verified.
- Everything here was derived from the official firmware alone. Corrections are welcome: say how you checked.
