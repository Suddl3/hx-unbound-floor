@ ram_art.s: Focus View's picture from RAM, uploaded at run time (auto/floor_ram_art.py); nothing installed.
@ The host writes the pictures to PIC_BASE (free SDRAM) and a jump to ram_img over focus_img's start in the DSP meter
@ module (local SRAM), while Focus View is off. ram_img is entered as focus_img is (r4 the frame, from focus_fill in
@ the paint task): it finds the selected block's preset id as focus_pid does, looks its picture up in the RAM table and
@ copies it into the frame, centred on dm_imgs slot 0's x, top at its y.
@ RAM table at pic_base: +0 u16 picture size S (S x S, RGB555 rows from the top), +2 u16 preset ids in the map,
@ +4 u32 offset of the pixels from pic_base, +8 u16 map[preset id] = picture index (0xffff none).
.syntax unified
.thumb
.text
.equ SEL_BLOCK, 0x281043e9          @ (&out) -> the selected block's id
.equ MEMSET, 0x28155f35
.equ PRESET_OBJ, 0x28114a1d         @ () -> the edit buffer's preset
.equ BLOCK_DESC, 0x28148ccd         @ (preset, block id, desc) -> < 0 none; desc +1 (24 bits) and +4 (8 bits): the preset id
.equ ROW, 1600                      @ a frame row: 800 RGB555 pixels
.global ram_img

.thumb_func
ram_img:                            @ r4 the frame
    push {r4-r8, lr}
    sub sp, #0x40                   @ 24 + 64: external calls stay 8-byte aligned, as in focus_img
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
    blt ri_out
    ldr r0, [sp]
    lsrs r0, r0, #8
    ldrb r1, [sp, #4]
    orr r0, r0, r1, lsl #24         @ the preset id (-1: an empty block)
    ldr r5, pic_base
    ldrh r1, [r5, #2]
    cmp r0, r1
    bhs ri_out
    add r2, r5, #8
    ldrh r0, [r2, r0, lsl #1]       @ its picture
    movw r1, #0xffff
    cmp r0, r1
    beq ri_out
    ldrh r6, [r5]                   @ S
    mul r1, r6, r6
    lsls r1, r1, #1                 @ bytes a picture
    ldr r2, [r5, #4]
    add r2, r5
    mla r7, r0, r1, r2              @ r7 its pixels
    ldr r3, dm_imgs_p
    ldrh r1, [r3, #2]               @ centre x
    ldrh r2, [r3, #4]               @ top y
    sub r1, r1, r6, lsr #1
    movw r3, #800
    mla r1, r2, r3, r1
    add r8, r4, r1, lsl #1          @ r8 the first row in the frame
    mov r2, r6
ri_row:
    mov r3, r6
    mov r0, r8
ri_px:
    ldrh r1, [r7], #2
    strh r1, [r0], #2
    subs r3, #1
    bne ri_px
    movw r12, #ROW
    add r8, r12
    subs r2, #1
    bne ri_row
ri_out:
    add sp, #0x40
    pop {r4-r8, pc}

.ltorg
.balign 4
dm_imgs_p:
    .word 0                         @ the meter's dm_imgs (host-filled)
pic_base:
    .word 0x29900000
