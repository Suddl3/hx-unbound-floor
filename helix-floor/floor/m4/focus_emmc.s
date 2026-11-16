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
.equ BGCACHE, 0x29940000            @ one background, up to 0xc0000 B (to the icon store's RAM at TBL)
.equ BGMAX, 0xc0000
.equ HDR_SECS, 12                   @ header sectors read on the first call (4096 B held set A only)
.equ SETB_MAP, 3072                 @ set B (theme pack): u16 map[preset id] here, u8 slot[preset id] at SETB_SLOT (ids <= 1000)
.equ SETB_SLOT, 5072
.equ BG_HDR, 2048                   @ in the header read at HDR: "HXBG", u16 count, u16 sectors a background, u32 first sector,
.equ MAGICBG, 0x47425848            @ u16 y0, u16 rows, then u8 slot[preset id] (0xff none); the PC side is bg_store.py
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
.equ MAXSEC, 10230                  @ picture sectors that fit: 0x29a00000 + 10 sectors up to 0x29f00000 (live code)
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
    ldrh r1, [r6, #4]               @ the store's own numbers are checked before they size a read or a copy: S 1..44 (the
    subs r2, r1, #1                 @ frame's inside), the sectors a picture holds S x S pixels, and the pictures fit the RAM
    cmp r2, #43                     @ set aside (TBL up to the live code at 0x29f00000)
    bhi fh_fail
    mul r1, r1, r1
    lsls r1, r1, #1
    lsls r2, r0, #9
    cmp r1, r2
    bhi fh_fail
    mul r8, r0, r8                 @ sectors of pictures
    movw r1, #MAXSEC
    cmp r8, r1
    bhi fh_fail
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
    bl fe_old                       @ first take away the white border this slot had in this frame buffer last time (a block gone, moved or
    lsrs r0, r7, #4                 @ not selected any more, a new preset): the stock paint does not clean outside a block's own image
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
    ldrh r1, [r6, #12]
    cmp r10, r1
    bhs fh_next                     @ a map entry past the stored pictures
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
    lsrs r2, r9, #1
    rsb r2, r2, #23                 @ the frame (48 square) starts this many pixels before the blanked square
    movw r0, #1602
    mul r2, r2, r0
    sub.w r0, r12, r2               @ the frame's first pixel
    ldrh r1, [r0, #48]              @ the top edge's middle: the stock outline, a grey of 31 (white) on the selected frame
    and r1, r1, #31
    cmp r1, #24
    ite hs
    movhs r1, #1
    movlo r1, #0
    str r1, [sp, #0x40]             @ 1: the selected block
    str r0, [sp, #0x60]
    cbz r1, fh_nosel
    bl fe_fbrow
    str r0, [r2, r7, lsl #2]        @ remember where this slot's border is drawn (cleared by fe_old at the next paint)
fh_nosel:
    ldr r1, [sp, #0x3c]
    cbz r1, fh_noring               @ no category colour: the frame stays as it is
    bl fh_ring                      @ the frame's outline in the category colour
fh_noring:
    ldr r0, [sp, #0x60]
    ldr r1, [sp, #0x40]
    bl fh_outer                     @ the selected frame's second border, white, outside the first (black again when not selected)
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
    ldr r1, [sp, #0x40]
    lsls r1, r1, #1
    orr r1, r1, r11                 @ selected * 2 + bypassed
    adr.w r8, dm_cfg_p
    add.w r8, r8, r1, lsl #3
    ldr lr, [r8, #0x10]             @ the state's dim_mask
    ldr r8, [r8, #0xc]              @ and dim_shift
    mov r2, r9
fh_ar_row:
    mov r12, r0
    mov r3, r9
fh_ar_px:
    ldrh r1, [r10], #2
    lsrs r11, r1, r8
    ands r11, r11, lr
    subs r1, r1, r11                @ v - ((v >> dim_shift) & dim_mask): shift 1 mask 0x3def = half, shift 2 mask 0x1ce7 = three quarters, mask 0 = full
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
@ round the edge, where every grey pixel (the stock outline: a grey of 16 in 5 bits on a plain frame, 31 = white on the selected
@ one, 6 on the bypassed ones, in between at the edges) becomes the category colour: all of it on an enabled frame (selected or
@ not), 6/32 of it on a bypassed one (a category without a colour, 0, is left as it is).
fh_ring:
    push {r4-r9, lr}
    movw r4, #0x7c1f
    movt r4, #0x01f0                @ the fields' mask after the shift by 5
    movw r5, #0x4010
    movt r5, #0x0100                @ 16 in each field: rounding
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
    cmp r3, #0
    beq fr_skip
    cmp r11, #0
    bne fr_byp
    cmp r3, #16                     @ an enabled frame: the whole colour (the stock outline is a grey of 16, white 31 when selected)
    it hi
    movhi r3, #16
    lsls r3, r3, #1
    b fr_lin
fr_byp:
    cmp r3, #6                      @ a bypassed frame: 6/32 of the colour, selected or not
    it hi
    movhi r3, #6
fr_lin:
    mul r2, r1, r3
    add r2, r5
    lsrs r2, r2, #5
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

@ fh_outer: the selected frame's second border (r0 the frame's first pixel, r1 = 1 selected): a 2 pixel white border one pixel outside the
@ 48 x 48 frame (a black gap between the two), rounded to follow its corners (outer radius 9 on the 54 x 54 box; the tables
@ fo_tab give, for the top 9 rows, the first column of the border and of its inner edge; the bottom 9 rows mirror them). Every call
@ first wipes the whole square ring (the stock paint does not clean outside a block's own image): black, except at the path
@ line's middle rows (frame rows 22..25), where the line's own pixel (the one just outside the ring) is put back.
fh_outer:
    push {r4-r9, lr}
    mov r3, r1
    movs r4, #0
    movw r1, #4806                  @ 3 rows and 3 columns before the frame
    subs r5, r0, r1
    movs r6, #0
fo_row:
    cmp r6, #3
    blo fo_full
    cmp r6, #51
    bhs fo_full
    subs r7, r6, #25                @ frame row 22 is row index 25
    cmp r7, #4
    bhs fo_side
    ldrh r2, [r5, #-2]
    strh r2, [r5]
    strh r2, [r5, #2]
    strh r2, [r5, #4]
    ldrh r2, [r5, #108]
    strh r2, [r5, #102]
    strh r2, [r5, #104]
    strh r2, [r5, #106]
    b fo_next
fo_side:
    strh r4, [r5]
    strh r4, [r5, #2]
    strh r4, [r5, #4]
    strh r4, [r5, #102]
    strh r4, [r5, #104]
    strh r4, [r5, #106]
    b fo_next
fo_full:
    mov r7, r5
    movs r2, #54
fo_px:
    strh r4, [r7], #2
    subs r2, #1
    bne fo_px
fo_next:
    add.w r5, r5, #1600
    adds r6, #1
    cmp r6, #54
    bne fo_row
    cmp r3, #0
    beq fo_done
    movw r4, #0x7fff                @ white
    movw r1, #0x5180
    movt r1, #1                     @ 54 rows of 1600 bytes
    subs r5, r5, r1                 @ back to row -3
    adr.w r8, fo_tab
    movw r12, #1600
    movs r6, #0
fo_dr:
    cmp r6, #9
    bhs fo_mid
    ldrb r7, [r8, r6]               @ the border's first column in this row
    adds r1, r8, #9
    ldrb r9, [r1, r6]               @ its inner edge's first column in this row (255: none yet)
    mul r1, r6, r12
    add r1, r5                      @ this row (top)
    rsb r2, r6, #53
    mul r2, r2, r12
    add r2, r5                      @ the mirrored row (bottom)
    cmp r6, #2
    bhs fo_cor
    lsls r7, r7, #1
    rsb r9, r7, #54                 @ the span between the two ends, in pixels (54 - 2 skip)
    add r0, r1, r7
    mov r3, r9
    bl fo_fill
    add r0, r2, r7
    mov r3, r9
    bl fo_fill
    b fo_dnext
fo_cor:
    subs r9, r9, r7                 @ the width of each end piece
    lsls r7, r7, #1
    add r0, r1, r7
    mov r3, r9
    bl fo_fill
    add r0, r2, r7
    mov r3, r9
    bl fo_fill
    rsb r7, r7, #108
    sub.w r7, r7, r9, lsl #1        @ the right piece's first byte
    add r0, r1, r7
    mov r3, r9
    bl fo_fill
    add r0, r2, r7
    mov r3, r9
    bl fo_fill
fo_dnext:
    adds r6, #1
    b fo_dr
fo_mid:
    movs r6, #9
fo_mr:
    mul r1, r6, r12
    add r1, r5
    strh r4, [r1]
    strh r4, [r1, #2]
    strh r4, [r1, #104]
    strh r4, [r1, #106]
    adds r6, #1
    cmp r6, #45
    bne fo_mr
fo_done:
    pop {r4-r9, pc}
fo_fill:                            @ r0 pixel, r3 count
    strh r4, [r0], #2
    subs r3, #1
    bne fo_fill
    bx lr
.balign 4
fo_tab:
    .byte 6, 4, 3, 2, 1, 1, 0, 0, 0
    .byte 255, 255, 6, 5, 4, 3, 2, 2, 2

.equ MEMSET_, 0
.ltorg
.org 0x540
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
    movs r2, #HDR_SECS
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
    mov r8, r0
    bl fe_bg                        @ the model's background first (r0 its preset id, r4 the frame); the picture goes over it
    mov r0, r8
    add r2, r5, #8                  @ the picture map of set A (the header's own)
    ldr r3, =HDR + BG_HDR + 16
    ldrh r3, [r3]                   @ the mode: 1 = set B (its own map at SETB_MAP), anything else (an old store: 0) = set A
    cmp r3, #1
    bne fe_seta
    ldr r2, =HDR + SETB_MAP
fe_seta:
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

@ fe_bg: r0 the preset id, r4 the frame: the background of the model's slot (sectors read into BGCACHE when the slot changes) is
@ copied into rows y0 .. y0 + rows of the frame. Everything the header says is checked first (magic, count, slot, rows, sectors).
@ No background section, slot 0xff or a failed read: nothing drawn (the plain black Focus View). Keeps r4-r10.
fe_bg:
    push {r5-r9, lr}                @ 6 words: external calls stay 8-byte aligned (fe_img's frame is)
    ldr r5, =HDR + BG_HDR
    ldr r1, [r5]
    ldr r2, =MAGICBG
    cmp r1, r2
    bne fb_out
    ldr r1, =HDR + 18               @ the header's preset id count
    ldrh r1, [r1]
    cmp r1, #1000                   @ the slot bytes must stay inside the header sectors
    bhi fb_out
    cmp r0, r1
    bhs fb_out
    add r1, r5, #24                 @ set A's slots (the section's own: after magic .. rows, mode, spare)
    ldrh r2, [r5, #16]              @ the mode
    cmp r2, #1
    bne fb_seta
    ldr r1, =HDR + SETB_SLOT
fb_seta:
    ldrb r6, [r1, r0]               @ r6 the slot
    ldrh r1, [r5, #4]               @ the count
    cmp r1, #250
    bhi fb_out
    cmp r6, r1
    bhs fb_out                      @ 0xff: none
    ldrh r7, [r5, #14]              @ r7 rows
    ldrh r8, [r5, #12]              @ r8 y0
    cmp r7, #0
    beq fb_out
    add r0, r7, r8
    cmp r0, #480
    bhi fb_out
    movw r0, #1600
    mul r9, r7, r0                  @ r9 bytes drawn
    ldr r1, =BGMAX
    cmp r9, r1
    bhi fb_out
    ldrh r0, [r5, #6]               @ sectors a background
    add r1, r9, #511
    lsrs r1, r1, #9
    cmp r0, r1
    blo fb_out
    cmp r0, #1024
    bhi fb_out
    adr.w r12, fe_bgcached
    ldr r1, [r12]
    cmp r1, r6
    beq fb_draw
    mvn r1, #0
    str r1, [r12]                   @ invalid while reading
    ldr r1, [r5, #8]
    mla r1, r6, r0, r1              @ its sector
    mov r2, r0
    ldr r0, =BGCACHE
    ldr r3, =READ
    blx r3
    cmp r0, #0
    blt fb_out
    adr.w r12, fe_bgcached
    str r6, [r12]
fb_draw:
    movw r0, #1600
    mul r0, r8, r0
    add r0, r4                      @ the frame's row y0
    ldr r1, =BGCACHE
    lsrs r2, r9, #2                 @ words
fb_copy:
    ldr r3, [r1], #4
    str r3, [r0], #4
    subs r2, #1
    bne fb_copy
fb_out:
    pop {r5-r9, pc}

@ fe_row: r4 the frame -> r2 its row of 32 words (one per path + slot): the first pixel of the frame whose white border is drawn there, 0 none.
@ Two frame buffers are drawn in turn and each keeps its own pixels, so each has a row (found by its address, taken on first sight).
fe_fbrow:
    push {r3, lr}
    adr.w r2, fe_fbs
    ldr r3, [r2]
    cmp r3, r4
    beq fr_a
    ldr r3, [r2, #4]
    cmp r3, r4
    beq fr_b
    ldr r3, [r2]
    cbnz r3, fr_new_b
    str r4, [r2]
    b fr_a
fr_new_b:
    str r4, [r2, #4]
fr_b:
    adr.w r2, fe_rows
    add.w r2, r2, #128
    pop {r3, pc}
fr_a:
    adr.w r2, fe_rows
    pop {r3, pc}

fe_old:                             @ r7 the slot, r4 the frame: wipe the border this slot has in this buffer (fh_outer, not selected)
    push {r0-r3, lr}
    bl fe_fbrow
    ldr r0, [r2, r7, lsl #2]
    cbz r0, fo_none
    movs r1, #0
    str r1, [r2, r7, lsl #2]
    bl fh_outer
fo_none:
    pop {r0-r3, pc}

.ltorg
.org 0x800                          @ (focus_emmc.py LIT: the code before fe_img outgrew 0x500)
dm_cfg_p:
    .word 0                         @ the meter's dm_cfg (the build / the host fills it)
    .word 0                         @ the meter's focus_fill, Thumb bit set
    .word 0                         @ fi_state
    .word 0, 0                      @ dim (shift, mask) of the art, by state (poked live to tune): enabled: full
    .word 1, 0x3def                 @ bypassed, not selected: half
    .word 0, 0                      @ on, selected: full
    .word 1, 0x3def                 @ bypassed, selected: half
.balign 4
fe_fbs:
    .word 0, 0                      @ the two frame buffers seen
fe_rows:
    .space 256                      @ 2 x 32 words
fe_state:
    .word 0                         @ 0 header not read yet, 1 ready, 2 no store
fe_cached:
    .word 0xffffffff                @ the picture in the cache
fe_bgcached:
    .word 0xffffffff                @ the background (slot) in BGCACHE
