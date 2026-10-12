@ Mod matrix over MIDI CC for MicroFreak firmware 5.0.0.2084.
@
@ The mod matrix is seven stock parameter groups, Co1..Co7 (10..16), one per
@ destination row: Pitch, Wave, Timbre, Cutoff, Assign 1, 2 and 3. Indices
@ 0..4 of each row are the amounts for the five sources: CyclEnv, Env, LFO,
@ Press and Key/Arp. They are ordinary saved parameters with no CC (127), and
@ their values are signed: 0 is no modulation, -0x8000..+0x7FFE is -100..+100%.
@
@   matrix_boot      after the parameter object is built, give each cell in
@                    matrix_ccs its CC in both directions
@   matrix_cc_in     incoming CC: 0..127 -> -100..+100%, CC 64 = exactly 0
@   matrix_cc_out    outgoing CC from the parameter-change listener (panel
@   matrix_send_cc   edits, preset loads) and from the set-and-send function:
@                    the inverse, so values round-trip exactly
@   matrix_local, matrix_local2
@                    with Local Control off, stock refuses panel writes to a
@                    parameter that has a CC; matrix cells stay exempt, as in
@                    stock, so the matrix keeps working locally
@
@ Stock already converts this way for one cell: CC 26 (Filter Amt, 0x605) also
@ writes Env -> Cutoff (0x0D01) as (v15 - 0x4000) * 2, with CC 64 as 0. That
@ cell keeps CC 26 and gets no second CC here.
@
@ Stock has eight more CC senders, in the panel's pot and encoder handlers.
@ They only run for the 24 parameters of the fixed panel list at 0x08073788,
@ which holds no matrix cell, so they keep sending exactly what stock sends.
@
@ Every hook here replaces 4 bytes with a `bl` where lr holds nothing live, and
@ returns with `bx lr`. The code is placed over the factory console's "synth"
@ handler, which the patch retires. It has no relocations: every stock address
@ is a literal. docs/matrix-cc.md records where every address comes from.

        .syntax unified
        .thumb
        .text

        .equ OBJ,            0x2001C898      @ parameter object
        .equ CC_MAP,         0x14C           @ OBJ + CC_MAP + cc*2 = (index, group)
        .equ CC_ARRAYS,      0xEC            @ OBJ + CC_ARRAYS + group*4 = that group's CC bytes
        .equ PARAM_INIT,     0x0800EB11      @ parameter object constructor
        .equ FIRST_ROW,      10              @ Co1
        .equ ROWS,           7
        .equ SOURCES,        5
        .equ FIRST_ID,       FIRST_ROW << 8
        .equ CC_64,          0x4081          @ CC value 64 after stock's 7-to-15-bit stretch
        .equ NO_CC,          0x7F

@ Only matrix amounts reach these hooks with a CC: the Dest parameters
@ (index 5) and Env -> Cutoff keep "no CC". So "is this a matrix amount?" is
@ just "is the id in 0x0A00..0x10FF?":
        .macro  IF_MATRIX_ID scratch, id
        sub     \scratch, \id, #FIRST_ID
        cmp     \scratch, #ROWS << 8
        .endm                           @ then: lo = matrix

@ ------------------------------------------------------------------ boot
@ Replaces `bl 0x0800EB10` at 0x08043530, the constructor's only call
@ (r0 = obj). The Release patch's group is registered inside it, so the CC map
@ is complete when this runs. The caller reloads r0 afterwards.

        .global matrix_boot
        .thumb_func
matrix_boot:
        push    {r4-r6, lr}
        ldr     r12, =PARAM_INIT
        blx     r12
        adr     r4, ccs_table
        ldr     r5, =OBJ
        movs    r6, #0                  @ cell = row * SOURCES + source
1:      ldrb    r3, [r4, r6]            @ its CC, 0 = none
        cbz     r3, 2f
        movs    r2, #SOURCES
        udiv    r0, r6, r2              @ r0 = row
        mls     r1, r0, r2, r6          @ r1 = source = parameter index
        adds    r0, #FIRST_ROW          @ r0 = group
        add     r2, r5, r3, lsl #1
        strb    r1, [r2, #CC_MAP]       @ CC in: cc -> (index, group)
        strb    r0, [r2, #CC_MAP + 1]
        add     r2, r5, r0, lsl #2
        ldr     r2, [r2, #CC_ARRAYS]
        strb    r3, [r2, r1]            @ CC out: parameter -> cc
2:      adds    r6, #1
        cmp     r6, #ROWS * SOURCES
        bne     1b
        pop     {r4-r6, pc}

@ ------------------------------------------------------------------ MIDI in
@ Replaces `ubfx r3, r9, #8, #8` at 0x080479D6 in the MIDI input handler,
@ right after the CC map lookup: r9 = parameter id, r8 = the CC value
@ stretched to 0..0x7FFF. Stock then compares r8 with the current value and
@ stores it, so a matrix amount is converted to signed here. Returns with
@ r3 = group, as the displaced instruction left it; clobbers r12.

        .global matrix_cc_in
        .thumb_func
matrix_cc_in:
        ubfx    r3, r9, #8, #8
        IF_MATRIX_ID r12, r9
        bhs     1f
        movw    r12, #CC_64
        cmp     r8, r12
        sub     r8, r8, #0x4000
        lsl     r8, r8, #1
        it      eq
        moveq   r8, #0
1:      bx      lr

@ ------------------------------------------------------------------ MIDI out
@ Both stock senders a matrix amount can reach compute the CC value as
@ `asrs v, v, #8; uxtb r1, v` after checking the parameter has a CC. For a
@ matrix amount v becomes ((v >> 8) + 128) >> 1, which equals
@ (value + 0x8000) >> 9: -100%, 0 and +100% go out as 0, 64 and 127.
        .macro  SEND_CC id, value
        asrs    \value, \value, #8
        IF_MATRIX_ID r1, \id            @ r1 is free: the displaced uxtb sets it
        itt     lo
        addlo   \value, #128
        asrlo   \value, \value, #1
        uxtb    r1, \value
        bx      lr
        .endm

@ Replaces `asrs r5, r5, #8; uxtb r1, r5` at 0x08023A02 in the listener that
@ sends a parameter's CC when it changes (r3 = id, r5 = value).
        .global matrix_cc_out
        .thumb_func
matrix_cc_out:
        SEND_CC r3, r5

@ Replaces `asrs r7, r7, #8; uxtb r1, r7` at 0x08026874 in the set-and-send
@ function 0x0802682C (r5 = id, r7 = value), which stock already points at
@ matrix ids (0x08026B9C).
        .global matrix_send_cc
        .thumb_func
matrix_send_cc:
        SEND_CC r5, r7

@ ------------------------------------------------------------------ Local Off
@ Stock: with Local Control off, a panel write to a parameter whose CC byte
@ isn't 0x7F is refused (only MIDI may set it). Matrix cells had no CC, so
@ they were always written; they still are. Each replaces
@ `ldrb r3, [r3, idx]; cmp r3, #0x7F`; the caller branches on these flags.
        .macro  LOCAL_GATE group, index
        ldrb    r3, [r3, \index]
        sub     r12, \group, #FIRST_ROW
        cmp     r12, #ROWS - 1
        it      ls
        movls   r3, #NO_CC
        cmp     r3, #NO_CC
        bx      lr
        .endm

@ 0x08023C82 in the setter 0x08023C40 (r4 = group, r7 = index).
        .global matrix_local
        .thumb_func
matrix_local:
        LOCAL_GATE r4, r7

@ 0x08024756 in the setter 0x0802473C (r6 = group, r5 = index).
        .global matrix_local2
        .thumb_func
matrix_local2:
        LOCAL_GATE r6, r5

        .ltorg

@ ------------------------------------------------------------------ CCs
@ One CC per cell, rows in matrix order, sources CyclEnv, Env, LFO, Press,
@ Key/Arp; 0 = no CC. All are unused by stock and avoid the CCs MIDI gives a
@ fixed meaning (bank, mod wheel, data entry, volume, expression, the 14-bit
@ LSBs, pedals, portamento, high-resolution velocity, effect depths,
@ RPN/NRPN, channel mode) and the Release patch's default CC 72.

        .balign 4
        .global matrix_ccs              @ the patcher reads this table
matrix_ccs:
ccs_table:                              @ local alias: adr to a global label needs a relocation
        .byte   14,  15,  20,  21,  22  @ Pitch
        .byte   25,  27,  30,  31,   3  @ Wave
        .byte   85,  86,  87,  80,  89  @ Timbre
        .byte   90,   0, 104, 107, 108  @ Cutoff (Env: CC 26, Filter Amt, in stock)
        .byte  109, 110, 111, 112, 113  @ Assign 1
        .byte  114, 115, 116, 117, 118  @ Assign 2
        .byte  119,  75,  76,  77,  78  @ Assign 3
        .balign 4
