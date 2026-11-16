@ emmc_art.s: Focus View's picture from the eMMC, uploaded at run time (auto/floor_emmc_art.py load); the pictures
@ themselves are stored once in the eMMC past every partition (floor_emmc_art.py write) and stay there.
@ The host copies the store's header to hdr_p (RAM) and writes a jump to emmc_img over focus_img's start in the DSP
@ meter module, while Focus View is off. emmc_img is entered as focus_img is (r4 the frame, paint task): it finds the
@ selected block's preset id as focus_pid does, maps it to a picture, reads that picture from the eMMC into the cache
@ (only when it changed: the firmware's own sector read, under the card's mutex, as the stock image draw streams its
@ pixels in the paint task too) and copies it into the frame, centred on dm_imgs slot 0's x, top at its y.
@ Header (RAM copy): +0 u16 picture size S (S x S RGB555, rows from the top), +2 u16 preset ids in the map,
@ +4 u32 the first picture's sector (each picture starts on a sector), +8 u16 map[preset id] (0xffff none).
.syntax unified
.thumb
.text
.equ SEL_BLOCK, 0x281043e9
.equ MEMSET, 0x28155f35
.equ PRESET_OBJ, 0x28114a1d
.equ BLOCK_DESC, 0x28148ccd
.equ READ, 0x1000504d               @ (buffer, sector, count) -> < 0 on error
.equ ROW, 1600
.global emmc_img

.thumb_func
emmc_img:                           @ r4 the frame
    push {r4-r10, lr}
    sub sp, #0x40                   @ 32 + 64: external calls stay 8-byte aligned
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
    blt ei_out
    ldr r0, [sp]
    lsrs r0, r0, #8
    ldrb r1, [sp, #4]
    orr r0, r0, r1, lsl #24         @ the preset id (-1: an empty block)
    ldr r5, hdr_p
    ldrh r1, [r5, #2]
    cmp r0, r1
    bhs ei_out
    add r2, r5, #8
    ldrh r9, [r2, r0, lsl #1]       @ r9 its picture
    movw r1, #0xffff
    cmp r9, r1
    beq ei_out
    ldrh r6, [r5]                   @ r6 S
    mul r10, r6, r6
    lsl r10, r10, #1
    add r10, r10, #511
    lsr r10, r10, #9                @ r10 sectors a picture
    adr r12, cached
    ldr r3, [r12]
    cmp r3, r9
    beq ei_have
    mvn r3, #0
    str r3, [r12]                   @ invalid while reading
    ldr r1, [r5, #4]
    mla r1, r9, r10, r1             @ its sector
    ldr r0, cache_p
    mov r2, r10
    ldr r3, =READ
    blx r3
    cmp r0, #0
    blt ei_out
    adr r12, cached
    str r9, [r12]
ei_have:
    ldr r7, cache_p
    ldr r3, dm_imgs_p
    ldrh r1, [r3, #2]               @ centre x
    ldrh r2, [r3, #4]               @ top y
    sub r1, r1, r6, lsr #1
    movw r3, #800
    mla r1, r2, r3, r1
    add r8, r4, r1, lsl #1          @ r8 the first row in the frame
    mov r2, r6
ei_row:
    mov r3, r6
    mov r0, r8
ei_px:
    ldrh r1, [r7], #2
    strh r1, [r0], #2
    subs r3, #1
    bne ei_px
    movw r12, #ROW
    add r8, r12
    subs r2, #1
    bne ei_row
ei_out:
    add sp, #0x40
    pop {r4-r10, pc}

.ltorg
.balign 4
cached:
    .word 0xffffffff                @ the picture in the cache
dm_imgs_p:
    .word 0                         @ the meter's dm_imgs (host-filled)
hdr_p:
    .word 0x29900000                @ the header's RAM copy
cache_p:
    .word 0x29910000                @ one picture (up to 256 x 256: 128 KB)
