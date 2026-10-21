# The `.mff` update file

`src/freakpatch/mff.py` implements everything on this page.

## Container

An `.mff` is a standard ZIP whose members are all **stored** (not compressed). It holds `info.json` and five images:

```json
{ "version_number": "5.0.0.2084", "date": "2023_05_30",
  "images": [
    {"image_num": 4, "file_name": "userwavetable_factory_v1_3__20211015.bin"},
    {"image_num": 2, "file_name": "nanowave_iochip_matrix__fw1_0_0_1857__2023_05_29.bin"},
    {"image_num": 3, "file_name": "nanowave_iochip_kbd__fw1_0_1_1857__2023_05_29.bin"},
    {"image_num": 0, "file_name": "nanowave_main__fw5_0_0_2084__2023_05_30.bin"},
    {"image_num": 1, "file_name": "nanowave_iochip_oled__fw1_0_0_1905__2023_05_29.bin"} ] }
```

"Nanowave" appears to be the product's internal codename.

| Image | # | 5.0.0.2084 size | 4.0.1.1376 size | Notes |
|---|---|---|---|---|
| Main CPU | 0 | 473,760 | 449,936 | Everything this project patches |
| OLED I/O chip | 1 | 81,712 | 80,624 | Drives the display, including the envelope curve |
| Matrix (panel) I/O chip | 2 | 29,744 | 29,744 | Byte-identical between the two releases apart from its name |
| Keyboard I/O chip | 3 | 26,928 | 27,104 | |
| Factory user wavetables | 4 | 327,744 | 327,744 | Identical between the two releases |

The whole 5.0.0.2084 file is 941,572 bytes. Because members are stored and Arturia never re-zips a released file, every member sits at a fixed offset; the main image's data starts at file offset `0x05DED0`. A tool can therefore patch raw offsets in the whole `.mff`, as long as it also fixes the CRCs (below).

## Image header and checksum

Every image starts with a 64-byte header:

| Offset | Meaning |
|---|---|
| 0 | `image_num` (`0x81` for the wavetable image; the others use their plain number) |
| 1 | Checksum: XOR-8 of the payload |
| 2–63 | Zero in the code images. The wavetable image stores two words here (below). |

- **Code images** (main, OLED, matrix, keyboard): the payload is followed by one trailing byte, a copy of header byte 1. So every byte from `0x40` to the end, trailing byte included, XORs to zero. (Verified on all ten images of 4.0.1 and 5.0.0.)
- **Wavetable image:** no trailing copy. Header byte 1 is the XOR of all 327,680 body bytes.

| Image | 5.0.0 checksum | 4.0.1 checksum |
|---|---|---|
| main | `0xD2` | `0xD4` |
| OLED | `0xCA` | `0x8D` |
| matrix | `0xD0` | `0xD0` |
| keyboard | `0x95` | `0x72` |
| wavetables | `0x79` | `0x79` |

There is **no signature or cryptographic MAC**. MIDI Control Center accepts a modified main image as long as:

1. the new checksum is written to both header byte 1 and the trailing byte, and
2. the member's ZIP CRC-32 is right, in both the local header (file offset `0x05DE95` for the main image) and the central directory (`0x0E5D0E`).

`freakpatch` re-zips with `ZIP_STORED`, keeping member order, names, timestamps and attributes, which takes care of both CRCs.

## Rebuilding a valid `.mff`

1. Read the main image, strip the 64-byte header and the trailing byte, and patch the payload.
2. Recompute the XOR-8 and write it into header byte 1 and the trailing byte.
3. Either rewrite the two CRC-32 fields in place (keeps every offset stable) or re-zip with `ZIP_STORED`.
4. Keep `info.json` and every file name unchanged.
5. **Keep the main image's length a multiple of 16 bytes**, header and checksum byte included, and its payload ending by `0x08080000`. Stock already is; an image that grows must be padded ([why](free-space-and-dead-code.md#constraint-1-the-image-grows-only-in-whole-words)). The other images keep their stock length.

## Recovery

The bootloader lives in the 48 KB of flash below `0x0800C000` and isn't part of the update file, so a bad main image can't break it. Holding **Shift + Arp + Oct** at power-on enters update mode, and MIDI Control Center can then flash the official file. (Verified: this is how every failed test flash during development was recovered.)

## The wavetable image

`userwavetable_factory_v1_3__20211015.bin` is the same file in 4.0.1 and 5.0.0. It holds the factory contents of the 16 **user wavetable** slots, which MIDI Control Center can replace without any firmware change.

```
header  (64 B)  81 79 00 00 | 00 F0 F5 00 | 00 00 05 00 | 00 …
                num  xor       0x00F5F000    0x00050000
body    (0x50000 B = 327,680)
  0x00000–0x0FFFF  16 metadata pages × 4 KB (padding is erased flash, 0xFF)
  0x10000–0x4FFFF  16 tables × 16 KB  (32 cycles × 256 samples × int16 LE)
```

- The two header words are most likely the destination address and length in the 16 MB external QUADSPI flash. (Inferred: it fits the main firmware's QUADSPI driver, but the updater side wasn't traced.)
- Each metadata page starts with the `u32` slot index, followed by two identical name records `{u16 index, u8 1, u8 1, char name[24]}`; the rest is `0xFF`.

| Slot | Name | Slot | Name |
|---|---|---|---|
| 0 | Convergence | 8 | Shrrom |
| 1 | Funky Bell | 9 | Nache |
| 2 | Pluck Additive | 10 | My DM |
| 3 | Pluck Odd | 11 | SawQ |
| 4 | Pluck Resonant | 12 | Potion |
| 5 | Iris | 13 | Subt |
| 6 | FM Triangle | 14 | Little Monster |
| 7 | Mellovox | 15 | Sine Bells |

Older 3.x firmware used a different wavetable image (no metadata pages, a different header); [mf-utils](related-projects.md#mf-utils) documents that version.

## The I/O chip images

The OLED, matrix and keyboard images are code for separate Cortex-M0 microcontrollers that talk to the main CPU over serial links (inferred from the main CPU's USART handlers). They use the same header and checksum rule as the main image. They haven't been mapped here, apart from the OLED chip's envelope curve renderer, which the `release-matrix` build patches (payload base `0x08000000`, see [release-patch.md](release-patch.md#separate-decay-and-release-segments-release-matrix)). What the main CPU sends to the OLED and matrix chips is mapped in [The screen and LEDs](screen-and-leds.md).
