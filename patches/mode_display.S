@ Voice-mode displays: a timed notice ("Paraphony / Unison / Delay / Duo" + "ON/OFF") when the Paraphonic button
@ changes the voice mode. Part of the voice-modes build (docs/voice-modes.md, mode-display.hooks.json), over the delay
@ voice and Duo.
@
@ The notice goes through stock's display manager: the Paraphonic release posts request 0x700 ("show param 0x700",
@ a case stock has but never posts) and the manager draws the page, times it out and returns to the preset page. The
@ text widget is only drawn from inside that case (direct drawing leaves the overlay that stuck on hardware).
@
@ Hooks:
@   notice     Duo's notice_fn word (0x0802BE98, duo.S): Duo's Paraphonic wrapper takes the mode key at the press and
@              after the release, and calls notice(new key, changed bits) when it changed. notice picks the notice
@              and posts 0x700. (A press-time post would be ended by stock's release, which calls FUN_08055E40 to
@              close its Shift-held Spread page.) So this patch needs Duo in its base.
@   popup_text b over the case's `bne.w 0x08053284` at 0x08052F1C (r6 = Paraphony value, r7 = 0): draw the notice's
@              name and stock's "ON" / "OFF", set the timeout to NOTICE_MS, rejoin the case's tail at 0x08052F6E.
@
@ Notice = a name and ON/OFF, by what changed: Delay > Duo (Duo -> Unison shows "Unison ON") > Unison > Paraphony.
@ So leaving Unison or Duo with a plain tap says "Unison OFF" / "Duo OFF" (user, 2026-10-16, after the first
@ hardware run showed "Paraphony OFF" there).
@
@ RAM: NOTICE (u8 notice to draw). (0x2001F4C8 held the press's mode key before Duo took that over.)

        .syntax unified
        .thumb
#include "series.inc"
        .text

        .equ GET_PARAM,     0x0803B815      @ (id) -> u16
        .equ POST,          0x080558C1      @ (req, param): show this param
        .equ REQ,           0x20000A14
        .equ WIDGET,        0x2001DFF4
        .equ TEXT,          0x080557E9      @ (widget, ptr, len): text chunk; (widget, 0, 0x7F) clears
        .equ SEND,          0x0805579D      @ (widget, cmd, arg)
        .equ CASE_TAIL,     0x08052F6F
        .equ STR_OFF,       0x08075710      @ "Paraphony\nOFF", 14 bytes with the NUL
        .equ STR_ON,        0x08075720      @ "Paraphony\nON", 13
        .equ UNISON,        0x7FFF
        .equ NOTICE_MS,     3000            @ mode-notice timeout (user, 2026-10-16; stock popups: 5000)
        .equ NOTICE,        0x2001F4C9      @ u8: name (bits 0-1) | N_ON
        .equ N_PARA,        0               @ notice names: stock's "Paraphony\n", then ours
        .equ N_UNISON,      1
        .equ N_DELAY,       2
        .equ N_DUO,         3
        .equ N_ON,          4               @ "ON", else "OFF" (both stock's, the Paraphony strings' tails)

        .equ K_PARA,        1               @ Duo's mode key: Paraphony != 0, Chord == Unison, Delay, Duo
        .equ K_UNISON,      2
        .equ K_DELAY,       4
        .equ K_DUO,         8

@ ---------------------------------------------------------------------------------------------------------------
@ notice(r0 = mode key after the release, r1 = bits the release changed), from Duo's Paraphonic wrapper.
        .global notice
        .thumb_func
notice:
        movs    r2, #N_DELAY            @ r2 = name, r3 = the key bit that makes it ON
        movs    r3, #K_DELAY
        tst     r1, r3
        bne     4f
        movs    r2, #N_DUO
        movs    r3, #K_DUO
        tst     r1, r3
        beq     3f
        tst     r0, r3
        bne     4f                      @ Duo ON
        movs    r2, #N_UNISON           @ Duo left for Unison: "Unison ON"; otherwise "Duo OFF"
        movs    r3, #K_UNISON
        tst     r0, r3
        bne     4f
        movs    r2, #N_DUO
        b       4f
3:      movs    r2, #N_UNISON
        movs    r3, #K_UNISON
        tst     r1, r3
        bne     4f
        movs    r2, #N_PARA
        movs    r3, #K_PARA
4:      tst     r0, r3
        it      ne
        orrne   r2, r2, #N_ON
        ldr     r1, =NOTICE
        strb    r2, [r1]
        ldr     r0, =REQ
        movw    r1, #0x700
        jump    POST

@ ---------------------------------------------------------------------------------------------------------------
        .global popup_text
        .thumb_func
popup_text:
        push    {r4, r5}                @ the manager's object and request struct; r6 is reset by the tail, r7 untouched
        sub     sp, #16                 @ the notice is built here: each text call carries 4 bytes, so a name and its
        ldr     r0, =REQ                @ ON/OFF must go out as one string (two sends put junk between them)
        movw    r1, #NOTICE_MS          @ the manager armed 5000 ms (+0x7C) just before this case
        str     r1, [r0, #0x7C]
        ldr     r1, =NOTICE
        ldrb    r5, [r1]
        and     r1, r5, #3
        adr     r0, names
        ldr     r4, [r0, r1, lsl #2]
        adr     r0, name_len
        ldrb    r6, [r0, r1]
        mov     r0, sp
1:      ldrb    r2, [r4], #1            @ "Paraphony\n", "Unison\n", "Delay\n" or "Duo\n"
        strb    r2, [r0], #1
        subs    r6, #1
        bne     1b
        tst     r5, #N_ON
        ite     ne
        ldrne   r4, =STR_ON + 10        @ then stock's "ON" / "OFF", with the NUL
        ldreq   r4, =STR_OFF + 10
2:      ldrb    r2, [r4], #1
        strb    r2, [r0], #1
        cmp     r2, #0
        bne     2b
        mov     r4, sp
        subs    r5, r0, r4              @ length with the NUL
        ldr     r0, =WIDGET
        movs    r1, #0
        movs    r2, #0x7F
        call    TEXT
3:      cmp     r5, #4
        ite     hs
        movhs   r2, #4
        movlo   r2, r5
        ldr     r0, =WIDGET
        mov     r1, r4
        adds    r4, r4, r2
        subs    r5, r5, r2
        call    TEXT
        cmp     r5, #0
        bne     3b
        ldr     r0, =WIDGET
        movs    r1, #0x12
        ldr     r2, =0x02001A00
        call    SEND
        add     sp, #16
        pop     {r4, r5}
        jump    CASE_TAIL

        .ltorg
        .balign 4
names:                                  @ by name index, no NULs
        .word   STR_OFF, str_unison, str_delay, str_duo
name_len:
        .byte   10, 7, 6, 4
str_unison:
        .ascii  "Unison\n"
str_delay:
        .ascii  "Delay\n"
str_duo:
        .ascii  "Duo\n"
        .balign 4
