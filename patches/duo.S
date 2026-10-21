@ Duo voice mode (Minilogue): 2 notes x 2 voices, each pair detuned by Unison Spread (docs/voice-modes.md,
@ duo.hooks.json). Part of the voice-modes build, over the delay voice.
@
@ Gestures (user's design): Shift + tap Paraphonic cycles Unison -> Duo -> Unison; from Mono / Paraphony it gives
@ Unison (stock). A plain tap leaves either (stock), a plain hold is Delay (the base). Shift + hold Paraphonic + the
@ Preset encoder is stock's Spread editor (0x705); in Duo it edits the detune and stays in Duo. A Shift press whose
@ hold changed 0x705 doesn't cycle (Unison stays Unison, Duo stays Duo).
@
@ Duo sits on stock's Unison params (0x700 = 0x7FFF, 0x707 = 0x7FFF): a plain tap or hold then does what it does from
@ Unison, and stock keeps computing the spread unit from 0x705 (FUN_08013C08 does so only in Unison) and adds +d / -d
@ to the two voices of each note itself. Over that the note handler's 8 mode fields are set to a Chord of 2 at
@ interval 0 (04 01 02 02 02 02 00 7F), so stock's handler plays two notes on 2 + 2 voices. Leaving puts stock's
@ bytes back and runs stock's own voice-mode set-up from the params.
@
@ LED: while Duo is on, the Paraphonic LED double-pulses (60 on, 120 off, 60 on, 760 off); stock's Unison blink is
@ held off through its enable byte (Paraphonic object +0x39) and given back when Duo returns to Unison.
@
@ Hooks (chained: tools/build_patch.py fills each next word with the site's current target):
@   duo_btn   b.w at 0x080433F0 (press) and 0x0803F1E2 (release), wrapping the delay voice's para_btn
@   duo_tick  bl  at 0x0803A824, the main-loop poll (the delay voice's echo_tick is there)
@
@ Mode notices: duo_btn is the only Paraphonic wrapper. It takes the mode key at the press and again after the
@ release (and Duo's own sync); if it changed it tail-calls notice_fn(new key, changed bits), which the displays
@ patch (mode_display.S) fills. notice_fn sits at a fixed place, the section's third word (0x0802BE98); 0 = none.
@
@ RAM: STATE 21 bytes at 0x2001F4B0; S_DUO (+0) is the interface the displays patch reads.

        .syntax unified
        .thumb
#include "series.inc"
        .text

        .equ STATE,          0x2001F4B0
        .equ S_DUO,          0x00            @ u8  1 while Duo is on (interface)
        .equ S_XF,           0x01            @ u8  Duo's fields are applied
        .equ S_PRESS,        0x02            @ u8  press: key & 3 for a Shift press (3 = from Unison), P_DUO from
                                             @     Duo, 0 a plain press
        .equ S_PHASE,        0x03            @ u8  LED phase 0..3
        .equ S_SPREAD,       0x04            @ u16 0x705 at the Shift press
        .equ S_NEXT,         0x08            @ u32 next LED change, ms
        .equ S_SAVE,         0x0C            @ u8 x 8: stock's fields before Duo
        .equ S_KEY,          0x14            @ u8  mode key at the press
        .equ P_DUO,          4
        .equ F_READ,         0               @ fields() ops
        .equ F_WRITE,        1
        .equ F_MATCH,        2

        .equ K_PARA,         1               @ mode key bits (mode_key), shared with mode_display.S
        .equ K_UNISON,       2
        .equ K_DELAY,        4
        .equ K_DUO,          8

        .equ UNISON,         0x7FFF          @ 0x707 value for Unison (also 0x700 on)
        .equ PARA_OBJ,       0x20003714      @ Paraphonic handler object: +8 -> Shift byte, +0x39 Unison blink on,
                                             @ +0x60 press handled, +0x61 Spread editor on
        .equ VOICES,         0x20004384
        .equ HANDLER,        0x20003778
        .equ DISPLAY,        0x20000A14
        .equ DELAY_ON,       0x2001F300      @ the delay voice's S_ON
        .equ PARA_VOICES,    0x2001B210

        .equ GET_PARAM,      0x0803B815
        .equ GET_TICK,       0x08055ED9
        .equ SPREAD_PAGE,    0x08055BFD      @ FUN_08055BFC(DISPLAY): post screen 0x15 (stock's Shift press does)
        .equ DELAY_OFF,      0x0807FB0B      @ the delay voice's delay_off (no arguments)
        .equ APPLY_MODE,     0x08049E2D      @ FUN_08049E2C(HANDLER, mode)
        .equ SET_VOICES,     0x08049A99      @ FUN_08049A98(HANDLER, n)
        .equ LED_SET,        0x0807FB43      @ the delay voice's led_set(on): Paraphonic LED on if r0 != 0

        .balign 4
btn_next:   .word 0                          @ filled by the build: the sites' current target
tick_next:  .word 0
notice_fn:  .word 0                          @ filled by mode-display's word hook: notice(key, changed), 0 = none

@ ---------------------------------------------------------------------------------------------------------------
@ Paraphonic button, r0 = this (PARA_OBJ), r1 = 1 press / 0 release.
        .global duo_btn
        .thumb_func
duo_btn:
        push    {r4, r5, r6, lr}
        mov     r4, r0
        mov     r5, r1
        ldr     r6, =STATE
        cbz     r5, 5f
        bl      mode_key                @ press: the mode before anything acts on it
        strb    r0, [r6, #S_KEY]
        and     r5, r0, #3              @ 3: Unison, Paraphony on
        ldr     r2, [r4, #8]            @ stock's own Shift test (FUN_0803B77C == 1)
        ldrb    r2, [r2]
        cmp     r2, #1
        beq     1f
        movs    r5, #0                  @ a plain press
        b       3f
1:      movw    r0, #0x705
        call    GET_PARAM
        strh    r0, [r6, #S_SPREAD]
        ldrb    r0, [r6, #S_DUO]
        cbz     r0, 3f
        movs    r0, #P_DUO              @ Shift press in Duo: stock's, without the switch to Unison
        strb    r0, [r6, #S_PRESS]
        ldr     r0, =DISPLAY
        call    SPREAD_PAGE
        movs    r0, #1
        strb    r0, [r4, #0x60]
        strb    r0, [r4, #0x61]
        b       8f
3:      strb    r5, [r6, #S_PRESS]
        mov     r0, r4
        movs    r1, #1
        ldr     r12, btn_next
        blx     r12
8:      bl      sync
        pop     {r4, r5, r6, pc}
5:      mov     r0, r4                  @ release: the delay's and stock's first
        movs    r1, #0
        ldr     r12, btn_next
        blx     r12
        ldrb    r5, [r6, #S_PRESS]
        movs    r0, #0
        strb    r0, [r6, #S_PRESS]
        subs    r5, #3                  @ 0: Shift press from Unison, 1: from Duo
        cmp     r5, #1
        bhi     6f
        movw    r0, #0x705
        call    GET_PARAM
        ldrh    r1, [r6, #S_SPREAD]
        cmp     r0, r1
        bne     6f                      @ the encoder edited the spread: stay
        eor     r0, r5, #1              @ a Shift tap: Unison -> Duo, Duo -> Unison
        strb    r0, [r6, #S_DUO]
6:      bl      sync
        bl      mode_key                @ the notice for what the release changed
        ldrb    r1, [r6, #S_KEY]
        eors    r1, r0
        ldr     r3, notice_fn
        it      ne
        cmpne   r3, #0
        pop     {r4, r5, r6, lr}
        it      ne
        bxne    r3                      @ notice_fn(new key, changed)
        bx      lr

@ ---------------------------------------------------------------------------------------------------------------
@ Main-loop poll: keep Duo's fields and LED in step, then the next poll with r0-r3 as given.
        .global duo_tick
        .thumb_func
duo_tick:
        push    {r0, r1, r2, r3, r4, lr}
        bl      sync
        pop     {r0, r1, r2, r3, r4, lr}
        ldr     r12, tick_next
        bx      r12

@ Duo stays on only over stock's Unison. Enter: save stock's fields, Delay off; leave: stock's fields and set-up back.
        .thumb_func
sync:
        push    {r4, r5, r6, lr}
        ldr     r4, =STATE
        movs    r5, #0
        ldrb    r0, [r4, #S_DUO]
        cbz     r0, 1f
        bl      unison
        mov     r5, r0
1:      strb    r5, [r4, #S_DUO]
        ldrb    r6, [r4, #S_XF]
        cmp     r5, r6
        beq     6f
        strb    r5, [r4, #S_XF]
        add     r0, r4, #S_SAVE
        eor     r1, r5, #1              @ enter: save stock's fields; leave: put them back
        bl      fields
        cbz     r5, 4f
        ldr     r0, =DELAY_ON
        ldrb    r0, [r0]
        cbz     r0, 2f
        call    DELAY_OFF
2:      movs    r0, #3                  @ the first pulse at once
        strb    r0, [r4, #S_PHASE]
        call    GET_TICK
        str     r0, [r4, #S_NEXT]
        b       7f
4:      bl      stock_mode              @ leave
        bl      unison
        ldr     r1, =PARA_OBJ
        strb    r0, [r1, #0x39]         @ stock's Unison blink back if still in Unison
        movw    r0, #0x700
        call    GET_PARAM
        call    LED_SET
        pop     {r4, r5, r6, pc}
6:      cbz     r5, 9f
        adr     r0, duo_fields          @ stock rewrote a field (a param change): ours again
        movs    r1, #F_MATCH
        bl      fields
        cbnz    r0, 8f
7:      adr     r0, duo_fields
        movs    r1, #F_WRITE
        bl      fields
8:      ldr     r1, =PARA_OBJ
        movs    r0, #0
        strb    r0, [r1, #0x39]         @ stock's Unison blink off
        call    GET_TICK
        ldr     r1, [r4, #S_NEXT]
        subs    r1, r0, r1
        bmi     9f
        ldrb    r1, [r4, #S_PHASE]
        adds    r1, #1
        and     r1, r1, #3
        strb    r1, [r4, #S_PHASE]
        adr     r2, led_ms
        ldrh    r2, [r2, r1, lsl #1]
        add     r0, r2
        str     r0, [r4, #S_NEXT]
        eor     r0, r1, #1              @ phases 0 and 2 lit
        and     r0, r0, #1
        call    LED_SET
9:      pop     {r4, r5, r6, pc}

@ r0 = 1 if 0x707 is Unison and Paraphony is on, else 0.
        .thumb_func
unison:
        push    {r3, lr}
        bl      mode_key
        and     r0, r0, #3
        cmp     r0, #3
        ite     eq
        moveq   r0, #1
        movne   r0, #0
        pop     {r3, pc}

@ r0 = Paraphony != 0 | (Chord == Unison) << 1 | Delay << 2 | (Duo and Unison) << 3
        .thumb_func
mode_key:
        push    {r4, lr}
        movw    r0, #0x700
        call    GET_PARAM
        subs    r4, r0, #0
        it      ne
        movne   r4, #K_PARA
        movw    r0, #0x707
        call    GET_PARAM
        movw    r1, #UNISON
        cmp     r0, r1
        it      eq
        orreq   r4, r4, #K_UNISON
        ldr     r1, =DELAY_ON
        ldrb    r1, [r1]
        cbz     r1, 1f
        adds    r4, #K_DELAY
1:      tst     r4, #K_UNISON           @ Duo only rides on Unison (sync drops it otherwise), so a plain tap from
        beq     2f                      @ Duo reads as Duo OFF even before S_DUO clears
        ldr     r1, =STATE
        ldrb    r1, [r1, #S_DUO]
        cbz     r1, 2f
        adds    r4, #K_DUO
2:      mov     r0, r4
        pop     {r4, pc}

@ Stock's voice-mode set-up from the params: FUN_08049E2C(HANDLER, 3 Unison / 2 Chord / 0), then
@ FUN_08049A98(HANDLER, Paraphony ? para voice count : 1).
        .thumb_func
stock_mode:
        push    {r4, lr}
        movw    r0, #0x707
        call    GET_PARAM
        movs    r1, #0
        movw    r2, #UNISON
        cmp     r0, r2
        it      eq
        moveq   r1, #3
        movw    r2, #0x5555
        cmp     r0, r2
        it      eq
        moveq   r1, #2
        ldr     r0, =HANDLER
        call    APPLY_MODE
        movw    r0, #0x700
        call    GET_PARAM
        movs    r1, #1
        cbz     r0, 1f
        ldr     r0, =PARA_VOICES
        ldrh    r1, [r0]
1:      ldr     r0, =HANDLER
        call    SET_VOICES
        pop     {r4, pc}

@ The note handler's 8 mode fields, in field_off order. fields(r0 = buf, r1 = op): F_READ copies them to buf,
@ F_WRITE buf to them, F_MATCH returns r0 = 1 if they hold buf (else 0).
        .thumb_func
fields:
        push    {r4, r5, r6, lr}
        ldr     r6, =VOICES
        adr     r2, field_off
        movs    r3, #0
1:      ldrsh   r4, [r2, r3, lsl #1]
        ldrb    r5, [r6, r4]            @ the field
        cbnz    r1, 2f
        strb    r5, [r0, r3]            @ read
        b       4f
2:      ldrb    r12, [r0, r3]
        cmp     r1, #F_WRITE
        bne     3f
        strb    r12, [r6, r4]           @ write
        b       4f
3:      cmp     r5, r12                 @ match
        bne     5f
4:      adds    r3, #1
        cmp     r3, #8
        blo     1b
        movs    r0, #1
        pop     {r4, r5, r6, pc}
5:      movs    r0, #0
        pop     {r4, r5, r6, pc}

        .ltorg
        .balign 4
field_off:                                      @ from VOICES
        .hword  0, 0x4A, 0x4B, HANDLER + 0x2E5 - VOICES, HANDLER + 0x2E6 - VOICES, HANDLER + 0x2E7 - VOICES
        .hword  HANDLER + 0x2E9 - VOICES, HANDLER + 0x2EA - VOICES
duo_fields:
        .byte   4, 1, 2, 2, 2, 2, 0, 0x7F       @ a Chord of 2 at interval 0, duplicates allowed: 2 notes x 2 voices
led_ms:
        .hword  60, 120, 60, 760                @ LED phases: on, off, on, off
