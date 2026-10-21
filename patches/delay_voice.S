@ Delay voice mode: a Minilogue-style note echo on stock 5.0.0 (docs/voice-modes.md, delay-voice.hooks.json).
@
@ Hold Paraphonic for HOLD_MS or longer with no key down and Delay toggles. Paraphony is turned on with it, and left as
@ it was before the hold when Delay goes off. A tap is stock, except that a tap that turns Paraphony off also clears
@ Delay. Holding Paraphonic while playing keys is stock's chord capture and doesn't touch Delay.
@
@ While Delay is on, each paraphonic note-on queues REPEATS echoes: the same note again at k * D (D = a dotted 1/8 at
@ the preset tempo), each on whatever voice the stock allocator gives it, and quieter by ATT[k] in the voice mix. An
@ echo lasts as long as the played note, at most D - GAP. Echoes of a note are skipped while its key is held.
@
@ Hooks (delay-voice.hooks.json):
@   para_btn     b.w  at 0x080433F0 (press) and 0x0803F1E2 (release), in place of the Paraphonic handler 0x0803CA5C
@   echo_on      bl   at 0x0804866E, the paraphonic note-on call of the voice allocator 0x0804DA80
@   echo_off     bl   at 0x080493CC, the paraphonic note-off call of the allocator
@   echo_tick    bl   at 0x0803A824, a main-loop poll (in place of 0x08039DA4, tail-called)
@   voice_level  bl   at every call of the envelope-level getter 0x0800DCC8 in the audio block's voice mix
@
@ Feedback: while Delay is on the Paraphonic LED stays lit with a DIP_MS dark dip every D, on each echo of the last note
@ played: the reverse of Unison's short bright blip about once a second. (A "Delay ON/OFF" popup was tried: stock's
@ text popup stays up on hardware, so there is none.)
@
@ RAM: STATE, 424 bytes between the heap (one 88-byte block from 0x2001F230) and the deepest stack seen (0x2001FAE0).

        .syntax unified
        .thumb
        .text

        .equ STATE,          0x2001F300
        .equ S_ON,           0x00            @ u8  Delay on
        .equ S_LED,          0x01            @ u8  1 = LED lit, 0 = in a dip
        .equ S_PRESS,        0x04            @ u32 Paraphonic press time, ms
        .equ S_BLINK,        0x08            @ u32 next LED change, ms
        .equ S_LAST,         0x0C            @ u32 last ms the queue was scanned
        .equ S_ATT,          0x10            @ u16 x 4: per-voice attenuation, Q15 (0 = stock level)
        .equ S_HELD,         0x18            @ u32 x 4: keys held, one bit per note
        .equ S_QUEUE,        0x28            @ NEV x {u32 due ms, u32 msg}; msg 0 = free
        .equ NEV,            48

        .equ HOLD_MS,        500
        .equ REPEATS,        3
        .equ DIV_MS_X_TEMPO, 4500000         @ dotted 1/8: 0.75 beat = 45000 / BPM s, tempo is BPM x 100
        .equ GAP,            10              @ ms between an echo's end and the next echo
        .equ DIP_MS,         60              @ dark part of each beat (the matrix chip applies LED changes ~10 ms apart)

        .equ PARA_HANDLER,   0x0803CA5D      @ (this, down): stock Paraphonic button
        .equ GET_PARAM,      0x0803B815      @ (id) -> u16 value
        .equ GET_TICK,       0x08055ED9      @ HAL_GetTick, ms
        .equ ALLOC,          0x0804DA81      @ (VOICES, status | note << 8 | vel << 16, 0, para)
        .equ MAIN_POLL,      0x08039DA5
        .equ IO_SEND,        0x08021415      @ (IO_LINK, w0, w1, 1): queue a 6-byte UI frame
        .equ IO_LINK,        0x200005A0
        .equ VOICES,         0x20004384      @ count, then 12-byte slots at +2: active, voice, note, vel, ...
        .equ ENV_BASE,       0x200089C0      @ voice k's envelopes are at ENV_BASE + 0x68 (+ 0x68) + k * VOICE
        .equ VOICE,          0x59E4
        .equ TEMPO,          0x20003EEC      @ u16 BPM x 100 (tempo clock 0x20003CDC + 0x210)
        .equ LED_HEAD,       0x000700F5      @ F5 00 07 00: the event FUN_08021A8C builds for 0x700's LED

@ ---------------------------------------------------------------------------------------------------------------
@ Paraphonic button, r0 = this (0x20003714), r1 = 1 press / 0 release.
        .global para_btn
        .thumb_func
para_btn:
        cbz     r1, 1f
        push    {r0, r1, r2, lr}
        bl      get_tick
        ldr     r3, =STATE
        str     r0, [r3, #S_PRESS]
        pop     {r0, r1, r2, lr}
        ldr     r12, =PARA_HANDLER
        bx      r12
1:      push    {r4, r5, r6, lr}
        mov     r4, r0
        bl      get_tick
        ldr     r3, =STATE
        ldr     r2, [r3, #S_PRESS]
        subs    r5, r0, r2              @ ms held
        movw    r0, #0x700
        bl      get_param
        mov     r6, r0                  @ Paraphony before the release
        mov     r0, r4
        movs    r1, #0
        bl      call_handler            @ stock release: chord capture, or toggle Paraphony
        movw    r0, #HOLD_MS
        cmp     r5, r0
        bhs     2f
        movw    r0, #0x700              @ a tap: Paraphony off clears Delay
        bl      get_param
        cbnz    r0, 9f
        ldr     r3, =STATE
        ldrb    r2, [r3, #S_ON]
        cbz     r2, 9f
        bl      delay_off
        b       9f
2:      movw    r0, #0x707              @ chord captured (or unison): stock's result stands
        bl      get_param
        cbnz    r0, 9f
        ldr     r3, =STATE
        ldrb    r2, [r3, #S_ON]
        cbz     r2, 3f
        bl      delay_off               @ Delay off, Paraphony back to what it was
        movw    r0, #0x700
        bl      get_param
        cmp     r0, r6
        beq     9f
        b       4f
3:      movs    r2, #1                  @ Delay on, with Paraphony on
        strb    r2, [r3, #S_ON]
        strb    r2, [r3, #S_LED]
        bl      get_tick
        ldr     r3, =STATE
        str     r0, [r3, #S_BLINK]      @ first dip now
        movw    r0, #0x700
        bl      get_param
        cbnz    r0, 9f
4:      mov     r0, r4
        movs    r1, #0
        bl      call_handler            @ the stock release again toggles Paraphony back
9:      pop     {r4, r5, r6, pc}

        .thumb_func
call_handler:
        ldr     r12, =PARA_HANDLER
        bx      r12

        .thumb_func
get_param:
        ldr     r12, =GET_PARAM
        bx      r12

        .thumb_func
get_tick:
        ldr     r12, =GET_TICK
        bx      r12

@ Delay off: drop queued echo note-ons, play queued echo note-offs now (no voice is left holding), voices back to
@ stock level, LED shows Paraphony.
        .thumb_func
delay_off:
        push    {r4, r5, r6, lr}
        ldr     r3, =STATE
        movs    r2, #0
        strb    r2, [r3, #S_ON]
        str     r2, [r3, #S_ATT]
        str     r2, [r3, #S_ATT + 4]
        add     r4, r3, #S_QUEUE
        movs    r5, #NEV
1:      ldr     r0, [r4, #4]
        cbz     r0, 2f
        movs    r1, #0
        str     r1, [r4, #4]
        uxtb    r1, r0
        cmp     r1, #0x80
        it      eq
        bleq    fire
2:      adds    r4, #8
        subs    r5, #1
        bne     1b
        movw    r0, #0x700
        bl      get_param
        bl      led_set
        pop     {r4, r5, r6, pc}

@ r0 != 0: Paraphonic LED on, else off.
        .thumb_func
led_set:
        push    {r4, lr}
        cmp     r0, #0
        ite     ne
        movne   r2, #0xFF00
        moveq   r2, #0
        ldr     r1, =LED_HEAD
        ldr     r0, =IO_LINK
        movs    r3, #1
        ldr     r12, =IO_SEND
        blx     r12
        pop     {r4, pc}

@ Delay time in ms from the tempo.
        .thumb_func
delay_ms:
        ldr     r0, =TEMPO
        ldrh    r0, [r0]
        movw    r1, #3000
        cmp     r0, r1
        it      lo
        movwlo  r0, #12000
        ldr     r1, =DIV_MS_X_TEMPO
        udiv    r0, r1, r0
        bx      lr

@ The allocator slot that plays `note` (r0) gets attenuation r1. Clobbers r0-r3, r12.
        .thumb_func
set_att:
        ldr     r2, =VOICES
        ldrb    r3, [r2]
        adds    r2, #2
1:      cbz     r3, 9f
        ldrb    r12, [r2]
        cmp     r12, #0
        beq     2f
        ldrb    r12, [r2, #2]
        cmp     r12, r0
        bne     2f
        ldrb    r12, [r2, #1]
        cmp     r12, #3
        bhi     9f
        ldr     r2, =STATE + S_ATT
        strh    r1, [r2, r12, lsl #1]
        bx      lr
2:      adds    r2, #12
        subs    r3, #1
        b       1b
9:      bx      lr

@ Queue an echo's note-on {r0 due, r1 msg} and its note-off {r2 due, r3 msg} together, or neither when fewer than two
@ slots are free: a note-on queued without its note-off would hold a voice until Delay is turned off. Clobbers r0-r3,
@ r12.
        .thumb_func
enqueue_pair:
        push    {r4, r5, r6, lr}
        ldr     r4, =STATE + S_QUEUE
        movs    r5, #NEV
        movs    r6, #0                  @ first free slot
1:      ldr     r12, [r4, #4]
        cmp     r12, #0
        bne     2f
        cbz     r6, 3f
        str     r0, [r6]                @ second free slot: store both
        str     r1, [r6, #4]
        str     r2, [r4]
        str     r3, [r4, #4]
        pop     {r4, r5, r6, pc}
3:      mov     r6, r4
2:      adds    r4, #8
        subs    r5, #1
        bne     1b
        pop     {r4, r5, r6, pc}        @ full: drop the echo

@ r0 = 1 << (note & 31), r1 = the held word's address. Clobbers r2.
        .thumb_func
held_bit:
        ldr     r1, =STATE + S_HELD
        lsrs    r2, r0, #5
        add     r1, r1, r2, lsl #2
        and     r2, r0, #31
        movs    r0, #1
        lsls    r0, r2
        bx      lr

@ ---------------------------------------------------------------------------------------------------------------
@ Paraphonic note-on: r0 = VOICES, r1 = 0x90 | note << 8 | vel << 16, r2 = 0, r3 = 1.
        .global echo_on
        .thumb_func
echo_on:
        push    {r4, r5, r6, r7, r8, lr}
        mov     r4, r1
        ldr     r12, =ALLOC
        blx     r12
        ubfx    r5, r4, #8, #7          @ note
        mov     r0, r5
        bl      held_bit
        ldr     r2, [r1]
        orrs    r2, r0
        str     r2, [r1]
        mov     r0, r5
        movs    r1, #0
        bl      set_att                 @ a played note is at stock level
        ldr     r3, =STATE
        ldrb    r0, [r3, #S_ON]
        cbz     r0, 9f
        movw    r0, #0x707              @ not in chord or unison mode
        bl      get_param
        cbnz    r0, 9f
        bl      delay_ms
        mov     r7, r0                  @ D
        bl      get_tick
        mov     r8, r0                  @ now
        ldr     r3, =STATE              @ LED: lit now, the next dip on this note's first echo
        add     r0, r8, r7
        str     r0, [r3, #S_BLINK]
        ldrb    r0, [r3, #S_LED]
        movs    r1, #1
        strb    r1, [r3, #S_LED]
        cbnz    r0, 2f
        movs    r0, #1
        bl      led_set
2:      movs    r6, #1
1:      mla     r0, r7, r6, r8          @ echo k on at now + k * D
        add     r2, r0, r7              @ and off at now + k * D + D - GAP (shortened at note-off)
        subs    r2, #GAP
        bic     r1, r4, #0xFF000000
        orr     r1, r1, r6, lsl #24
        lsls    r3, r5, #8
        orr     r3, r3, #0x80
        orr     r3, r3, r6, lsl #24
        bl      enqueue_pair
        adds    r6, #1
        cmp     r6, #REPEATS + 1
        bne     1b
9:      pop     {r4, r5, r6, r7, r8, pc}

@ Paraphonic note-off: r0 = VOICES, r1 = 0x80 | note << 8, r2, r3 as stock passes them.
        .global echo_off
        .thumb_func
echo_off:
        push    {r4, r5, r6, r7, r8, lr}
        mov     r4, r1
        ldr     r12, =ALLOC
        blx     r12
        ubfx    r5, r4, #8, #7
        mov     r0, r5
        bl      held_bit
        ldr     r2, [r1]
        bics    r2, r0
        str     r2, [r1]
        bl      delay_ms
        mov     r7, r0                  @ D
        bl      get_tick
        mov     r8, r0                  @ now
        sub     lr, r7, #GAP            @ the longest echo
        ldr     r6, =STATE + S_QUEUE
        movs    r4, #NEV
1:      ldr     r1, [r6, #4]
        uxtb    r0, r1
        cmp     r0, #0x80
        bne     2f
        ubfx    r0, r1, #8, #7
        cmp     r0, r5
        bne     2f
        lsrs    r1, r1, #24             @ k
        mul     r2, r1, r7              @ k * D
        ldr     r0, [r6]
        subs    r3, r0, r2
        subs    r3, r3, lr              @ the note's on time
        sub     r12, r8, r3             @ how long it was held
        cmp     r12, lr
        bhs     2f
        add     r0, r3, r2
        add     r0, r12
        str     r0, [r6]                @ echo k off at on + k * D + held
2:      adds    r6, #8
        subs    r4, #1
        bne     1b
        pop     {r4, r5, r6, r7, r8, pc}

@ ---------------------------------------------------------------------------------------------------------------
@ Main-loop poll: once per ms, play due echoes and blink the LED; then the stock poll with r0 as given.
        .global echo_tick
        .thumb_func
echo_tick:
        push    {r0, r4, r5, r6, r7, lr}
        bl      get_tick
        mov     r5, r0
        ldr     r4, =STATE
        ldr     r1, [r4, #S_LAST]
        cmp     r1, r5
        beq     8f
        str     r5, [r4, #S_LAST]
        ldrb    r0, [r4, #S_ON]
        cbz     r0, 3f
        ldr     r1, [r4, #S_BLINK]
        subs    r1, r5, r1
        bmi     3f
        ldrb    r6, [r4, #S_LED]        @ lit for D - DIP_MS, then dark for DIP_MS
        eor     r6, r6, #1
        strb    r6, [r4, #S_LED]
        bl      delay_ms
        subs    r0, #DIP_MS
        cmp     r6, #0
        it      eq
        moveq   r0, #DIP_MS
        add     r0, r5
        str     r0, [r4, #S_BLINK]
        mov     r0, r6
        bl      led_set
3:      add     r6, r4, #S_QUEUE
        movs    r7, #NEV
4:      ldr     r1, [r6, #4]
        cbz     r1, 6f
        ldr     r0, [r6]
        subs    r0, r5, r0
        bmi     6f
        movs    r0, #0
        str     r0, [r6, #4]
        mov     r0, r1
        bl      fire
6:      adds    r6, #8
        subs    r7, #1
        bne     4b
8:      pop     {r0, r4, r5, r6, r7, lr}
        ldr     r12, =MAIN_POLL
        bx      r12

@ Play one queued event, r0 = msg; skipped while its key is held.
        .thumb_func
fire:
        push    {r4, r5, r6, lr}
        mov     r4, r0
        ubfx    r5, r4, #8, #7
        mov     r0, r5
        bl      held_bit
        ldr     r1, [r1]
        tst     r1, r0
        bne     9f
        uxtb    r1, r4
        cmp     r1, #0x90
        bne     5f
        ldr     r0, =VOICES
        bic     r1, r4, #0xFF000000
        movs    r2, #0
        movs    r3, #1
        ldr     r12, =ALLOC
        blx     r12
        lsrs    r1, r4, #24
        adr     r2, att_table
        ldrh    r1, [r2, r1, lsl #1]
        mov     r0, r5
        bl      set_att
        b       9f
5:      ldr     r0, =VOICES
        uxth    r1, r4
        movs    r2, #0
        movs    r3, #0
        ldr     r12, =ALLOC
        blx     r12
9:      pop     {r4, r5, r6, pc}

@ ---------------------------------------------------------------------------------------------------------------
@ Voice mix: the envelope level (stock getter: ldrh [r0, #0x64]) scaled by that voice's echo attenuation.
        .global voice_level
        .thumb_func
voice_level:
        push    {r1, r2, r3, lr}
        ldr     r1, =ENV_BASE
        subs    r1, r0, r1
        ldrh    r0, [r0, #0x64]
        movw    r2, #VOICE
        movs    r3, #0
1:      cmp     r1, r2
        blo     2f
        subs    r1, r1, r2
        adds    r3, #1
        cmp     r3, #4
        bhs     9f
        b       1b
2:      ldr     r1, =STATE + S_ATT
        ldrh    r1, [r1, r3, lsl #1]
        cbz     r1, 9f
        rsb     r1, r1, #0x8000
        muls    r0, r1, r0
        lsrs    r0, r0, #15
9:      pop     {r1, r2, r3, pc}

        .ltorg
        .balign 4
@ Attenuation of echo k (index 0 unused): gains 0.6, 0.36, 0.216 (-4.4, -8.9, -13.3 dB).
att_table:
        .hword  0, 0x3333, 0x51EC, 0x645A
