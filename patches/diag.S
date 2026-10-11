@ Hardware diagnostics for the Release patch's placement (no behaviour change).
@
@ diag-region: this code is written into the Release code region and the
@ console "synth" slot is retired, with no hooks, so none of it runs.
@ diag-hook: the same plus one hook, the boot-time call the Release patch uses,
@ routed through `passthrough`, which does exactly what the stock call did.

        .syntax unified
        .thumb
        .text

        .equ AFTER_REGISTER, 0x0800E731

        .global passthrough
        .thumb_func
passthrough:
        ldr     r12, =AFTER_REGISTER
        bx      r12

        .ltorg
