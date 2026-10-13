# Writing a patch

A ThisFirmwareDoesNotExist patch is a small piece of Thumb code placed inside the stock image, plus a list of stock instructions to redirect into it and a few in-place edits. The `freakpatch` CLI applies it to the user's own firmware. This page walks through the format, the conventions the existing patches follow, and how to get from an idea to a file that's safe to flash. [The Release patch](release-patch.md) is the full worked example.

## Ground rules

1. **Derive everything from the official firmware.** Don't copy or diff other people's modified firmware.
2. **Ship no Arturia bytes.** A patch contains only your code, addresses and short strings you wrote. Users patch their own copy.
3. **Keep the main image at its stock length.** A longer image doesn't boot ([why](free-space-and-dead-code.md#constraint-1-the-image-cant-grow)).
4. **Prove "unreachable" from the raw bytes** with `tests/refscan.py`, never from a disassembler's listing.
5. **Hook the path the hardware actually runs** (see [lessons](#lessons-from-hardware)).

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

- **region:** where your code is written. It must be space you've made unreachable (see [free space](free-space-and-dead-code.md#making-space-retiring-console-commands)), and the code must fit.
- **hooks:** each replaces 4 bytes at `site` with a `bl` or `b.w` to `symbol` in your code. Write down what was there in `was`; it's the first thing a reviewer checks.
- **edits:** a `movw rN, #value` (4 bytes), a 32-bit `word`, a `half` (one 16-bit Thumb instruction), or a NUL-padded `string` of exactly `length` bytes. An edit with `"image": "oled"` targets the OLED chip's image (payload base `0x08000000`) instead of the main image; that image keeps its length and gets a fresh checksum ([example](release-patch.md#separate-decay-and-release-segments-release-matrix)).
- **combine:** a spec can instead be built from other patches, each keeping its own region, with `drop_hooks` and `edits` of its own ([combined builds](matrix-cc.md#combined-builds)). That's how features go into one build, since patched files can't be patched again.
- **options:** a byte in your code the CLI may rewrite (`--release-cc`). Add a CLI flag if you add one.
- Keys the patcher doesn't use (`was`, `description`) are for people.

### What the patcher does

`patcher.apply()`:

1. checks the input's SHA-256 against the official 5.0.0.2084 file (anything else is refused, including patched files, so patches can't be stacked; combine features into one patch instead);
2. writes your code at the region start, then each hook and edit;
3. recomputes the image checksum and rebuilds the ZIP;
4. runs `verify()`: same member list, every image the same length, images the patch doesn't edit untouched, **no byte changed outside the region, hooks and edits**, and every hook decodes to its symbol.

To make a new patch selectable, add its name to `PATCHES` in `src/freakpatch/cli.py`.

## Writing the code

`patches/release.S` shows the conventions:

- **Every stock address is an `.equ` constant** with a comment saying what it is. The object must have no relocations, because `build_patch.py` copies the raw `.text` bytes. Use `ldr rX, =ADDR` (a literal pool, `.ltorg` at the end), never a symbol from another file. Local labels for data in your own code are fine (`adr r3, release_name`).
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

## Building

```sh
uv run python tools/build_patch.py patches/NAME
# src/freakpatch/patches/NAME.json: 412 of 432 bytes, 11 hooks, 6 edits
```

It needs a clang with the ARM target (Apple's clang and upstream LLVM both have it). It refuses relocations, code larger than the region, and hooks or options naming symbols your code doesn't export. `tests/test_build.py` checks that the shipped JSON matches the source.

## Testing

All firmware tests read the user's own official file (set `FREAKPATCH_STOCK_MFF`, or keep MIDI Control Center's copy) and skip without it.

**Static checks** (see `tests/test_release.py`):

- the patched image keeps its stock length, and only declared bytes change;
- each hook site held exactly the stock instruction you expect (`was`);
- `references()` on the stock image finds only the expected ways into your region, and on the patched image only your hooks.

**Emulation** with `tests/emu.py`, a small [Unicorn](https://www.unicorn-engine.org/) harness for single stock functions:

```python
emu = Emu(patched_payload)              # maps flash and RAM, copies .data, runs the parameter constructor
emu.call(0x0802_3C2C, PARAMS, 0x602)    # call a stock function with up to 4 args; returns r0
emu.set_regs(r4=VOICE, ...); emu.run(site, continue_at)   # run a hook site and stop where stock continues
emu.stub(0x0804_4FDC, lambda e: e.set_regs(r0=BUFFER))    # replace a function you don't want to run
```

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
