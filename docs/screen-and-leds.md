# The screen and LEDs

How the main CPU gets something onto the OLED and the matrix LEDs, and what the shipped patches change there. The detail behind each claim is in [the Release patch](release-patch.md#screen) and [the mod matrix over MIDI CC](matrix-cc.md#why-incoming-ccs-dont-light-the-matrix); this page is the map.

## Provenance

Derived from Arturia's stock MicroFreak firmware 5.0.0.2084 only, with the tools in [Reverse-engineering setup](reverse-engineering-setup.md), Unicorn runs of stock functions, and a whole-firmware emulator (local, not published). No Arturia code is reproduced here: only addresses, message layouts and what the code does. Main-image addresses follow the [conventions](README.md#conventions). OLED-image addresses use that image's payload base, `0x08000000`.

## Who draws what

The main CPU doesn't drive the display or the LEDs itself. It sends messages to separate I/O chips, each with its own firmware image in the update file ([update file format](update-file-format.md#the-io-chip-images)).

| Output | Drawn by | Fed by |
|---|---|---|
| OLED: popups, values, names, the envelope curve | the OLED I/O chip (image 1) | the UI listener and UI tick on the main CPU |
| Mod-matrix LEDs | the matrix I/O chip, from its LED scan buffer | the matrix controller on the main CPU |

Both are fed through the same queued sender, **`FUN_08021414`**, on the I/O link object `0x200005A0` (verified). Stock MIDI code calls it too (`0x080472AE`, `0x0804756E`).

## How a change reaches the display

A stored value doesn't redraw anything by itself. What gets redrawn depends on the path the change took (verified, under emulation and on hardware):

| Path | What runs | Display |
|---|---|---|
| Panel knob, encoder or matrix screen | the handler sets the value, then `0x0803AE30(obj, id)` broadcasts a change to the six listeners at `obj+0x10…+0x24` | the UI listener `0x20000A10` (handler `0x0804ED94` → `FUN_080558C0`) records the id; the UI tick opens its popup |
| Incoming MIDI CC | stored through `0x0803F2C4` or `0x08023C9C`, then the plain setter `0x08023C40` | nothing: the setter notifies only groups whose notify bit (`obj+0x274 + group*2`) is set, and only group 0 has one |
| Preset load | the parser, then the broadcast `FUN_080543E0` | the listeners see every parameter |

So an incoming CC changes the sound (the voices read stored values directly) but opens no popup and lights no LED. Stock behaves this way for every parameter, not just patched ones.

## The OLED

### Popups

- The UI tick **`FUN_08052B84`**, run from the main loop, turns the last touched id into a popup.
- **Its id switch exists twice** (verified on hardware): in the dispatcher `FUN_080519EC`, which the tick calls only on its first run, and inlined in the tick (`movw r3,#0x503` at `0x08052BAE`), which runs from then on. A hook on only one copy never fires after boot. The Release patch hooks both.
- Values are formatted by **`FUN_0804E404(buf, id)`**; unknown ids print as plain numbers.
- Display names are copied from flash strings at boot, so a rename is a same-length string edit (`"Dec/Rel"` → `"Decay"` at `0x0806298C`).

### The envelope curve

- The envelope popup **`FUN_0804F7AC`** reads four values with the raw getter `FUN_0804ED7C`, sends their top bytes as one 4-byte message (`FUN_080557E8` → `FUN_08021414`), then command `0x12`/`0x2000` (verified).

  | Slot | Stock | `release` | `release-matrix` |
  |---|---|---|---|
  | 1 | Attack `0x601` | same | same |
  | 2 | Dec/Rel `0x602` | Release `0x1400` while its popup is open (`curve_time`) | Decay `0x602` |
  | 3 | Sustain `0x603` | same | same |
  | 4 | Filter Amt `0x605`, ignored by the OLED chip | same | Release `0x1400` |

- **The OLED chip draws the curve** in `FUN_080082D4(a, d, s, f)`: widths `a/4`, then `d/4` for both the decay and the release segment, height from `s`. Stock never reads `f` (verified under emulation).
- `release-matrix` patches two halfwords in that function so the release segment uses `f/4`: see [Separate decay and release segments](release-patch.md#separate-decay-and-release-segments-release-matrix). The main-image and OLED edits must ship together: with only the main edit, the stock OLED ignores slot 4 and the Release popup stops redrawing the curve.

## The matrix LEDs

- The LEDs belong to the **matrix controller** `0x200035A4`, ticked by `0x0803AFB0` from the main loop (`0x08024F42`). It redraws them from the stored amounts (verified):
  - a sweep over all 35 cells (counter `+0x44`, about one cell every 3 ms, started by `0x0803B728` or `0x0803B2D8`), sent from `0x0803B00A`;
  - the blinking cursor cell (`+6`/`+7`).
- Each LED is one 6-byte frame, built by `0x08021AB0` and queued with `FUN_08021414(0x200005A0, bytes 0–3, bytes 4–5, 1)`:

  | Amount | Frame |
  |---|---|
  | ≠ 0 | `F7 10 col row 7F FF` (three 5-bit levels at 31) |
  | 0, or LED mode `+4` ≠ 1 | `F7 10 col row 00 00` |

  col = source 0–4, row = destination 0–6.
- The panel path also broadcasts the change, which opens the "Matrix Amount" popup. Broadcasting to light an LED from MIDI therefore brings the popup with it, which stock never shows for an incoming CC.
- `matrix-cc` (and `release-matrix`) sends the one frame for the cell an incoming CC changed, only when it turns on or off, and nothing to the screen: see [the LED refresh](matrix-cc.md#the-led-refresh). It runs in the main loop just before the matrix tick, so it can't interleave with the controller's own frames. Tested on hardware: [LED refresh on hardware](matrix-cc.md#led-refresh-on-hardware).

## Writing your own

- To show a new parameter, follow it through all three: the listener (it records any id), **both** copies of the popup switch, and the formatter. The [Release patch](release-patch.md#screen) is the worked example.
- To light something without a popup, send the frame the owning controller would send, through `FUN_08021414`, from the main loop.
- Anything drawn on the OLED chip itself (curves, layout) needs an OLED-image edit (`"image": "oled"`, see [Writing a patch](writing-a-patch.md#the-spec)).

## Open questions

- What the rest of the OLED image does: only the envelope renderer `FUN_080082D4` has been mapped.
- The command set of the display link beyond popups and command `0x12`.
- Whether frames to the matrix chip can drive LED levels other than 0 and 31 (the frame carries three 5-bit levels).
- **Hardware:** the `release-matrix` curve edits have run only under emulation. A build that includes them (SHA-256 `303bed10…`) was flashed for the [LED test](matrix-cc.md#led-refresh-on-hardware), but what its envelope curve showed wasn't recorded, nor whether the update re-flashed the OLED chip.
