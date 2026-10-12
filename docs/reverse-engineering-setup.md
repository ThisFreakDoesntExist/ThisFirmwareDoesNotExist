# Reverse-engineering setup

Everything in these docs came from three tools: headless Ghidra with the scripts in [`tools/ghidra/`](../tools/ghidra/), the raw-byte reference scanner [`tests/refscan.py`](../tests/refscan.py), and the Unicorn harness [`tests/emu.py`](../tests/emu.py).

## Get the main image

```sh
python3 -I tools/ghidra/extract_main.py microfreak_Firmware_Update_5.0.0.2084.mff main500.bin
```

It prints `info.json` and each image's size and checksum bytes, and writes the main image's payload (header and trailing checksum byte stripped) to `main500.bin`. Load it at `0x0800C000`. Keep firmware files and Ghidra projects out of the repository; `.gitignore` already excludes `*.mff` and `*.bin`.

## Ghidra (headless)

Tested with Ghidra 12.1.4 and OpenJDK 21. Two things stop it before analysis starts:

- **It needs to find Java.** Headless mode can't ask which JDK to use, so without one it stops with `Unable to prompt user for JDK path, no TTY detected`. Homebrew installs OpenJDK 21 without linking it into macOS's Java lookup, so point `JAVA_HOME` at it: `export JAVA_HOME="$(brew --prefix)/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"`.
- **No dot-directories in the project path.** Ghidra refuses any project path with a dot-directory in it (`Path element starting with '.' is not permitted`). That includes `~/.cache/...` and git worktrees under `.claude/worktrees/`, so keep the project in a plain path such as `/tmp/mf-proj`.

```sh
GHIDRA=/path/to/ghidra   # e.g. $(brew --prefix ghidra)/libexec on macOS with Homebrew
H="$GHIDRA/support/analyzeHeadless"

# 1. Import and analyse: Cortex-M, raw binary at the load base
GHIDRA_HEADLESS_MAXMEM=6G "$H" /tmp/mf-proj mf \
  -import main500.bin -loader BinaryLoader -loader-baseAddr 0x0800C000 \
  -processor ARM:LE:32:Cortex -cspec default \
  -scriptPath tools/ghidra -preScript MfSetup.java -postScript MfExport.java /tmp/mf-out

# 2. Seed functions reached only through vtables, re-analyse, export again
"$H" /tmp/mf-proj mf -process main500.bin -scriptPath tools/ghidra \
  -preScript MfSeed.java -postScript MfExport.java /tmp/mf-out

# 3. Ask questions, read-only: decompile, cross-references, strings, disassembly
"$H" /tmp/mf-proj mf -process main500.bin -noanalysis -readOnly -scriptPath tools/ghidra \
  -postScript MfQuery.java out.txt dec:0x0802F3BC xref:0x40015C04 'str:Sample.Rate' dis:0x0802FEA0:30

# 4. Decompile every function into one file, then search it
"$H" /tmp/mf-proj mf -process main500.bin -noanalysis -readOnly -scriptPath tools/ghidra \
  -postScript MfDecompileAll.java all.c
```

| Script | Purpose |
|---|---|
| `MfSetup.java` | Adds SRAM (`0x20000000`, 128 KB), CCM, peripheral and system-control blocks so register references resolve, and creates functions from the vector table |
| `MfSeed.java` | Creates a function at every flash word that is a Thumb pointer to a `push` prologue. This finds vtable-only methods such as the oscillator engines' render functions, which the default analysis misses; it raises the function count from 1,162 to 1,247. |
| `MfExport.java` | Writes `functions.tsv` (entry, size, caller count, name) and `strings.tsv` (address, text, cross-references) |
| `MfQuery.java` | `dec:ADDR`, `xref:ADDR`, `str:REGEX`, `dis:ADDR:N`; creates the function first if needed |
| `MfDecompileAll.java` | Decompiles all 1,247 functions into one text file (about 2.3 MB, a few minutes), each headed `######## <entry> <name>` |

**Searching the decompiled code is usually the fastest way in.** Grep `all.c` for a parameter id, a RAM address or a constant, then map each hit back to the nearest `########` line above it. To find code that passes a parameter id, match it as a function argument (`grep -nE '[(,] ?0x406[,)]' all.c`), since a bare `0x406` also matches unrelated struct offsets. Code that reaches a parameter through its value table by offset doesn't show up this way. To find that code, search for the global object it uses (see [Spice and Dice](spice-and-dice.md#how-this-was-found) for a worked example).

`str:` only finds strings Ghidra defined, and it misses some short ones (`"Dice"` among them). When a name doesn't show up, search the raw image bytes.

After seeding, about 297 KB of the 474 KB image lies inside functions; the rest is mostly tables, strings and float constants. **The listing is still incomplete**: 184 functions have no direct callers, and real callers exist in code Ghidra never decoded. Treat "no references" in Ghidra as a hint, never as proof.

## Raw-byte reference scan

```python
from refscan import references  # run from tests/, or put tests/ on sys.path

references(payload, 0x0800C000, lo, hi)  # [(source address, form), ...]
```

It decodes every halfword as every Thumb form that carries a target, and every halfword-aligned word as a pointer, so an empty result proves nothing refers into `[lo, hi)`. See [free space and dead code](free-space-and-dead-code.md#proving-code-is-unreachable-testsrefscanpy) for how to read its hits.

## Running stock code under emulation

`tests/emu.py` maps flash and RAM in [Unicorn](https://www.unicorn-engine.org/), copies `.data` the way the reset handler does, and (by default) runs the parameter constructor, so the parameter object is set up as on the synth. From there you can call any stock function, run from one address to another, stub out functions, and read or write memory. It doesn't model peripherals, interrupts or the I/O chips, so it suits single functions; a question about the whole system (which code path a knob turn takes, what goes to the display chip) needs a bigger emulator or the hardware.

## Other useful checks

| Check | How |
|---|---|
| Image checksums | XOR of `data[0x40:]` per image, compared with header byte 1 and the last byte (`extract_main.py` prints both) |
| Floating-point code density | Count Thumb-2 coprocessor-10/11 encodings (`hw1 & 0xEC00 == 0xEC00` and `(hw2 >> 9) & 7 == 0b101`). A heuristic: it over-counts data. |
| Which parameter a knob drives | Watch the synth's MIDI output with any MIDI monitor while turning it |
