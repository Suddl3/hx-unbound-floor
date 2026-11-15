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
.global fe_img, fe_hook


@ ---- block icons: the picture of each path block's model inside its frame (NAM_EMMC_ART=1) -------------------------
@ fe_hook replaces the DSP meter's Focus View lines at the end of its paint (dm_paint: r5 the home view, r4 the frame; the
@ build, or auto/floor_emmc_art.py live, writes `mov r0, r5; mov r1, r4; bl fe_hook` over them). Focus View on: focus_fill as
@ before. Off: for each of the 32 block image widgets (view + 0x64 + 0x4c0 path + 0x4c slot: visible, 48 x 48 = a block frame
@ image, index at +0) the model's small picture goes inside the stock frame, which stays as it is: the 38 x 38 inside is
@ blanked, the 36 x 36 picture drawn on it (halved in brightness on the bypassed frames, found by the image index in the
@ store's bitmap). The block's preset id comes from the same lookup as the block title's (block id 10 (2 path + slot / 8) +
@ slot % 8 + 1). Icon store at ICON_STORE (auto/floor_emmc_art.py icons): sector 0: "HXPI", +4 u16 S, +6 u16 preset ids,
@ +8 u32 first picture sector, +12 u16 pictures, +14 u16 sectors a picture, +16 bitmap of the Off frame images (1024 bits),
@ +144 u16 map[preset id]; the pictures go to TBL + 0x1000 on first use. No store: nothing is drawn.
.equ ICON_STORE, 0x440000
.equ TBL, 0x29A00000
.equ MAGICI, 0x49505848             @ "HXPI"
.equ HDR_SEC, 10                    @ header sectors; the pictures follow it in RAM
.equ NAM_PID, 1912                  @ header: u16 the NAM block's preset id; +1920 u16 picture[128] by capture slot
.equ NAM_TAB, 1920
.equ COLOURS, 2304                  @ header: u16 category colour[1024] by stock frame image index
.equ PARAM_FN, 0x2813aab9           @ (ctx, block id, query, out): the block title's parameter reader

.thumb_func
fe_hook:                            @ r0 the home view, r1 the frame
    push {r4-r11, lr}
    sub sp, #0x64                   @ 36 + 100: external calls stay 8-byte aligned; [sp] the block descriptor (0x34 B), [sp, #0x38] a pointer,
                                    @ [0x3c] the colour, [0x44] the NAM knob query (12 B), [0x50] its answer (12 B)
    mov r4, r1
    mov r5, r0
    adr.w r12, dm_cfg_p
    ldr r0, [r12]
    ldrb r0, [r0, #2]               @ Focus View (dm_cfg + 2)
    cbz r0, fh_icons
    ldr r3, [r12, #4]
    blx r3                          @ focus_fill (r4 the frame)
    b fh_out
fh_icons:
    ldr r0, [r12, #8]               @ fi_state: 0 not loaded, 1 ready, 2 no store
    cmp r0, #1
    beq fh_go
    bhi fh_out
    ldr r6, =TBL
    mov r0, r6
    ldr r1, =ICON_STORE
    movs r2, #HDR_SEC
    ldr r3, =READ
    blx r3
    cmp r0, #0
    blt fh_fail
    ldr r0, [r6]
    ldr r1, =MAGICI
    cmp r0, r1
    bne fh_fail
    ldrh r8, [r6, #12]
    ldrh r0, [r6, #14]
    mul r8, r0, r8                 @ sectors of pictures
    ldr r9, [r6, #8]                @ their first sector
    add.w r10, r6, #(HDR_SEC * 512)
fh_chunk:
    cmp r8, #0
    beq fh_loaded
    mov r11, r8
    cmp r11, #1024
    it hi
    movhi r11, #1024
    mov r0, r10
    mov r1, r9
    mov r2, r11
    ldr r3, =READ
    blx r3
    cmp r0, #0
    blt fh_fail
    add r10, r10, r11, lsl #9
    add r9, r11
    sub r8, r11
    b fh_chunk
fh_loaded:
    movs r0, #1
    b fh_state
fh_fail:
    movs r0, #2
fh_state:
    adr.w r12, dm_cfg_p
    str r0, [r12, #8]
    cmp r0, #1
    bne fh_out
fh_go:
    ldr r6, =TBL
    movs r7, #0                     @ i: 16 path + slot
fh_loop:
    lsrs r0, r7, #4
    mov.w r1, #0x4c0
    mul r0, r0, r1
    and r1, r7, #15
    movs r2, #0x4c
    mla r0, r1, r2, r0
    add r0, r5
    add.w r8, r0, #0x64             @ the slot's image widget
    ldrb.w r0, [r8, #0x1d]
    cmp r0, #0
    beq fh_next                     @ hidden
    ldr r0, [r8, #0x14]
    cmp r0, #48
    bne fh_next
    ldr r0, [r8, #0x18]
    cmp r0, #48
    bne fh_next                     @ not a block frame (the move frames, the splits, the inputs and outputs)
    ldr r9, [r8]                    @ its image index
    cmp r9, #1024
    bhs fh_next
    lsrs r0, r7, #4
    lsls r0, r0, #1
    and r1, r7, #15
    add.w r0, r0, r1, lsr #3
    movs r2, #10
    mul r0, r0, r2
    and r1, r1, #7
    add r0, r1
    adds r0, #1
    mov r10, r0                     @ the block id
    mov r0, sp
    movs r1, #0
    movs r2, #0x34
    ldr r3, =MEMSET
    blx r3
    ldr r3, =PRESET_OBJ
    blx r3
    mov r1, r10
    mov r2, sp
    ldr r3, =BLOCK_DESC
    blx r3
    cmp r0, #0
    blt fh_next                     @ no block
    ldr r0, [sp]
    lsrs r0, r0, #8
    ldrb r1, [sp, #4]
    orr r0, r0, r1, lsl #24         @ the preset id (-1: an empty block)
    ldrh r1, [r6, #6]
    cmp r0, r1
    bhs fh_next
    ldrh r1, [r6, #NAM_PID]
    cmp r0, r1
    beq fh_nam                      @ a NAM block: the picture of its capture
    add.w r2, r6, #144
    ldrh r10, [r2, r0, lsl #1]      @ its picture
fh_pic:
    movw r1, #0xffff
    cmp r10, r1
    beq fh_next
    lsrs r0, r9, #3
    add.w r1, r6, #16
    ldrb r0, [r1, r0]
    and r1, r9, #7
    lsrs r0, r0, r1
    and r11, r0, #1                 @ 1: a bypassed frame
    add.w r1, r6, #COLOURS
    ldrh r1, [r1, r9, lsl #1]       @ this frame image's category colour (RGB555, 0: none)
    ubfx r0, r1, #10, #5
    lsls r0, r0, #20
    ubfx r2, r1, #5, #5
    orr r0, r0, r2, lsl #10
    and r2, r1, #31
    orr r0, r0, r2                  @ spread: 5-bit channels in 10-bit fields, for one multiply
    cmp r1, #0
    it eq
    moveq r0, #0
    str r0, [sp, #0x3c]
    ldrh r9, [r6, #4]               @ S
    ldrh r1, [r6, #14]
    lsls r1, r1, #9
    mul r1, r10, r1
    add r1, r6
    add.w r10, r1, #(HDR_SEC * 512) @ the picture's pixels
    ldrb r3, [r8, #0x1c]            @ the widget's centre, as the meter's labels find it
    movs r2, #3
    udiv r1, r3, r2
    mls r0, r1, r2, r3
    ldr r2, [r8, #0x14]
    mul r0, r0, r2
    ldr r3, [r8, #0xc]
    sub.w r3, r3, r0, asr #1
    add.w r3, r3, r2, asr #1        @ centre x
    ldr r2, [r8, #0x18]
    mul r1, r1, r2
    ldr r0, [r8, #0x10]
    sub.w r0, r0, r1, asr #1
    add.w r0, r0, r2, asr #1        @ centre y
    sub.w r1, r3, r9, lsr #1
    subs r1, #1                     @ the blanked square's left
    sub.w r2, r0, r9, lsr #1
    subs r2, #1                     @ its top
    movw r12, #800
    mla r2, r2, r12, r1
    add.w r12, r4, r2, lsl #1       @ its first pixel
    str r12, [sp, #0x38]
    ldr r1, [sp, #0x3c]
    cbz r1, fh_noring               @ no category colour: the frame stays as it is
    lsrs r2, r9, #1
    rsb r2, r2, #23                 @ the frame (48 square) starts this many pixels before the blanked square
    movw r0, #1602
    mul r2, r2, r0
    sub.w r0, r12, r2
    bl fh_ring                      @ the frame's outline in the category colour
fh_noring:
    ldr r0, [sp, #0x38]
    adds r2, r9, #2
    movs r1, #0
fh_er_row:
    mov r12, r0
    adds r3, r9, #2
fh_er_px:
    strh r1, [r12], #2
    subs r3, #1
    bne fh_er_px
    add.w r0, r0, #1600
    subs r2, #1
    bne fh_er_row
    ldr r0, [sp, #0x38]
    addw r0, r0, #1602             @ one row and one pixel in: the picture's first pixel
    movw lr, #0x7fff
    cmp r11, #0
    it ne
    movwne lr, #0x3def              @ a bypassed frame: half the brightness
    mov r2, r9
fh_ar_row:
    mov r12, r0
    mov r3, r9
fh_ar_px:
    ldrh r1, [r10], #2
    lsrs r1, r1, r11
    ands r1, r1, lr
    strh r1, [r12], #2
    subs r3, #1
    bne fh_ar_px
    add.w r0, r0, #1600
    subs r2, #1
    bne fh_ar_row
    b fh_next
fh_nam:                             @ r10 the block id: knob 0 (the capture slot, 1..128) through the title's reader
    mvn r1, #1
    str r1, [sp, #0x44]
    movs r1, #0
    str r1, [sp, #0x48]
    str r1, [sp, #0x4c]
    str r1, [sp, #0x50]
    str r1, [sp, #0x54]
    str r1, [sp, #0x58]
    ldr r3, =PRESET_OBJ
    blx r3
    mov r1, r10
    add r2, sp, #0x44
    add r3, sp, #0x50
    ldr lr, =PARAM_FN
    blx lr
    ldrb r0, [sp, #0x54]
    ldr r1, [sp, #0x50]
    lsls r0, r0, #24
    orr r0, r0, r1, lsr #8
    subs r0, #1
    cmp r0, #128
    bhs fh_next
    add.w r1, r6, #NAM_TAB
    ldrh r10, [r1, r0, lsl #1]
    b fh_pic
fh_next:
    adds r7, #1
    cmp r7, #32
    bne fh_loop
fh_out:
    add sp, #0x64
    pop {r4-r11, pc}

@ fh_ring: the outline of a 48 x 48 block frame (r0 its first pixel, r1 the category colour spread as above): the 4 pixel band
@ round the edge, where a pixel that is a grey of 1..16 (the stock outline 16, its edge pixels and the bypassed frames' dimmer
@ greys) becomes the category colour times grey / 16. Brighter greys (the selected frame's white) and everything else stay.
fh_ring:
    push {r4-r9, lr}
    movw r4, #0xfc3f
    movt r4, #0x03f0                @ the fields' mask after the shift
    movw r5, #0x2008
    movt r5, #0x0080                @ 8 in each field: rounding
    movs r6, #0
fr_row:
    mov r7, r0
    cmp r6, #4
    blo fr_full
    cmp r6, #44
    bhs fr_full
    movs r8, #4
    bl fr_run
    add.w r7, r7, #80
    movs r8, #4
    bl fr_run
    b fr_next
fr_full:
    movs r8, #48
    bl fr_run
fr_next:
    add.w r0, r0, #1600
    adds r6, #1
    cmp r6, #48
    bne fr_row
    pop {r4-r9, pc}
fr_run:                             @ r7 pixel, r8 count
    ldrh r2, [r7]
    and r3, r2, #31
    ubfx r9, r2, #5, #5
    cmp r3, r9
    bne fr_skip
    ubfx r9, r2, #10, #5
    cmp r3, r9
    bne fr_skip
    subs r9, r3, #1
    cmp r9, #15
    bhi fr_skip
    mul r2, r1, r3
    add r2, r5
    lsrs r2, r2, #4
    and r2, r2, r4
    lsrs r3, r2, #10
    and r3, r3, #0x7c00
    lsrs r9, r2, #5
    and r9, r9, #0x3e0
    orr r3, r3, r9
    and r9, r2, #31
    orr r3, r3, r9
    strh r3, [r7]
fr_skip:
    adds r7, #2
    subs r8, #1
    bne fr_run
    bx lr

.equ MEMSET_, 0
.ltorg
.org 0x3c0
dm_cfg_p:
    .word 0                         @ the meter's dm_cfg (the build / the host fills it)
    .word 0                         @ the meter's focus_fill, Thumb bit set
    .word 0                         @ fi_state
.org 0x400
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
