@ Direct branches to fixed addresses (stock, or another part's code) for patches tools/build_patch.py links:
@   call F    bl F      F a .equ address (the Thumb bit doesn't matter)
@   jump F    b.w F
@ LLVM folds a .equ operand of bl / b.w at assembly time and can't relocate it, so each macro relocates against the
@ undefined symbol `F.abs` and makes F global; build_patch.assemble gives `F.abs` F's value. The encoding is
@ `bl .` / `b.w .`, the addend build_patch.link reads back.

        .macro  call target
        .global \target
        .reloc  ., R_ARM_THM_CALL, \target\().abs
        .inst.w 0xf7fffffe
        .endm

        .macro  jump target
        .global \target
        .reloc  ., R_ARM_THM_JUMP24, \target\().abs
        .inst.w 0xf7ffbffe
        .endm
