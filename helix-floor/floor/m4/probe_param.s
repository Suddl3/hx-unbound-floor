@ probe_param.s: live probe (not committed): knob 0 of block id r0 through the block title's parameter reader.
@ Result words at 0x29f03000: out[0..2] (12 bytes the reader fills), the reader's return, the block's preset id.
.syntax unified
.thumb
.text
.equ MEMSET, 0x28155f35
.equ PRESET_OBJ, 0x28114a1d
.equ BLOCK_DESC, 0x28148ccd
.equ CTX_FN, 0x28114a1d
.equ PARAM_FN, 0x2813aab9
.equ RESULT, 0x29f03000
.global probe

.thumb_func
probe:
    push {r4-r6, lr}
    sub sp, #0x60
    mov r4, r0                      @ the block id (the call's argument byte)
    mov r0, sp
    movs r1, #0
    movs r2, #0x34
    ldr r3, =MEMSET
    blx r3
    ldr r3, =PRESET_OBJ
    blx r3
    mov r1, r4
    mov r2, sp
    ldr r3, =BLOCK_DESC
    blx r3
    mov r6, r0                      @ its result
    mvn r0, #1
    str r0, [sp, #0x38]
    movs r0, #0
    str r0, [sp, #0x3c]             @ q = {-2, knob 0}
    str r0, [sp, #0x40]
    str r0, [sp, #0x44]
    str r0, [sp, #0x48]
    str r0, [sp, #0x4c]
    str r0, [sp, #0x50]
    ldr r3, =CTX_FN
    blx r3
    mov r1, r4                      @ the block id (the title's r5)
    add r2, sp, #0x38
    add r3, sp, #0x48
    ldr r5, =PARAM_FN
    blx r5
    ldr r1, =RESULT
    ldr r2, [sp, #0x48]
    str r2, [r1]
    ldr r2, [sp, #0x4c]
    str r2, [r1, #4]
    ldr r2, [sp, #0x50]
    str r2, [r1, #8]
    str r0, [r1, #12]
    ldr r2, [sp, #1]
    str r2, [r1, #16]
    str r6, [r1, #20]
    add sp, #0x60
    pop {r4-r6, pc}
.ltorg
