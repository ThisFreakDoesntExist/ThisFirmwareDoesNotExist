@ Tempo-synced cycling envelope (docs/voice-modes.md, cyc-sync.hooks.json). Part of the voice-modes build.
@
@ Shift + Mode toggles sync (stock treats it as a plain Mode press; with Shift held the press is swallowed). Plain
@ Mode still cycles Env -> Run -> Loop. While synced, Rise and Fall lock to the LFO's 13 divisions (8/1 .. 1/32, its
@ label table 0x08062378), spread over each knob as the firmware spreads a 13-step param (FUN_0800E644: index =
@ min(v * 13 >> 15, 12)), longest at the top like stock's Rise/Fall; and the selected mode's LED blinks, lit for the
@ first half of each beat of the tempo clock. Sync is global, not saved, off at power-on. Each toggle shows
@ "Cyc-Env Sync ON/OFF" through the voice-mode displays (mode_display.S), which the base must carry.
@
@ How: the cycling envelope (object 0x2001AFDC, envelope 0x2001B138) turns Rise/Fall into per-block phase rates with
@ three setters, rate = K / (v^3 / 2^30 + 1), K = 2^40 / (20 * blocks per second) at env + 0x40: 0x0800DD90 rise
@ (env + 0x14), 0x0800DDA8 decay (+ 0x18), 0x0800DDC0 fall / release (+ 0x1C). A segment ends when the 24-bit phase
@ overflows (and restarts at 0), so it lasts ceil(2^24 / rate) blocks. Synced, each setter's rate is replaced by
@     rate = ceil((K >> 8) * tempo / (q24 * 3200))  tempo = BPM x 100 (0x20003EEC), q24 = division in 1/24 quarters
@ which is 2^24 / (division in seconds * blocks per second), whatever the block rate (3000/s, 2667/s at 32 kHz).
@ The params and the knob display are untouched. The update FUN_08012514 only calls the setters when a value changes,
@ so on a toggle or a tempo change while synced the main-loop poll calls the three (wrapped) setters itself with the
@ envelope's current Rise / Fall values, as the update would.
@
@ Hooks (chain = a hook with a next word, which tools/build_patch.py fills with the site's current target):
@   ui_event   b     0x080219D4  UI event entry (its first two instructions are re-run): Shift + Mode
@   rise_set   chain 0x080125A4, 0x0801522C        bl 0x0800DD90 (update, engine-rate set-up)
@   decay_set  chain 0x08012656, 0x08015284        bl 0x0800DDA8
@   fall_set   chain 0x0801265E; chainb 0x08015290 bl / b.w 0x0800DDC0
@   sync_tick  chain 0x0803A824  main-loop poll (after whatever patch holds it; r0 passed on)
@   graph_value chain 0x0804F5AC, 0x0804F5DC       popup FUN_0804F5A0's graph reads of Rise / Fall (FUN_0804ED7C)
@   value_text chain 0x0804F6D4  its value text (FUN_0804E404)
@
@ RAM: STATE 0x2001F4D0 - 0x2001F4EF (32 B). Stock never writes it; it is initialised on the first poll after a
@ reset (magic word, and the HAL tick going backwards).

        .syntax unified
        .thumb
#include "series.inc"

        .equ STATE,          0x2001F4D0
        .equ S_SYNC,         0x00            @ u8  1 = synced
        .equ S_EAT,          0x01            @ u8  1 = a Shift + Mode press was swallowed: swallow its release too
        .equ S_ROW,          0x02            @ u8  LED row of the selected mode last seen (4 Env, 5 Run, 6 Loop)
        .equ S_LIT,          0x03            @ u8  1 = that LED is lit (as stock or we last drew it)
        .equ S_KEY,          0x04            @ u16 tempo while synced, 0 while not: a change re-applies Rise/Fall
        .equ S_LAST,         0x08            @ u32 HAL tick at the last poll
        .equ S_MAGIC,        0x0C            @ u32 MAGIC once initialised
        .equ MAGIC,          0xC7C5E7C0

        .equ SHIFT,          0x2000456C      @ u8 Shift held
        .equ TEMPO,          0x20003EEC      @ u16 BPM x 100
        .equ CLOCK_TICKS,    0x20003EA0      @ u32 tempo-clock ticks, 480 per quarter (clock object 0x20003CDC + 0x1C4)
        .equ UWTICK,         0x2001E1D8      @ HAL tick, ms
        .equ MODE,           0x2001DA7A      @ s16 cycling-env Mode param (0x200): 0 Env, 16384 Run, 32767 Loop
        .equ CYC,            0x2001AFDC      @ cycling envelope's update object: +8 Rise, +0xC Fall (s16)
        .equ ENV,            0x15C           @ CYC + ENV: the envelope the setters take
        .equ IO_LINK,        0x200005A0      @ I/O-link sender object
        .equ IO_SEND,        0x08021415      @ (obj, word0, word1, 1): queue a 6-byte frame
        .equ LED_HEAD,       0x10F7          @ F7 10: panel LED
        .equ LED_COL,        6
        .equ LED_ON,         0xFF7F
        .equ UI_REST,        0x080219D9      @ FUN_080219D4 after its first two instructions
        .equ STEPS,          13              @ the LFO's divisions
        .equ DIRECTION,      1               @ 1: knob up = longer division (as stock Rise/Fall); 0: as the LFO Rate
        .equ VALUE_TEXT,     1               @ synced Rise/Fall popup value: 1 the division ("1/8T"), 0 stock's time
        .equ LFO_LABELS,     0x08062378      @ the LFO's division names, 8/1 first
        .equ GET_VALUE,      0x0804ED7D      @ FUN_0804ED7C(id) -> u16 param value
        .equ POST_NOTICE,    0x0807FE00      @ mode_display.S: post_notice(r2 = notice)
        .equ RISE_ID,        0x201
        .equ FALL_ID,        0x203

@ ---------------------------------------------------------------------------------------------------------------
@ Tail (0x0807FF98, moved from 0x0807FF80 to give the displays room): the UI event entry.
        .text
        .balign 4

@ FUN_080219D4(ui, event): event = 20 01|02 02 00 00 01 is a Mode press | release.
        .global ui_event
        .thumb_func
ui_event:
        ldr     r2, [r1]
        bic     r2, r2, #0xFF00         @ 20 .. 02 00
        movw    r3, #0x0020
        movt    r3, #0x0002
        cmp     r2, r3
        bne     ui_stock
        ldrh    r2, [r1, #4]
        cmp     r2, #0x0100             @ 00 01: extra 1
        bne     ui_stock
        ldr     r3, =STATE
        ldrb    r2, [r1, #1]
        cmp     r2, #1
        bne     2f
        ldr     r2, =SHIFT              @ press
        ldrb    r2, [r2]
        cbz     r2, ui_stock
        b.w     toggle
2:      ldrb    r2, [r3, #S_EAT]        @ release
        cbz     r2, ui_stock
        movs    r2, #0
        strb    r2, [r3, #S_EAT]
        bx      lr
ui_stock:
        push    {r4, r5, lr}
        mov     r4, r1
        jump    UI_REST

        .ltorg

@ ---------------------------------------------------------------------------------------------------------------
@ gpio console handler (0x0802C2F4): the main-loop poll.
        .section .text.b, "ax", %progbits
        .balign 4
tick_next:   .word 0

@ Main-loop poll: re-apply Rise/Fall when sync or the synced tempo changes; blink the selected mode's LED.
@ The first poll after a reset re-applies too (stock's rates, sync off), so a stray sync byte can't stick.
        .global sync_tick
        .thumb_func
sync_tick:
        push    {r0, r4, r5, r6, r7, lr}
        ldr     r4, =STATE
        ldr     r0, =UWTICK
        ldr     r0, [r0]
        ldr     r1, [r4, #S_LAST]
        str     r0, [r4, #S_LAST]
        ldr     r2, [r4, #S_MAGIC]
        ldr     r3, =MAGIC
        cmp     r2, r3
        bne     1f
        cmp     r0, r1
        bhs     2f
1:      str     r3, [r4, #S_MAGIC]      @ first poll after a reset: sync off, re-apply stock's rates
        movs    r2, #0
        str     r2, [r4, #S_SYNC]       @ S_SYNC, S_EAT, S_ROW, S_LIT
        movw    r2, #0xFFFF
        strh    r2, [r4, #S_KEY]
2:      ldrb    r5, [r4, #S_SYNC]
        movs    r1, #0
        cbz     r5, 3f
        ldr     r1, =TEMPO
        ldrh    r1, [r1]
3:      ldrh    r2, [r4, #S_KEY]
        cmp     r1, r2
        beq     4f
        strh    r1, [r4, #S_KEY]
        bl      reapply
4:      ldr     r0, =MODE               @ row = 4 + min(mode * 3 >> 15, 2)
        ldrsh   r0, [r0]
        usat    r0, #15, r0
        add     r0, r0, r0, lsl #1
        lsrs    r0, r0, #15
        cmp     r0, #2
        it      hi
        movhi   r0, #2
        adds    r6, r0, #4
        ldrb    r1, [r4, #S_ROW]
        cmp     r1, r6
        beq     5f
        strb    r6, [r4, #S_ROW]        @ a new mode: stock has just drawn its LED lit
        movs    r1, #1
        strb    r1, [r4, #S_LIT]
5:      movs    r7, #1
        cbz     r5, 6f
        ldr     r0, =CLOCK_TICKS        @ synced: lit for the first half of each beat
        ldr     r0, [r0]
        movs    r1, #240
        udiv    r0, r0, r1
        and     r0, r0, #1
        eor     r7, r0, #1
6:      ldrb    r1, [r4, #S_LIT]
        cmp     r1, r7
        beq     8f
        strb    r7, [r4, #S_LIT]
        movw    r1, #LED_HEAD
        movt    r1, #LED_COL
        orr     r1, r1, r6, lsl #24     @ F7 10 06 row
        movw    r2, #LED_ON
        negs    r3, r7
        ands    r2, r3
        ldr     r0, =IO_LINK
        movs    r3, #1
        call    IO_SEND
8:      pop     {r0, r4, r5, r6, r7, lr}
        ldr     r12, tick_next
        bx      r12

        .ltorg

@ ---------------------------------------------------------------------------------------------------------------
@ flag console handler (0x0802D44C): the setter wrappers and the synced rate.
        .section .text.c, "ax", %progbits
        .balign 4
rise_next:   .word 0
decay_next:  .word 0
fall_next:   .word 0

@ Re-apply Rise and Fall through the wrappers, as the update FUN_08012514 does when they change.
        .thumb_func
reapply:
        push    {r4, lr}
        ldr     r4, =CYC
        add     r0, r4, #ENV
        ldrsh   r1, [r4, #8]
        bl      rise_set
        add     r0, r4, #ENV
        ldrsh   r1, [r4, #0xC]
        bl      decay_set
        add     r0, r4, #ENV
        ldrsh   r1, [r4, #0xC]
        pop     {r4, lr}
        b       fall_set

@ Setter wrappers: (env, v) -> stock's setter, then the synced rate over its field.
        .global rise_set, decay_set, fall_set
        .thumb_func
rise_set:
        ldr     r3, rise_next
        movs    r2, #0x14
        b       set_common
        .thumb_func
decay_set:
        ldr     r3, decay_next
        movs    r2, #0x18
        b       set_common
        .thumb_func
fall_set:
        ldr     r3, fall_next
        movs    r2, #0x1C
set_common:
        push    {r0, r1, r2, lr}
        blx     r3
        pop     {r0, r1, r2, lr}

@ r0 = env, r1 = knob value, r2 = rate field. Writes the synced rate if sync is on. Integers only (the setters'
@ callers may hold floats in s registers).
        .global synced_rate
        .thumb_func
synced_rate:
        push    {r0, r2, r4, lr}
        mov     r0, r1
        bl      synced_step             @ the knob's step, as FUN_0800E644 spreads a 13-step param
        cbz     r3, 8f
.if DIRECTION == 0
        rsb     r0, r0, #STEPS - 1
.endif
        adr     r3, q24
        ldrh    r1, [r3, r0, lsl #1]
        pop     {r0, r2}
        movw    r3, #3200
        muls    r1, r3                  @ q24 * 3200
        ldr     r3, [r0, #0x40]
        lsrs    r3, r3, #8              @ K >> 8 = 2^32 / (20 * blocks per second)
        ldr     r4, =TEMPO
        ldrh    r4, [r4]
        muls    r3, r4                  @ < 2^32 up to 534 BPM at 2667 blocks/s
        subs    r4, r1, #1
        add     r3, r4
        udiv    r3, r3, r1              @ rounded up: a segment of a whole number of blocks lasts exactly that
        cmp     r3, #1
        it      lo
        movlo   r3, #1
        str     r3, [r0, r2]
        pop     {r4, pc}
8:      pop     {r0, r2, r4, pc}

@ Divisions in 1/24 quarter, shortest first: 1/32 1/16T 1/16 1/8T 1/8 1/4T 1/4 1/2T 1/2 1/1 2/1 4/1 8/1.
        .balign 2
q24:    .hword  3, 4, 6, 8, 12, 16, 24, 32, 48, 96, 192, 384, 768

        .ltorg

@ ---------------------------------------------------------------------------------------------------------------
@ cvout console handler (0x0802BD94): the popup while synced. The cycling-env popup FUN_0804F5A0 reads the graph's
@ bytes with FUN_0804ED7C(id) (Rise 0x201 at 0x0804F5AC, Fall 0x203 at 0x0804F5DC; the OLED draws the high bytes)
@ and formats the value text with FUN_0804E404(buf, id) at 0x0804F6D4. Synced, the graph gets the centre of the
@ value's step (so the shape jumps between 13 positions) and the text the division's name from the LFO's table.
@ The label ("Rise Time" / "Fall Time") stays stock's.
        .section .text.d, "ax", %progbits
        .balign 4
graph_next:  .word 0
text_next:   .word 0

@ Shift + Mode press (r3 = STATE): flip sync, swallow the release, show "Cyc-Env Sync ON/OFF" through the displays'
@ post_notice (mode_display.S: name N_CYC = 4, N_ON = 8).
        .thumb_func
toggle:
        ldrb    r2, [r3, #S_SYNC]
        eor     r2, r2, #1
        strb    r2, [r3, #S_SYNC]
        movs    r1, #1
        strb    r1, [r3, #S_EAT]
        lsls    r2, r2, #3
        adds    r2, #4
        jump    POST_NOTICE

@ synced_step: r0 = v -> synced: r3 != 0 and r0 = v's step; not synced: r3 = 0, r0 unchanged.
@ step_of: r0 = v (0 .. 32767) -> r0 = its step, min(v * 13 >> 15, 12). Both clobber r1.
        .thumb_func
synced_step:
        ldr     r3, =STATE
        ldrb    r3, [r3, #S_SYNC]
        cbz     r3, 9f
        .thumb_func
step_of:
        usat    r0, #15, r0
        movs    r1, #STEPS
        muls    r0, r1
        lsrs    r0, r0, #15
        cmp     r0, #STEPS - 1
        it      hi
        movhi   r0, #STEPS - 1
9:      bx      lr

@ bl FUN_0804ED7C(id) in the popup: synced, the value becomes its step's centre, (2 * step + 1) * 32768 / 26.
        .global graph_value
        .thumb_func
graph_value:
        push    {r4, lr}
        ldr     r12, graph_next
        blx     r12
        bl      synced_step
        cbz     r3, 1f
        lsls    r0, r0, #1
        adds    r0, #1
        lsls    r0, r0, #15
        movs    r1, #2 * STEPS
        udiv    r0, r0, r1
1:      pop     {r4, pc}

@ bl FUN_0804E404(buf, id) in the popup: synced Rise / Fall get the division's name.
        .global value_text
        .thumb_func
value_text:
.if VALUE_TEXT
        ldr     r3, =STATE
        ldrb    r3, [r3, #S_SYNC]
        cbz     r3, 8f
        uxth    r2, r1
        movw    r3, #RISE_ID
        cmp     r2, r3
        beq     1f
        adds    r3, #FALL_ID - RISE_ID
        cmp     r2, r3
        bne     8f
1:      push    {r0, lr}
        mov     r0, r2
        call    GET_VALUE
        bl      step_of
.if DIRECTION
        rsb     r0, r0, #STEPS - 1      @ the LFO's table runs 8/1 .. 1/32
.endif
        ldr     r1, =LFO_LABELS
        ldr     r1, [r1, r0, lsl #2]
        pop     {r0, lr}
2:      ldrb    r2, [r1], #1
        strb    r2, [r0], #1
        cmp     r2, #0
        bne     2b
        bx      lr
.endif
8:      ldr     r12, text_next
        bx      r12

        .ltorg
