# Voice modes

`--patch voice-modes` is `release-matrix` plus four parts that work through the Paraphonic button and the cycling envelope:

| Part | Source | What you get |
|---|---|---|
| Delay | `patches/delay_voice.S` | Hold Paraphonic and each note echoes three times on other voices, quieter each time |
| Duo | `patches/duo.S` | Shift + Paraphonic from Unison: two notes, each on a detuned pair of voices |
| Mode notices | `patches/mode_display.S` | A 3 s page naming the mode a Paraphonic gesture turned on or off |
| Cycling-envelope sync | `patches/cyc_sync.S` | Shift + Mode locks Rise and Fall to the tempo, in the LFO's divisions |

The build (SHA-256 `dca1a91348b24165426e8f4088aec6292bd607dc6231c384c9d25df81afa26a5`) was flashed and tested on hardware on 2026-10-17. It's the first build that grows the main image past its stock length, which the bootloader accepts once the image is padded ([why](free-space-and-dead-code.md#constraint-1-the-image-grows-only-in-whole-words)).

This page describes what each part does and how it's built, as a starting point for your own voice modes. Addresses follow the [conventions](README.md#conventions).

## What each part does

### Delay

A note echo in the style of the Minilogue's Delay voice mode. It isn't an audio delay: each echo is a new note-on with its own envelope.

- **Toggle:** hold Paraphonic for 0.5 s or longer with no key down. Turning Delay on also turns Paraphony on; turning it off puts Paraphony back to what it was before the hold. A tap is stock, and a tap that turns Paraphony off also clears Delay. Holding Paraphonic while playing keys is still stock's chord capture.
- **Echoes:** each paraphonic note-on plays the same note again 3 times, at k × D, where D is a dotted 1/8 at the current tempo (375 ms at 120 BPM). Each echo goes to whatever voice the stock allocator gives it, at −4.4, −8.9 and −13.3 dB. An echo lasts as long as the played note, at most D − 10 ms. Echoes of a key that's still held are skipped. Echoes don't go out over MIDI and the arp doesn't see them.
- **Indicator:** the Paraphonic LED stays lit with a 60 ms dark dip every D, timed to land on the last note's echoes.
- **Not in Chord or Unison:** Delay does nothing in those modes, and Duo turns it off.

### Duo

- **Gestures:** Shift + tap Paraphonic cycles Unison → Duo → Unison. From Mono or Paraphony it gives Unison, as stock does. From Duo, a plain tap gives Mono and a hold gives Delay, exactly as from Unison.
- **Sound:** two notes on 2 + 2 voices, each pair detuned by Unison Spread on stock's own curve (0.123 semitone at the Init value, 0.5 at 8192, 1.0 at 16384).
- **Detune editor:** Shift + hold Paraphonic + the Preset encoder is stock's spread editor. In Duo it edits Duo's detune and stays in Duo.
- **LED:** the Paraphonic LED double-pulses (60 ms on, 120 off, 60 on, 760 off) instead of Unison's short blip.
- **Menu:** the Utility menu entry "Unison Spread" reads "Spread/Detune". The spread page's title is drawn by the OLED chip from its own copy of the string, so it still reads "Unison Spread".

### Mode notices

When a Paraphonic gesture changes the voice mode, the screen shows a full page for 3 s, then goes back to the preset page: "Paraphony ON/OFF", "Unison ON/OFF", "Duo ON/OFF", "Delay ON/OFF". The notice names what changed, in this order of priority: Delay, Duo, Unison, Paraphony. So Duo → Unison reads "Unison ON". A tap that doesn't change the mode shows nothing.

### Cycling-envelope sync

- **Toggle:** Shift + Mode. Sync is global, off at power-on, and not saved in presets. Plain Mode still cycles Env → Run → Loop.
- **While synced:** Rise and Fall each pick one of the LFO's 13 divisions (8/1 … 1/32), spread over the knob the way the firmware spreads any 13-step parameter, with the longest at the top as stock's Rise and Fall are. The selected mode's LED blinks, lit for the first half of each beat.
- **Popup:** turning Rise or Fall shows the division ("Rise Time 1/4"), and the curve snaps to the centre of the division's step. Unsynced, the popup is stock's.
- **Tempo:** changing the tempo re-times the envelope. Only the durations are synced. The loop isn't phase-locked to the beat, and Hold's one audio block (0.33 ms) makes a Loop cycle that much longer.

## Layout

All addresses are fixed when the patch is built, so the parts combine without moving each other. The shipped JSON lists them as `parts`:

| Part | Region | Used / room | Free |
|---|---|---|---|
| release | `0x0802BB60` (console handlers, see [free space](free-space-and-dead-code.md#making-space-retiring-console-commands)) | 412 / 432 | 20 |
| matrix-cc | `0x0802CA94` (console `synth`) | 324 / 368 | 44 |
| delay-voice | `0x0807FA60`, appended | 916 / 928 | 12 |
| duo | `0x0802BE90` (console `codec`) | 604 / 674 | 70 |
| mode-display | `0x0807FE00`, appended | 252 / 408 | 156 |
| cyc-sync `.text` | `0x0807FF98`, appended | 80 / 103 | 23 (`0x0807FFE8`–`0x0807FFFE`) |
| cyc-sync `.text.b` | `0x0802C2F4` (console `gpio`) | 196 / 238 | 42 |
| cyc-sync `.text.c` | `0x0802D44C` (console `flag`) | 176 / 228 | 52 |
| cyc-sync `.text.d` | `0x0802BD94` (console `cvout`) | 136 / 252 | 116 |

The voice-mode parts total 2,360 B: the delay's 916 and 1,444 for the other three. The update payload is 475,120 B (main payload 475,119 plus its checksum byte), 16 B under the bootloader's limit of 475,136.

### RAM

The four parts keep their state between the heap and the deepest stack seen in emulation. The heap starts at `0x2001F230` and holds one 88-byte block after boot. The stack grows down from `0x20020000` and was never seen below `0x2001FAE0`.

| Part | Address | Size | Notes |
|---|---|---|---|
| Delay | `0x2001F300` | 424 B | on/off byte (`+0`), press time, LED timer, per-voice attenuation, a 128-bit held-key map, a 48-event echo queue |
| Duo | `0x2001F4B0` | 21 B | `+0` = 1 while Duo is on (the notices read it), saved mode fields, LED state, the mode key at the press |
| Notices | `0x2001F4C9` | 1 B | the notice to draw |
| Cyc-env sync | `0x2001F4D0` | 16 B | sync byte, tempo key, last tick, and a magic word |

None of it is saved: every mode starts off at power-on. Stock never writes any of these bytes (checked in emulation across notes, chords, a preset change, the arp and every Paraphonic gesture). USB interrupts weren't modelled, so the real stack may reach deeper. About 1.5 KB separates the deepest stack seen from this state, and no hardware session has shown a problem.

### Hooks and chains

Three sites are shared, and each is chained: the outermost part's wrapper calls the part it replaced, through a `next` word that the build fills in.

| Site | What it is | Chain (outermost first) |
|---|---|---|
| `0x080433F0` | Paraphonic press: `b.w` to the Paraphonic handler `0x0803CA5C` | Duo `duo_btn` → Delay `para_btn` → stock |
| `0x0803F1E2` | Paraphonic release: the same `b.w` | Duo `duo_btn` → Delay `para_btn` → stock |
| `0x0803A824` | Main-loop poll: `bl 0x08039DA4` | cyc-env `sync_tick` → Duo `duo_tick` → Delay `echo_tick` → stock |

Each part's other hooks are its own:

| Part | Hooks | Edits |
|---|---|---|
| Delay | `bl echo_on` / `echo_off` at the paraphonic note-on and note-off calls of the voice allocator (`0x0804866E`, `0x080493CC`); `bl voice_level` at the 9 envelope-level reads in the voice mix (`0x0803751C`, `0x0803755A`, `0x0803763C`, `0x0803767C`, `0x08037AEA`, `0x08037AF8`, `0x08037B3E`, `0x08037B4A`, `0x08037B6E`) | |
| Duo | | `codec` vtable word `0x08074094` → stock's `bx lr`; the menu string at `0x0807624C` |
| Notices | `b.w popup_text` over the `bne.w` at `0x08052F1C`, in the display manager's case for request `0x700`; a `word` hook fills Duo's `notice_fn` (`0x0802BE98`) with `notice` | |
| Cyc-env sync | `b.w ui_event` at the UI event entry `0x080219D4` (it replays the two instructions it covers); chained `bl` at each call of the cycling envelope's Rise, Decay and Fall setters (`0x080125A4`, `0x08012656`, `0x0801265E`, `0x0801522C`, `0x08015284`, and the tail call `b.w` at `0x08015290`); chained `bl` at the popup's two value reads (`0x0804F5AC`, `0x0804F5DC`) and its value text (`0x0804F6D4`) | vtable words `0x08073FF4`, `0x080740B4`, `0x08074134` → stock's `bx lr` |

Duo also calls two of the delay's routines by address, `delay_off` (`0x0807FB0A`) and `led_set` (`0x0807FB42`). Its spec lists them under `imports`, and the build checks that the delay put them there.

## How each part works

### Delay: echoes through the stock allocator

The delay doesn't make sound itself. It schedules extra note-ons and lets the synth play them.

- **Queue:** the note-on wrapper calls the stock allocator, marks the key held, and queues 3 echo note-on/note-off pairs. A pair is queued whole or not at all. The first hardware build queued the halves separately, and a fast keyboard sweep filled the queue with note-ons whose note-offs didn't fit, leaving notes stuck.
- **Scheduler:** once per millisecond, from the main-loop poll, due events go into the voice allocator `FUN_0804DA80`, the same entry a played note uses. Notes reach voices the normal way, so every engine, the filter and the VCA treat an echo like a played note.
- **Level:** velocity doesn't change a voice's level on this synth (emulation: the same RMS at velocity 127, 90, 50 and 20). The voice mix scales each voice by its amp envelope every audio block, reading it through one getter `FUN_0800DCC8` at 9 sites. Hooking those reads and scaling by a per-voice attenuation gives the fall-off on every engine. The voice index comes from the envelope's address (each voice's state is `0x59E4` bytes apart from `0x200089C0`).
- **Tempo:** u16 BPM × 100 at `0x20003EEC`, so D = 4,500,000 / tempo ms.
- **LED:** the Paraphonic LED is driven by a 6-byte event the main CPU queues to the matrix chip (`FUN_08021414` on the I/O link object `0x200005A0`). The LED is on/off only and the chip applies changes about 10 ms apart, so a dip is the only pattern that reads well.
- **No popup:** a "Delay ON/OFF" text drawn straight onto the text widget stayed on screen on hardware. The mode notices below use the display manager instead.

### Duo: stock's own Unison and Chord, recombined

Duo adds no voice or pitch code. It puts stock's machinery into a combination stock never selects:

- **Params:** Duo sits on Unison's params (`0x700` Paraphony and `0x707` Chord both `0x7FFF`). Stock then keeps computing the spread unit from Unison Spread (`0x705`) and adds +d / −d to the voices of each note itself. It does that only while `0x707` is Unison, which is why Duo lives there.
- **Mode fields:** the note handler decides how many notes and voices to play from eight mode bytes: `0x20004384` (+0, +0x4A, +0x4B) and `0x20003778` (+0x2E5, +0x2E6, +0x2E7, +0x2E9, +0x2EA). Writing `04 01 02 02 02 02 00 7F` there (a Chord of 2 notes at interval 0, duplicates allowed) makes C4 + E4 play C4 C4 E4 E4. The bytes' individual meanings are inferred, not traced: this combination was found by probing.
- **Keeping it:** the main-loop poll keeps Duo only while Unison holds. It rewrites the fields if stock rewrote them, and holds Unison's LED blink off (byte `+0x39` of the Paraphonic object `0x20003714`). Entering Duo saves stock's fields and turns Delay off; leaving writes them back and reruns stock's own mode set-up (`FUN_08049E2C`, then `FUN_08049A98`).
- **Button:** `duo_btn` wraps the Paraphonic handler. On a Shift press from Unison it runs stock's press; on the release, if the spread didn't change, it turns Duo on. In Duo it repeats stock's Shift press without the switch to Unison, so the spread editor opens and edits Duo's detune.

### Mode notices: the display manager's unused request

- **Request `0x700`:** the display manager (object `0x20000A10`, request struct `0x20000A14`) has a case for "show param `0x700`" that draws a full Paraphony page, but stock never posts it. `notice` posts it with `FUN_080558C0(0x20000A14, 0x700)`, and `popup_text` replaces the case's text with the notice. The manager then draws the page, times it out (the patch sets 3000 ms; stock popups use 5000) and returns to the preset page by itself.
- **Draw only inside the manager's case.** Drawing on the text widget from anywhere else leaves an overlay the manager never clears. That was the delay's stuck popup on hardware.
- **One string per notice.** Each text call to the OLED carries 4 bytes, so sending "Delay\n" and "ON" separately showed junk between them. The notice is built in a 16-byte stack buffer: the patch's own name, then stock's "ON" / "OFF" (the tails of its Paraphony strings at `0x08075710` and `0x08075720`).
- **Who decides:** Duo's wrapper is the only Paraphonic wrapper. It takes a mode key at the press and again after the release (Paraphony, Unison, Delay, Duo) and calls `notice(new key, changed bits)` through `notice_fn` when they differ. A build without the notices leaves `notice_fn` at 0.

### Cycling-envelope sync: wrap the rate setters, not the params

The cycling envelope turns Rise, Decay and Fall into per-block phase rates with three setters: `0x0800DD90`, `0x0800DDA8` and `0x0800DDC0`.

- **Rate formula:** each setter writes rate = K / (v³ / 2³⁰ + 1), where v is the knob value and K depends on the audio block rate. Every audio block adds the rate to a 24-bit phase, and a segment ends when the phase overflows, so it lasts ceil(2²⁴ / rate) blocks.
- **Who calls them:** the envelope's update calls them only when a value changes, and so does the engine-rate set-up (which runs when the block rate changes: 3000 blocks/s, or 2667 when the engine runs at 32 kHz).
- **Synced rate:** while synced, the wrapper on each call replaces the rate with (K >> 8) × tempo / (q24 × 3200), rounded up, where q24 is the division in 24ths of a quarter note. That's 2²⁴ / (division in seconds × blocks per second), so it's exact at either block rate.
- **What stays stock:** parameters, presets and the knob display are untouched, so turning sync off restores stock's times with nothing to undo.
- **Re-applying:** a toggle or a tempo change doesn't change a knob, so the update wouldn't call the setters. The main-loop poll calls the wrapped setters itself with the current Rise and Fall.
- **Mode LED:** the selected mode's LED is a grid LED (column 6, rows 4–6 for Env/Run/Loop), driven with `F7 10 col row` frames on the I/O link. The poll blinks it from the tempo clock (`0x20003EA0`, 480 ticks per quarter note).
- **Popup:** the cycling-envelope popup `FUN_0804F5A0` reads Rise and Fall through the value getter `FUN_0804ED7C` for its curve, and formats the value text with `FUN_0804E404`. Wrapping those three calls gives the synced popup. The division names are stock's own LFO labels (the table at `0x08062378`), read by pointer.

## Making a new voice mode

What these four parts suggest, in the order to try:

1. **Recombine stock's state before writing new code.** Duo is 604 bytes because it writes eight bytes stock already understands. The voice-mode params (`0x700`, `0x707`), the eight mode fields and the Paraphonic object's flags cover Mono, Paraphony, Chord, Unison and anything in between. Probe combinations in emulation and listen before reaching for the allocator or the pitch code.
2. **Feed the allocator rather than the voices.** A new note behaviour (echoes, strums, ratchets, a second note per key) can schedule note-ons into `FUN_0804DA80` from the main-loop poll, as the delay does. The synth's own voice management, envelopes and engines then work unchanged.
3. **Shape level at the voice mix.** The 9 envelope-level reads in the voice mix are the one place every engine's per-voice level passes through. Velocity won't do it.
4. **Put the gesture on the Paraphonic button's wrapper.** The press and release sites are already chained, and Duo's wrapper computes the mode key. Add your mode as a new key bit, and the notices can name it with one more string.
5. **Show state through the display manager**, never by drawing directly. Post a request the manager owns and replace that case's text.
6. **Keep new state out of presets unless you need it.** Every mode here is off at power-on and saves nothing, which keeps the patch away from the [flash writers](flash-writes.md) and means a stock preset always sounds the same.

For a timing feature like cyc-env sync, wrap the function that turns a parameter into an internal rate, not the parameter itself. The knob, the display and presets then stay stock, and switching the feature off restores stock behaviour without restoring anything.

## Building parts in series

The four parts were developed one at a time, each over the build before it. The patch format supports that directly ([writing a patch](writing-a-patch.md#several-regions-appending-and-chains)):

- **Agree addresses up front.** Each part's regions and RAM range were fixed before any of them was written (the tables above), so building them in any order never moved another part's code.
- **Chain at shared sites.** A later part's hook at a shared site declares `next`, the word that receives the site's current target. The build fills it in and drops the earlier hook, so stock is still called at the end of the chain.
- **Share small interfaces.** Parts talk through a byte in RAM (Delay's on byte at `0x2001F300`, Duo's at `0x2001F4B0`) or a word in code (`notice_fn`), never through each other's internals.
- **Combine in the spec.** `patches/voice-modes.hooks.json` is `"combine": ["release-matrix", "delay-voice", "duo", "mode-display", "cyc-sync"]`. A combined spec can include another combined spec.

## Space

The voice modes fill the flash after the stock image and four console handlers, so space is the constraint for anything new. What a size pass over these parts found:

**Done, 212 B saved** (1,656 → 1,444 B over Duo, the notices and cyc-env sync, with nothing observable changed in emulation: audio sample-identical, the same screens, LED frames and state after every gesture):

| Change | Saved |
|---|---|
| Direct `bl` / `b.w` to fixed addresses (`call` / `jump` in `series.inc`) instead of `ldr r12, =F; blx r12` and small trampolines | 88 B |
| One Paraphonic wrapper (Duo's) instead of one per part; the notices are called from it | 40 B |
| Duo reuses the delay's `led_set` instead of its own | 28 B |
| Duo's 8 mode-field addresses as one base plus 8 halfword offsets, read, written and compared by one loop | 36 B |
| Cyc-env's division lookup and sync test fused into one routine | 20 B |

**Not done** (estimates, each touching code that's already been on hardware):

| Change | Estimate |
|---|---|
| One main-loop dispatcher instead of three chained wrappers | 20–30 B |
| One LED pattern engine: Duo's double pulse as a table entry in the delay's dip timer | 25–35 B |
| Release's two identical 26-byte bodies merged, with two 4-byte entries | 15–25 B |
| One grid-LED frame helper shared by matrix-cc and cyc-env | 15–20 B |
| Direct calls in Release, Matrix CC and Delay, as done for the others (Release alone has 9 `ldr pc` jumps) | about 100 B |

**Layout:** moving cyc-env's `.text` from `0x0807FF98` down to `0x0807FF00` would join the tail's two free gaps into about 176 B at the end and shorten the update file. It would change the file's hash, so it waits for the next hardware round.

**Tips:**

- **Literals cost twice.** Every `ldr rX, =ADDR` is a 4-byte pool entry plus the load. Direct calls and shared base registers remove most of them.
- **One wrapper per site.** Each chained wrapper pushes, pops and re-reads the same params. When several features want the same site, let one wrapper serve them and call the others.
- **Reuse what's there.** Stock's strings ("ON", "OFF", the LFO's division names) and another part's helpers are a pointer away.
- **Not candidates:** the delay's voice-index loop (its 9 sites can't pass the voice), Matrix CC's 35-byte CC table, and the notices' strings, which already reuse stock's.
- **Stock dead code is nearly exhausted.** A scan counting every reference form (including `cbz`/`cbnz` and `tbb`/`tbh`, whose absence made live code look dead) found, beyond the console handlers, only `FUN_0802EE74` (178 B, reached only from the console handler Release retired) and a few 1–12 byte scraps. More room has to come from smaller patches.

## Hardware

- **Delay**, first flash (2026-10-15, over `release-matrix` 0.2.0): worked, with the stuck popup and the stuck notes after a fast sweep described above. Both were fixed before the voice-modes build.
- **Voice modes**, `dca1a913…` (2026-10-17): flashed and tested. The run before it showed "Paraphony OFF" when a plain tap left Unison or Duo, which is why the notices now name what changed.

Test plan for a build that changes any of this (Init preset):

1. **Base unchanged:** a tap gives Paraphony with a solid LED. Release, the Decay/Release curve and the matrix LEDs work as in `release-matrix`.
2. **Delay:** a 1 s hold gives "Delay ON" and the dipping LED; a staccato note gives 3 quieter repeats. Sweep the keyboard fast, up and down: nothing keeps sounding.
3. **Notices:** each gesture shows its page for about 3 s, then the preset page. Nothing stays on screen. Other popups (knobs, LFO Sync) still last 5 s.
4. **Duo:** Shift + tap twice gives "Duo ON" and the double pulse; C4 + E4 give two beating pairs. Shift + hold + Preset changes the detune and stays in Duo. A plain tap gives Mono; a hold gives Delay.
5. **Cyc-env sync:** Loop, Env → Cutoff, Shift + Mode. The Loop LED blinks on the beat, Rise and Fall jump between note lengths, and the loop follows the tempo. Shift + Mode again: solid LED, stock times.
6. **Stress:** switch presets while in Duo and while synced; leave the arp running for a few minutes.

## Known limitations and open questions

- **Delay:** a repeated note's echo retriggers the voice its previous echo is on, cutting that tail, because the allocator gives a note back the slot that last held it. Division (dotted 1/8), repeats (3) and fall-off are constants. Delay can't echo Chord, Unison or Duo notes, which go through other allocator calls.
- **Duo:** survives a preset change to another Unison preset; isn't saved. The spread page's title still reads "Unison Spread" (it would need an OLED image edit).
- **Cyc-env sync:** Hold isn't synced; the loop isn't phase-locked to the beat; following an external MIDI clock is untested (it reads the internal tempo word).
- **Notices:** no notice for toggling cyc-env sync.
