# Writing a patch

A ThisFirmwareDoesNotExist patch is a small piece of Thumb code placed in space it frees inside the stock image or appends after it, plus a list of stock instructions to redirect into it and a few in-place edits. The `freakpatch` CLI applies it to the user's own firmware. This page walks through the format, the conventions the existing patches follow, and how to get from an idea to a file that's safe to flash. [The Release patch](release-patch.md) is the full worked example.

## Ground rules

1. **Derive everything from the official firmware.** Don't copy or diff other people's modified firmware.
2. **Ship no Arturia bytes.** A patch contains only your code, addresses and short strings you wrote. Users patch their own copy.
3. **Grow the main image only through appended parts**, which the patcher pads to a length the bootloader accepts. An unpadded longer image doesn't boot ([why](free-space-and-dead-code.md#constraint-1-the-image-grows-only-in-whole-words)).
4. **Prove "unreachable" from the raw bytes** with `tests/refscan.py`, never from a disassembler's listing.
5. **Hook the path the hardware actually runs** (see [lessons](#lessons-from-hardware)).
6. **Never write flash.** Don't call, hook or edit the firmware's flash writers, and persist new state through the stock preset saver. [Flash writes](flash-writes.md) lists them and how to check.

## Anatomy

| File | Role |
|---|---|
| `patches/NAME.S` | Your code, in GNU assembler syntax for Thumb-2 |
| `patches/NAME.hooks.json` | Where it goes: the code region, the hook sites, the edits, options |
| `src/freakpatch/patches/NAME.json` | Built by `tools/build_patch.py`: the spec plus your code bytes and symbol offsets. This is what ships. |

### The spec

```json
{
  "name": "release",
  "description": "One line shown by `freakpatch --list`.",
  "region": {"start": "0x0802BB60", "end": "0x0802BD10", "was": "what used to be here"},
  "hooks": [
    {"site": "0x0801103C", "kind": "bl",  "symbol": "reg_group",  "was": "bl 0x0800E730"},
    {"site": "0x08034194", "kind": "b.w", "symbol": "diff_check", "was": "ldrsh r2,[r4,r2]; ldrsh r3,[r4,r3]"}
  ],
  "edits": [
    {"site": "0x08034A3C", "kind": "movw",   "reg": 1, "value": "0x1400"},
    {"site": "0x08074054", "kind": "word",   "value": "0x0802B8ED"},
    {"site": "0x0806298C", "kind": "string", "text": "Decay", "length": 8}
  ],
  "options": {"release_cc": {"symbol": "release_cc", "default": 72}}
}
```

- **region:** where your code is written. It must be space you've made unreachable (see [free space](free-space-and-dead-code.md#making-space-retiring-console-commands)) or start at or after `0x0807FA60` (appended), and the code must fit. A source with several sections uses `sections` instead ([below](#several-regions-appending-and-chains)).
- **hooks:** each replaces 4 bytes at `site` with a `bl` or `b.w` to `symbol` in your code. Write down what was there in `was`; it's the first thing a reviewer checks. A hook with `next` chains to the site's previous target, and a `word` hook points a word at your symbol ([below](#several-regions-appending-and-chains)).
- **edits:** a `movw rN, #value` (4 bytes), a 32-bit `word`, a `half` (one 16-bit Thumb instruction), or a NUL-padded `string` of exactly `length` bytes. An edit with `"image": "oled"` targets the OLED chip's image (payload base `0x08000000`) instead of the main image; that image keeps its length and gets a fresh checksum ([example](release-patch.md#separate-decay-and-release-segments-release-matrix)).
- **combine:** a spec can instead be built from other patches, each keeping its own region, with `drop_hooks` and `edits` of its own ([combined builds](matrix-cc.md#combined-builds)). That's how features go into one build, since patched files can't be patched again. A combined spec can name another combined spec: `voice-modes` starts from `release-matrix`.
- **options:** a byte in your code the CLI may rewrite (`--release-cc`). Add a CLI flag if you add one.
- Keys the patcher doesn't use (`was`, `description`) are for people.

### What the patcher does

`patcher.apply()`:

1. checks the input's SHA-256 against the official 5.0.0.2084 file (anything else is refused, including patched files, so patches can't be stacked; combine features into one patch instead);
2. if any part is appended, grows the main image to hold it: zero up to `0x0807FA60`, `0xFF` after, and `0xFF` padding to a multiple of 16 bytes;
3. writes your code at each region's start, then each hook and edit;
4. recomputes the image checksum and rebuilds the ZIP;
5. runs `verify()`: same member list, every image the same length (the main image grown by exactly the appended code, fill and padding), images the patch doesn't edit untouched, **no byte changed outside the regions, hooks and edits**, and every hook decodes to its symbol.

To make a new patch selectable, add its name to `PATCHES` in `src/freakpatch/cli.py`.

## Writing the code

`patches/release.S` shows the conventions:

- **Every stock address is an `.equ` constant** with a comment saying what it is. Use `ldr rX, =ADDR` (a literal pool, `.ltorg` at the end), or `call ADDR` / `jump ADDR` from `patches/series.inc` for a direct `bl` / `b.w`. Never use a symbol from another file. Local labels for data in your own code are fine (`adr r3, release_name`, or `.word label`, which the build resolves).
- **Thumb pointers have bit 0 set.** `.equ REGISTER, 0x0800E7B5` is the function at `0x0800E7B4`.
- **Returning into stock code:** `ldr pc, =CONTINUE` (with bit 0 set) or `ldr r12, =FUNC; bx r12` for a tail call. `r12` is free to clobber at a call boundary; elsewhere, check.
- **Exported symbols** (`.global name` + `.thumb_func`) are what hooks and options name.

### Kinds of hook

| Situation | Hook | Your code must |
|---|---|---|
| Replace or wrap a call (`bl FUNC`) | `bl` at the call site | behave like `FUNC`: preserve callee-saved registers, return to `lr`, and usually tail-call `FUNC` itself |
| Divert in the middle of a function | `b.w` over one 32-bit or two 16-bit instructions | **replay the instructions you overwrote**, keep every register the following code reads, and jump back to the next instruction |
| Change a constant | `movw` edit | nothing; no code needed |
| Re-point a table entry | `word` edit | nothing |

Rules for `b.w` sites, all learned the hard way:

- The 4 bytes you overwrite must not be **the target of any branch** (check the second halfword with `references()`), and must not be inside an `IT` block.
- Replay displaced instructions exactly, including their flag effects, and say so in a comment (`format_release` replays `sub sp,#8; mov r5,r1; mov r6,r0`).
- Write down which registers are live at the site and which your code clobbers, as `release.S` does for each hook.

## Several regions, appending and chains

A feature bigger than one free region, or one built on top of another patch, uses the rest of the format. [Voice modes](voice-modes.md) uses all of it; `patches/cyc-sync.hooks.json` is the fullest example.

### Sections at fixed addresses

Put each piece of code in its own section (`.section .text.b, "ax", %progbits`) and give each one a place:

```json
"sections": {
  ".text":   {"start": "0x0807FF98", "end": "0x0807FFFF", "was": "appended"},
  ".text.b": {"start": "0x0802C2F4", "end": "0x0802C3E2", "was": "console 'gpio' handler"}
}
```

Each section ships as its own part. Code in one section can call another's labels (`bl synced_step`), and data can hold their addresses (`.word str_unison`): the build resolves those relocations for the addresses above. Fix the addresses before writing the code, and write them down. Then parts developed separately can't move each other.

### Direct calls

`bl 0x0803B814` can't be written in LLVM's assembler: it won't branch to an absolute `.equ`. `patches/series.inc` provides two macros:

```asm
#include "series.inc"
        .equ GET_PARAM, 0x0803B815
        call    GET_PARAM               @ bl 0x0803B814
        jump    CASE_TAIL               @ b.w, a tail call or a return into stock
```

Each is 4 bytes, with no literal and no scratch register. `ldr r12, =F; blx r12` costs 8 bytes plus a 4-byte literal. Across the voice-mode parts this saved 88 bytes.

### Appending

A region starting at or after `0x0807FA60` is appended past the stock image ([the rules](free-space-and-dead-code.md#constraint-1-the-image-grows-only-in-whole-words)). Appended code needs no retired handler, but the whole area is 1,440 bytes, and the bigger the image, the longer the update takes. Before using it:

1. Flash a build with your appended code and **no hooks** first, as with any new region. The patcher pads it, so it should boot.
2. Leave the last byte, `0x0807FFFF`, free: the checksum byte goes there.

### Chained hooks

Two patches that want the same call site can both have it. The later one declares `next`, a word in its code, and the stock `target`:

```json
{"site": "0x0803A824", "kind": "bl", "symbol": "duo_tick", "next": "tick_next", "target": "0x08039DA4"}
```

The build stores the site's current target in `next` (with the Thumb bit set): the stock target, or, in a combined build, the part that hooked the site before. It also drops that part's hook. Your wrapper does its work and calls (or tail-calls) the word, passing the registers the site passed:

```asm
tick_next:  .word 0                     @ filled by the build
duo_tick:   push    {r0, r1, r2, r3, r4, lr}    @ the site's arguments, and an even count keeps sp 8-aligned
            bl      sync                @ Duo's poll
            pop     {r0, r1, r2, r3, r4, lr}
            ldr     r12, tick_next
            bx      r12                 @ the delay's echo_tick, which ends in stock's poll
```

For a `b.w` site (a tail call in stock), the wrapper is entered with stock's arguments and no return address of its own, so it must end by jumping to `next`, or by calling it and then returning to stock's caller.

### Word hooks and imports

- A hook with `"kind": "word"` points a 32-bit word at your symbol. If the word is inside another part's code, the build fills it in there. That's how the mode notices give Duo their `notice` routine through Duo's `notice_fn` word. Anywhere else it ships as a `word` edit, as for a vtable.
- `"imports": {"delay_off": "0x0807FB0A"}` records that your code calls another part's routine at a fixed address. The combined build fails if that part doesn't put it there.

### Order

In a combined spec, parts are built in the order listed, and each chains to the ones before it. List the innermost first: `voice-modes` is `release-matrix`, then `delay-voice`, `duo`, `mode-display`, `cyc-sync`. Changing the order changes which wrapper runs first, not any address.

## Building

```sh
uv run python tools/build_patch.py patches/NAME
# src/freakpatch/patches/NAME.json: release: 412 of 432 bytes
# 11 hooks, 6 edits
```

It needs a clang with the ARM target (Apple's clang and upstream LLVM both have it). It refuses relocations it can't resolve, code larger than its region, sections without an address, and hooks or options naming symbols your code doesn't export. `tests/test_build.py` checks that the shipped JSON matches the source.

## Testing

All firmware tests read the user's own official file (set `FREAKPATCH_STOCK_MFF`, or keep MIDI Control Center's copy) and skip without it.

**Static checks** (see `tests/test_release.py`):

- the patched image keeps its stock length (or grows only by appended code and padding), and only declared bytes change;
- each chained site's stock instruction branches to its declared `target`, and each `next` word holds the part it wraps (`tests/test_voice_modes.py`);
- each hook site held exactly the stock instruction you expect (`was`);
- `references()` on the stock image finds only the expected ways into your region, and on the patched image only your hooks.

**Emulation** with `tests/emu.py`, a small [Unicorn](https://www.unicorn-engine.org/) harness for single stock functions:

```python
emu = Emu(patched_payload)              # maps flash and RAM, copies .data, runs the parameter constructor
emu.call(0x0802_3C2C, PARAMS, 0x602)    # call a stock function with up to 4 args; returns r0
emu.set_regs(r4=VOICE, ...); emu.run(site, continue_at)   # run a hook site and stop where stock continues
emu.stub(0x0804_4FDC, lambda e: e.set_regs(r0=BUFFER))    # replace a function you don't want to run
```

Also check that the patch causes no flash writes stock wouldn't ([how](flash-writes.md#checking-under-emulation)).

The most useful test shape runs the same site on the stock and patched image and compares every register: identical for inputs your patch shouldn't affect, and the intended difference for inputs it should. Then drive the **real entry point** a user's action reaches (the knob handler, the preset parser) end to end.

## Test on hardware in steps

Each failed flash costs a recovery (hold **Shift + Arp + Oct** at power-on, then update from the official file), so check placement before behaviour:

| Step | Build | Changes | Expect |
|---|---|---|---|
| 1 | region only | the space retired and your code written, **no hooks** | boots and plays exactly like stock |
| 2 | one hook | step 1 plus one hook that does exactly what stock did | boots and plays exactly like stock |
| 3 | the feature | everything | your checklist |

If step 1 hangs, the same-length rewrite or the checksum is wrong, not your logic. If step 2 hangs, hooking into the region is the problem. The `diag-region` and `diag-hook` patches are these two steps for the console `synth` region; copy them for a new region.

Write the step 3 checklist before flashing. The Release patch's:

1. A stock preset sounds the same before and after patching.
2. Turning Decay changes only the decay; the release tail stays put.
3. Shift + Decay changes the release tail, in mono, paraphonic and unison modes.
4. CC 72 changes Release. Turning Shift + Decay sends CC 72.
5. Save a preset after changing Release, switch away and back: Release is restored.
6. A preset saved with the patch loads on stock firmware. MIDI Control Center can back up and restore it.
7. Flashing the official file restores stock.

A MIDI monitor is the cheapest hardware debugger: the synth sends a CC for every mapped parameter it changes, so you can see which parameter a knob really drove.

## Lessons from hardware

Two features passed every test and still didn't work on the synth, because the hook was in code the hardware didn't run:

- **Knobs.** The firmware has separate handlers for absolute knob positions (pots) and relative moves (encoders), each with its own copy of the Shift rule. Only the encoder one was hooked. A MIDI monitor showed the knob still sending the old CC while Shift was held, which pointed straight at it.
- **Screen.** The popup's parameter switch exists twice: in a dispatcher function, and inlined in the screen's main update loop, which calls the dispatcher only on its first pass. Only the dispatcher was hooked.

Before trusting a hook, find **every copy** of the logic you're changing (search for the same constants and compare sequences) and confirm which one a real button press or screen update reaches. The tests now drive the real stock knob handler end to end for this reason.

Other things that held up well:

- **Reuse stock machinery.** Registering Release as a real parameter made presets, MIDI in and out, the knob code and the value formatter work with no extra code. Look for a generic mechanism before writing a special case.
- **Make the old behaviour the default.** With Release equal to Decay the output is identical to stock, so old presets sound unchanged.
- **Stay compatible both ways.** Stock firmware skips unknown preset groups, so presets saved with the patch still load on stock.
