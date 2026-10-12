# Spice and Dice

Spice and Dice are the arpeggiator and sequencer's randomisers. This page is how they work in stock 5.0.0.2084, read from the firmware.

## In short

- **The randomness is a fixed table, not a dice roll per note.** The firmware keeps three tables of 64 random values. A step counter walks through them as the arp or sequencer plays, so a given Spice setting gives the same variation every time the pattern comes round.
- **Spice is how much of that table you hear.** At 0 nothing changes. As it rises, the table increasingly takes over three things: whether a step plays, how long its gate is, and whether it jumps an octave up or down.
- **You play both from the touch strip** while an arp or sequence is running. Sliding raises or lowers the amount.
- **Dice makes a new table.** It rolls fresh random values and lets you fade from the old table to the new one. When you let go, the table you ended on is kept.
- **The random pattern loops every 16 steps at boot.** The loop length can be changed to anything up to 63 steps; [which setting changes it](#the-step-counter) wasn't pinned down.
- **Spice changes three things: gate length, rests and octave.** It doesn't touch pitch within the octave or velocity. Two more Spice-scaled values go to another part of the firmware each step; where they end up wasn't traced.

## The parameters

| Id | Key / display name | Group | MIDI CC | What it holds |
|---|---|---|---|---|
| `0x0406` | `Spice` / Spice | Arp (4) | **2** | Spice amount, 0–`0x7FFF` |
| `0x0407` | `Dice` / Dice | Arp (4) | none | How far you've faded towards a new roll, while you're doing it |
| `0x1201` | `XiceRst` / XiceRst | Seq (18) | none | When set, the Spice step counter restarts on a new note (see [Restarting the pattern](#restarting-the-pattern)) |

Ids, keys, names and CCs were read from the stock constructor under Unicorn (verified). The parameter listener `FUN_08012C50` turns each value into one byte (value >> 7, so 0–255) and writes it into the Spice engine: Spice to byte `+0x01`, Dice to byte `+0x00` (verified from the code).

## The Spice engine

One object at **`0x20003B00`**, initialised at boot by `FUN_08029AF8` (called from `FUN_0802452C`).

```
+0x000  u8      D    Dice fade amount, 0..255
+0x001  u8      S    Spice amount, 0..255
+0x002  u8[64]       table A, base values          (gate and rests)
+0x042  s8[64]       table A, pending random offsets
+0x082  u8[64]       table B, base values          (octave)
+0x0C2  s8[64]       table B, pending random offsets
+0x102  u8[64]       table C, base values          (octave)
+0x142  s8[64]       table C, pending random offsets
+0x184  u32          random generator state
+0x188  u8           loop length (16 at boot, accepts 1..63)
+0x189  u8           step counter
+0x18A  u8           follow mode (counter copies the sequencer's position while set)
+0x18B  u8           "Dice rolled while Spice was 0" flag
```

### Effective table value

For each table, the value at step *i* is the base plus the pending offset, scaled by the Dice fade:

```
eff(T, i) = base_T[i] + (offset_T[i] * D) >> 8        range about -128..382
```

With no Dice fade in progress (`D = 0`) this is just the base value.

### The random generator

A 32-bit linear congruential generator:

```
state = state * 0x0BB38435 + 0x3619636B      (mod 2^32)
```

At boot the state is set to `0x3619636B`, the same number as the increment. Each roll (`FUN_08029C54(obj, 1)`) runs the generator 32 times, two steps per four table entries. It slices bytes out of each pair of results to fill all three offset tables, then saves the state. A roll therefore continues the sequence rather than reseeding (verified). Nothing found reseeds it, so the run of rolls is probably the same after every power-on (inferred: no other writer of `+0x184` was found, but the listing is incomplete).

### Baking

`FUN_08029C54(obj, 0)` makes the faded table permanent. Each base value becomes `eff(T, i)` folded back into 0..255: below 0 it reflects (`-v`), above 255 it reflects off the top (`510 - v`). Then `D` and the flag are cleared. At boot `FUN_08029AF8` rolls once and bakes at full fade, so the base tables start out as the absolute values of the first roll.

## What Spice does to a step

### The step counter

The step index is the step counter modulo the loop length. Arp and sequencer playback share the counter, which advances once per step (`FUN_080290DC`, `FUN_080292D4`). If `+0x18A` is set, it copies the sequencer's own step position (`FUN_080281F8`) instead of counting by itself. What sets `+0x18A` wasn't found.

The loop length is 16 at boot. The parameter listener `FUN_080135D8` changes it through `FUN_08029FC8`, which ignores values of 64 or more, and passes the same value to the sequencer object (`FUN_08028BA0`). Which parameter that is wasn't identified.

### Gate and rests: `FUN_08029DAC(obj, gate, step)`

`gate` is the step's programmed gate length in percent (0–100). The function crossfades it with table A, by Spice:

```
v = (gate + 50) * (256 - S) / 200  +  (eff(A, step) * S) >> 8
v = fold(v)
```

| `v` | Result |
|---|---|
| 64 or less | **off**: the step doesn't play |
| 65–191 | **on**, gate length `(v - 64) * 0xC800 >> 16` ≈ `(v - 64) × 0.78` % |
| 192 or more | **tie**: gate 100% |

At `S = 0` the first term maps 0–100% to 64–192, and the second term is 0, so the programmed gate comes back unchanged: 0% is off, 100% is a tie, and anything between is itself (verified).

The firmware asks two questions with this function:

| Caller | Asks | With `gate` = |
|---|---|---|
| `FUN_0802906C` | Does this step play? | 50 for an arp step or a sequencer step with a note; 0 for a sequencer rest |
| `FUN_08028F94` | How long is the gate? | The arp gate, or the sequencer step's gate (100 for a tied step) |

So **Spice can both drop notes and add notes on rests**: a rest asks with 0%, and enough Spice from a high table-A value pushes it over the threshold.

### Octave: `FUN_08029F08(obj, step)`

Returns a transposition in semitones, added to the step's note (`FUN_08028EFC` for playback):

```
if S == 0:                        0
A = eff(A, step), B = eff(B, step), C = eff(C, step)
if (A * S) >> 8 > 6 * B:          +12   (octave up)
elif 7 * C < (S * B) >> 8:        -12   (octave down)
else:                             0
```

Higher Spice makes both octave jumps more likely. Which steps jump depends on the tables.

### Two more outputs

`FUN_080290CC` and `FUN_080290D4` turn tables B and C into signed values, each step:

```
out = (S * (eff(T, step) - 128)) >> 8, folded into -127..127
```

`FUN_08029398` writes them into bytes `+0x38` and `+0x39` of another object every step (`FUN_0804DE40`, `FUN_0804DE48`). What reads those bytes wasn't traced.

### Checked under emulation

A Python model of the gate and octave rules above was run against the stock `FUN_08029DAC` and `FUN_08029F08` under Unicorn. It used 400 random cases mixing Spice and Dice amounts, steps, gate lengths and fresh rolls, and matched every one.

## The touch strip

Spice and Dice are played from the **touch strip** while an arp or sequence is running: sliding raises or lowers the Spice or Dice amount (verified on hardware). In the firmware the strip has press, slide and release handlers, and a mode byte at `0x20003706` (the object at `0x20003704`, offset 2) with one LED per mode (`0x110D` + mode).

| Mode | Slide | Press | Release |
|---|---|---|---|
| 0 | **Spice**: sets `0x0406`, sends CC 2 out | – | – |
| 1 | **Dice**: sets `0x0407`, which fades from the current table to the new roll | **Rolls** new offsets (`FUN_0803F254`) | **Bakes** the fade, sets Dice back to 0 (`FUN_0803F278`) |
| 2 (default) | Something else (`FUN_0803EFF0`), not Spice or Dice | – | – |

Handlers: slide `FUN_0803F56C`, press `FUN_0803F254`, release `FUN_0803F278`, reached through thunks at `0x0802E838`–`0x0802E84A`. The mode is switched by `FUN_0803D71C`. `FUN_0803D270` puts it back to mode 2 and sets Spice to 0.

Details worth knowing:

- **Rolling Dice at Spice 0 raises Spice too.** If Spice was 0 when you rolled, sliding in Dice mode also sets Spice to the same value (verified from the code). Presumably that's so a new roll isn't inaudible (inferred).
- **The first slide event after a press is ignored**, so touching to roll doesn't also jump the fade.
- **Spice moves are recorded.** In Spice mode the slide handler stores the value in an 8-entry list at `0x20000C0C`, keyed by parameter id (inferred: the sequencer's motion recording). If MIDI out is enabled, it also sends CC 2 on the configured channel.

## Restarting the pattern

`FUN_08029FA8` resets the step counter to 0 when `XiceRst` (`0x1201`) is non-zero. Its one caller is the note-on path in `FUN_08048524`, so with `XiceRst` set the random pattern restarts from its first step on a new note (inferred from where the call sits).

## Turning a spiced arp into a sequence

`FUN_08029180` renders the current arpeggio into a sequence slot with Spice applied: for each step, the octave jump goes into the note and the gate result goes into the step's gate flag (off, on or tie). `FUN_08043224`, the Shift handler, calls it in arp mode. It then switches the arpeggiator off and the sequencer on. Its argument picks the slot (A or B). Which button combination triggers this wasn't checked on hardware.

## Function index

| Function | Role |
|---|---|
| `FUN_08029AF8` | Boot init: loop length 16, seed, first roll, bake |
| `FUN_08029C54(obj, 1)` | Dice roll: fill the three offset tables from the LCG |
| `FUN_08029C54(obj, 0)` | Bake the faded tables into the base tables |
| `FUN_08029C4C` | Set Spice (`+0x01` = value >> 7) |
| `FUN_08029DA4` | Read the "rolled at Spice 0" flag |
| `FUN_08029DAC` | Gate result for a step: off / on with length / tie |
| `FUN_08029F08` | Octave jump for a step: −12 / 0 / +12 |
| `FUN_080290CC`, `FUN_080290D4` | Signed Spice outputs from tables B and C |
| `FUN_08029FA8` | Restart the pattern if `XiceRst` is set |
| `FUN_08029FC8` | Set loop length (values under 64), called from `FUN_080135D8` |
| `FUN_080290DC`, `FUN_080292D4` | Advance the step counter |
| `FUN_08029180` | Render arp + Spice into a sequence slot |
| `FUN_0803F254` / `FUN_0803F278` / `FUN_0803F56C` | Touch strip press / release / slide |
| `FUN_08012C50` | Parameter listener that feeds Spice and Dice into the engine |
