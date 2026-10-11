@ Separate Release for MicroFreak firmware 5.0.0.2084.
@
@ Release becomes a real stock parameter: group 20 ("?"), index 0, id 0x1400,
@ registered with the stock registrar in a group slot the parameter object
@ already provides (it has room for 24 groups; stock uses 20). Stock code then
@ saves and loads it in presets, maps its MIDI CC in and sends it out. This
@ file adds only what stock can't do by itself:
@
@   reg_group     register group 20 at boot
@   diff_check    recompute the amp envelope when Release changed
@   rel_main      amp envelope release time from Release
@   ar_main       attack/release envelope release time from Release
@   load_preset   presets without Release (all stock presets) get Release = Decay
@   shift_pot     Shift + Dec/Rel knob drives Release (pot handler)
@   shift_alt     the same for the encoder/relative handler
@   show_release, format_release   show "Release" with a time on the screen
@   curve_time    the popup's envelope curve follows Release while it is shown
@
@ Release follows Dec/Rel modulation proportionally:
@     R' = R * D' / D    (D = Dec/Rel, D' = modulated Dec/Rel)
@ and R == D gives exactly the stock value.
@
@ The code is placed over the factory console's "flag", "help" and "gpio"
@ handlers, which the patch retires (their table slots point at stock's own
@ `bx lr` stub). The display of Dec/Rel is renamed "Decay". It is
@ position-independent apart from literal stock addresses, so the object has
@ no relocations. docs/release-patch.md records where every address comes from.

        .syntax unified
        .thumb
        .text

        .equ OBJ,            0x2001C898      @ parameter object
        .equ REL,            0x2001DA72      @ OBJ+0x11DA: spare u16 at the end of value pool A
        .equ DECAY_VAL,      0x2001DA08      @ group-6 value 2 (Dec/Rel)
        .equ REL_META,       0x2001C9D8      @ OBJ+0x140: unused CC-table slots of groups 21-23
                                             @ +0 meta, +1 flags, +2 CC
        .equ REL_KEY,        0x08062987      @ "Rel": tail of stock key "DecRel"
        .equ REL_ID,         0x1400
        .equ DECAY_ID,       0x602
        .equ REL_FLAGS,      0x43            @ same flags as Dec/Rel: saved, knob parameter
        .equ REGISTER,       0x0800E7B5      @ register(obj, values, flags, ccs, keys, names, n)
        .equ AFTER_REGISTER, 0x0800E731      @ the call reg_group displaces
        .equ ENV_RELEASE,    0x0800DC8D      @ envelope release-time setter
        .equ AR_RELEASE,     0x08014459      @ AR envelope: 2 x t, clamped
        .equ PRESET_PARSE,   0x08054E09
        .equ SNAP_D,         0x404C          @ voice + 0x4034 snapshot + 0x18
        .equ SNAP_R,         0x40B6          @ voice + 0x4034 snapshot + 0x82
        .equ PREV,           0x84            @ previous snapshot follows the current one
        .equ DIFF_CONTINUE,  0x08034199      @ cmp r3, r2
        .equ SHIFT_CONTINUE, 0x08042C13
        .equ POT_CONTINUE,   0x08040253
        .equ ENV_POPUP_CASE, 0x08051AAD      @ dispatcher: Attack..Sustain -> envelope popup
        .equ POPUP_CONTINUE, 0x08051A15      @ cmp r5, r3
        .equ FORMAT_DEC_REL, 0x0804E45B      @ formatter: Dec/Rel time text
        .equ FORMAT_CONTINUE, 0x0804E411     @ cmp r4, r3
        .equ TICK_ENV_CASE,  0x08052C1D      @ UI tick: Attack..Sustain -> envelope popup
        .equ TICK_CONTINUE,  0x08052BB3      @ cmp r6, r3
        .equ PARAM_RAW,      0x0804ED7D      @ u16 value of a parameter id

@ ------------------------------------------------------------------ boot
@ Replaces `bl 0x0800E730` at the end of the parameter object constructor,
@ right after group 19 is registered: r0 = obj, r1 = 0, r2 = 0x16.

        .global reg_group
        .thumb_func
reg_group:
        push    {r0-r4, lr}
        sub     sp, #16
        ldr     r4, =REL_META           @ meta byte stays 0: .bss, zeroed by the reset handler
        movs    r3, #REL_FLAGS
        strb    r3, [r4, #1]
        ldrb    r3, cc_byte
        strb    r3, [r4, #2]
        ldr     r3, =REL_KEY
        str     r3, [sp]
        adr     r3, release_name
        str     r3, [sp, #4]
        movs    r3, #1
        str     r3, [sp, #8]
        ldr     r1, =REL
        mov     r2, r4
        adds    r3, r4, #2
        ldr     r12, =REGISTER
        blx     r12
        add     sp, #16
        pop     {r0-r4, lr}
        ldr     r12, =AFTER_REGISTER
        bx      r12

@ ------------------------------------------------------------------ envelope
@ Replaces `ldrsh r2,[r4,r2]; ldrsh r3,[r4,r3]` at 0x08034194 in the Dec/Rel
@ case of the voice update (r4 = voice, r2 = SNAP_D, r3 = SNAP_D + PREV).
@ Same loads, then r3 is made to differ from r2 when Release changed too.

        .global diff_check
        .thumb_func
diff_check:
        ldrsh   r2, [r4, r2]
        ldrsh   r3, [r4, r3]
        cmp     r2, r3
        bne     1f
        push    {r0, r1}
        movw    r0, #SNAP_R
        ldrh    r1, [r4, r0]
        adds    r0, #PREV
        ldrh    r0, [r4, r0]
        cmp     r0, r1
        pop     {r0, r1}
        it      ne
        addne   r3, r2, #1
1:      ldr     pc, =DIFF_CONTINUE

@ Replaces `bl ENV_RELEASE` at 0x08034682: r0 = envelope, r1 = D', r4 = voice.
        .global rel_main
        .thumb_func
rel_main:
        push    {r0, lr}
        bl      release_mod
        pop     {r0, lr}
        ldr     r12, =ENV_RELEASE
        bx      r12

@ Replaces `bl AR_RELEASE` at 0x080346A2: r0 = AR owner, r1 = D', r4 = voice.
        .global ar_main
        .thumb_func
ar_main:
        push    {r0, lr}
        bl      release_mod
        pop     {r0, lr}
        ldr     r12, =AR_RELEASE
        bx      r12

@ r1 = D' in, R' out; r4 = voice. Clobbers r2, r3.
release_mod:
        movw    r2, #SNAP_R
        ldrh    r2, [r4, r2]
        movw    r3, #SNAP_D
        ldrsh   r3, [r4, r3]
        cmp     r2, r3
        beq     2f                      @ R == D: stock value
        tst     r2, #0x8000
        bne     2f                      @ load in progress: behave as stock
        cmp     r3, #0
        ble     1f
        sxth    r1, r1
        mul     r1, r2, r1
        sdiv    r1, r1, r3
        usat    r1, #15, r1
        bx      lr
1:      mov     r1, r2
2:      bx      lr

@ ------------------------------------------------------------------ presets
@ Replaces `bl PRESET_PARSE` at 0x08055740. The parser resets every stock group
@ from its defaults but not group 20, so Release is preset to a marker the
@ parser can't produce; if the preset had no Release field it becomes Decay.

        .global load_preset
        .thumb_func
load_preset:
        push    {r4, lr}
        ldr     r4, =REL
        movw    r3, #0xFFFF
        strh    r3, [r4]
        ldr     r12, =PRESET_PARSE
        blx     r12
        ldrh    r3, [r4]
        lsrs    r3, r3, #15
        beq     1f
        ldr     r3, =DECAY_VAL
        ldrh    r3, [r3]
        strh    r3, [r4]
1:      pop     {r4, pc}

@ ------------------------------------------------------------------ panel
@ Replace `lsls r4,r3,#29; bpl.w ...`, the Shift branch of the pot handler
@ (0x0804038A, absolute knob positions) and of the encoder/relative handler
@ (0x08042D6A): r5 = parameter id, r3 = its flag byte 1. Stock: flag bit 2
@ selects id + 1 while Shift is held. Dec/Rel has no such flag; it gets Release.
@ Sets r5 and the flags; r4 is scratch, as in stock.

        .macro  SHIFT_ALT continue
        movw    r4, #DECAY_ID
        cmp     r5, r4
        bne     1f
        mov     r5, #REL_ID
        b       2f
1:      lsls    r4, r3, #29
        bpl     2f
        adds    r5, #1
        uxth    r5, r5
2:      ldr     pc, =\continue
        .endm

        .global shift_pot
        .thumb_func
shift_pot:
        SHIFT_ALT POT_CONTINUE

        .global shift_alt
        .thumb_func
shift_alt:
        SHIFT_ALT SHIFT_CONTINUE

@ ------------------------------------------------------------------ screen
@ The OLED already records 0x1400 as the last touched parameter but has no
@ page for it. The id switch exists twice: inlined in the UI tick (the live
@ path) and in the popup dispatcher the tick calls on its first run. Release
@ opens the envelope popup, as Attack/Dec/Rel/Sustain do.

@ Replaces `movw r3,#0x503` at 0x08052BAE in the UI tick (r6 = id, r4 = this, r5 = this+4).
        .global show_release_tick
        .thumb_func
show_release_tick:
        cmp     r6, #REL_ID
        bne     1f
        ldr     pc, =TICK_ENV_CASE
1:      movw    r3, #0x503
        ldr     pc, =TICK_CONTINUE

@ Replaces `movw r3,#0x503` at 0x08051A10 in the dispatcher (r5 = id, r4 = this, r6 = this+4).
        .global show_release
        .thumb_func
show_release:
        cmp     r5, #REL_ID
        bne     1f
        ldr     pc, =ENV_POPUP_CASE
1:      movw    r3, #0x503
        ldr     pc, =POPUP_CONTINUE

@ The OLED chip draws the envelope curve from one decay/release time. Replaces
@ `bl PARAM_RAW` at 0x0804F7C8 in the envelope popup (r0 = 0x602, r7 = popup):
@ while the popup shows Release, the curve gets Release's time.

        .global curve_time
        .thumb_func
curve_time:
        ldrh    r1, [r7, #6]
        cmp     r1, #REL_ID
        it      eq
        moveq   r0, #REL_ID
        ldr     r12, =PARAM_RAW
        bx      r12

@ Replaces `movw r3,#0x603` at 0x0804E40C at the start of the value formatter
@ (r0 = text buffer, r1 = id, r4 = id & 0xFFFF). Release takes Dec/Rel's time
@ formatting, which reads the value through the getter with r1 = id.

        .global format_release
        .thumb_func
format_release:
        cmp     r4, #REL_ID
        bne     1f
        sub     sp, #8                  @ the three stock instructions this skips
        mov     r5, r1
        mov     r6, r0
        ldr     pc, =FORMAT_DEC_REL
1:      movw    r3, #0x603
        ldr     pc, =FORMAT_CONTINUE

        .ltorg

        .global release_cc              @ the patcher's --release-cc rewrites this byte
release_cc:
cc_byte:                                @ local alias: a load from a global label needs a relocation
        .byte   72
        .balign 4
release_name:
        .asciz  "Release"
