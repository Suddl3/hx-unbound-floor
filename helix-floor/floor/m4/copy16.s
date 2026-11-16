@ copy16.s: copy 16 bytes from SRC to DST (the host patches both literals): reads local SRAM into SDRAM for a peek.
.syntax unified
.thumb
.text
.thumb_func
copy16:
    ldr r0, =0x1001fd7c
    ldr r1, =0x29f06800
    ldmia r0, {r2-r5}
    stmia r1, {r2-r5}
    bx lr
.ltorg
