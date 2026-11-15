@ focus_emmc.s: Focus View's picture from the eMMC picture store, built into the firmware (NAM_EMMC_ART=1, focus_emmc.py).
@ It sits after segment 1's bytes (local SRAM 0x1008ba38: that bank's tail held only the boot memory test's pattern at
@ run time), and the build writes a jump to fe_img over the DSP meter module's focus_img. fe_img is entered as focus_img
@ is (r4 the frame, from focus_fill in the paint task).
@ The store (auto/floor_emmc_art.py write) starts at sector STORE: sector 0 = "HXPC" + 12 bytes, then {u16 S, u16 preset
@ ids, u32 first picture sector, u16 map[preset id]} (0xffff none); each S x S RGB555 picture on whole sectors.
@ On the first call the store's 8 header sectors are read into HDR (free SDRAM); no store: nothing is drawn, ever (until
@ a restart). Then as emmc_art.s: the selected block's preset id (as focus_pid), its picture read into CACHE when it
@ changed (the firmware's own sector read, under the card's mutex) and copied into the frame centred at x 400, its
@ middle at y CENTRE_Y.
.syntax unified
.thumb
.text
.equ SEL_BLOCK, 0x281043e9
.equ MEMSET, 0x28155f35
.equ PRESET_OBJ, 0x28114a1d
.equ BLOCK_DESC, 0x28148ccd
.equ READ, 0x1000504d               @ (buffer, sector, count) -> < 0 on error
.equ STORE, 0x400000
.equ HDR, 0x29900000                @ free SDRAM (boot memory test pattern at run time)
.equ CACHE, 0x29910000              @ one picture, up to 256 x 256
.equ MAGIC, 0x43505848              @ "HXPC"
.equ ROW, 1600
.equ CENTRE_X, 400
.equ CENTRE_Y, 196
.global fe_img

.thumb_func
fe_img:                             @ r4 the frame
    push {r4-r10, lr}
    sub sp, #0x40                   @ 32 + 64: external calls stay 8-byte aligned
    adr r12, fe_state
    ldr r0, [r12]
    cmp r0, #1
    beq fe_ready
    bhi fe_out                      @ 2: no store
    ldr r0, =HDR                    @ 0: the first call reads the store's header
    ldr r1, =STORE
    movs r2, #8
    ldr r3, =READ
    blx r3
    ldr r1, =HDR
    ldr r1, [r1]
    ldr r2, =MAGIC
    cmp r0, #0
    it ge
    cmpge r1, r2
    ite eq
    moveq r0, #1
    movne r0, #2
    adr r12, fe_state
    str r0, [r12]
    cmp r0, #1
    bne fe_out
fe_ready:
    add r0, sp, #0x38
    ldr r3, =SEL_BLOCK
    blx r3
    mov r5, r0
    mov r0, sp
    movs r1, #0
    movs r2, #0x34
    ldr r3, =MEMSET
    blx r3
    ldr r3, =PRESET_OBJ
    blx r3
    mov r1, r5
    mov r2, sp
    ldr r3, =BLOCK_DESC
    blx r3
    cmp r0, #0
    blt fe_out
    ldr r0, [sp]
    lsrs r0, r0, #8
    ldrb r1, [sp, #4]
    orr r0, r0, r1, lsl #24         @ the preset id (-1: an empty block)
    ldr r5, =HDR + 16
    ldrh r1, [r5, #2]
    cmp r0, r1
    bhs fe_out
    add r2, r5, #8
    ldrh r9, [r2, r0, lsl #1]       @ r9 its picture
    movw r1, #0xffff
    cmp r9, r1
    beq fe_out
    ldrh r6, [r5]                   @ r6 S
    cmp r6, #256
    bhi fe_out
    mul r10, r6, r6
    lsl r10, r10, #1
    add r10, r10, #511
    lsr r10, r10, #9                @ r10 sectors a picture
    adr r12, fe_cached
    ldr r3, [r12]
    cmp r3, r9
    beq fe_have
    mvn r3, #0
    str r3, [r12]                   @ invalid while reading
    ldr r1, [r5, #4]
    mla r1, r9, r10, r1             @ its sector
    ldr r0, =CACHE
    mov r2, r10
    ldr r3, =READ
    blx r3
    cmp r0, #0
    blt fe_out
    adr r12, fe_cached
    str r9, [r12]
fe_have:
    ldr r7, =CACHE
    movw r1, #CENTRE_X
    sub r1, r1, r6, lsr #1          @ left x
    movs r2, #CENTRE_Y
    sub r2, r2, r6, lsr #1          @ top y
    movw r3, #800
    mla r1, r2, r3, r1
    add r8, r4, r1, lsl #1          @ r8 the first row in the frame
    mov r2, r6
fe_row:
    mov r3, r6
    mov r0, r8
fe_px:
    ldrh r1, [r7], #2
    strh r1, [r0], #2
    subs r3, #1
    bne fe_px
    movw r12, #ROW
    add r8, r12
    subs r2, #1
    bne fe_row
fe_out:
    add sp, #0x40
    pop {r4-r10, pc}

.ltorg
.balign 4
fe_state:
    .word 0                         @ 0 header not read yet, 1 ready, 2 no store
fe_cached:
    .word 0xffffffff                @ the picture in the cache
