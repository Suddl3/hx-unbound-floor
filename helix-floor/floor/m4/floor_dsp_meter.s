@ floor_dsp_meter.s - Helix Floor DSP meter, ported from HXtra's dsp_meter.s (wisemandenny/hxtra, GPL-3.0).
@ The home view shows each block's DSP cost in whole per cent under its icon, in grey, and each path's blocks' sum against
@ what blocks may use on its DSP (90% less the firmware's fixed 15%) as "P1 used/75" and "P2 used/75", in white, in the
@ title bar left of the snapshot icon (the paths' own ends move with the layout: a full path 2 lifts its output), or as
@ "Pn" and a bar (green, yellow, red). Global Settings > Preferences page 2 sets them: DSP Meter / Blocks (Off/On, ID 74)
@ and DSP Meter / Paths (Off/Numbers/Meters, ID 122); dm_text gives their value strings.
@ The costs are the firmware's own declared ones (hundredths of a per cent), not measured load.
@
@ dm_paint takes the home view's paint function pointer (the literal 0x2809372c, which the boot registers at 0x28093592):
@ it wipes (black) the labels that changed or went, runs the stock paint, which draws over the wipes whatever its own
@ changes put there (a moved path line, an icon), then draws every label into the same frame. The Floor's frame is
@ 800 x 480 RGB555, two buffers drawn in turn; the labels live outside every widget, so each buffer keeps the labels it
@ got (dm_track).
@
@ Home view (0x2818c21c): path p's 16 block slots are image widgets at view + 0x64 + 0x4c0 p + 0x4c k (k 0..7 row A,
@ 8..15 row B, as the layout 0x280d38a0 places them); block record 16 p + k in the DSP model (the ID map 0x2813dfc2).
.syntax unified
.thumb
.fpu fpv4-sp-d16

.equ POST_A, 0x28175a08             @ the UI event post's (0x2808b668) first two literals
.equ POST_B, 0x281759d0
.equ POST_ENTRY, 0x2808b669         @ the UI event post, as called (through the trampoline, so dm_event again)
.equ POST_BODY, 0x2808b671          @ it goes on here (its first 8 bytes are replayed by dm_event)
.equ HOME_VIEW, 0x2818c21c          @ its word 0 is 1 while the home view is the active screen
.equ FOCUS_Y, 52                    @ Focus View blanks the paths: below the title bar ...
.equ FOCUS_H, 288                   @ ... down to the bottom panel (y 340)
.equ IMG_WIDGET_PAINT, 0x2808e56d  @ (frame, -, widget): the image widget's paint
.equ IMG_LOOKUP, 0x2808af15         @ (index, &handle, &size): the image store's lookup, < 0 when missing
.equ IMG_DRAW, 0x2808cbed           @ (frame, handle, x, y; stack w, h, flag): draws an image, as the image widget paint does
.equ SEL_PIC, 4094                  @ dm_imgs index meaning the selected block's picture (floor_art.py sends 4094 for "sel")
.equ ART_BASE, 1093                 @ NAM_ART=map: Entry 9 item ART_BASE + preset id is that model's picture (stage_art.py)
.equ N_PIDS, 833                    @ preset ids 0..832
.equ SEL_BLOCK, 0x281043e9          @ (out byte) -> the selected block's id
.equ MEMSET, 0x28155f35             @ (dst, byte, n)
.equ PRESET_OBJ, 0x28114a1d         @ () -> the current preset
.equ BLOCK_DESC, 0x28148ccd         @ (preset, block id, desc 0x34 B) -> < 0 when none
.equ STOCK_PAINT, 0x280d6be9        @ the home view's paint (fb, view)
.equ GET_VALUE, 0x28150829          @ (id, out): a Global Setting, value at out + 4
.equ ID_BLOCKS, 74                  @ Preferences "DSP Meter / Blocks": a spare main-store ID, stock limits int 0..1, default 1
.equ ID_PATHS, 122                  @ Preferences "DSP Meter / Paths": spare, stock limits int 0..2, default 1
.equ TEXT_REST, 0x280941c9          @ the value-text function (id, value, out, size) after its first 8 bytes
.equ DSP_MODEL, 0x284e5758          @ -> the DSP model: block records of 0x54 bytes at +0x14, 32 of them
.equ DSP_LOCK, 0x2813e63d           @ (0): its lock (mutex at model + 8), as the stock lookups take it
.equ DSP_UNLOCK, 0x2813e655
.equ NODES, 0x5060                  @ model + this -> the node table (0x28140484's container + 4)
.equ WLOCK, 0x2808ee39              @ the widget lock (0x28178e6c), never held with the DSP model's
.equ WUNLOCK, 0x2808ee45
.equ FB0, 0x285a3f50                @ the first framebuffer; the second is 0xbb800 on
.equ SLOTS, 0x64
.equ PATH_SLOTS, 0x4c0
.equ WIDGET, 0x4c
.equ W, 800
.equ H, 480
.equ BUDGET, 75                     @ per cent of a DSP blocks may use: the limit 9000 less the fixed 1500, in hundredths
.equ SCALE, 2                       @ a glyph is 3 x 5 cells of SCALE pixels, a cell's gap between glyphs
.equ ADV, 4 * SCALE
.equ TALL, 5 * SCALE
.equ GAP, 6                         @ between an icon's bottom and its label (the selection frame is outside the icon)
.equ GREY, 0x6318                   @ RGB555 (24, 24, 24)
.equ WHITE, 0x7fff
.equ TOTAL_WIDE, 9 * ADV - SCALE   @ "P2 999/75"
.equ TOTAL_RIGHT1, 736              @ P2 right-aligned here, the snapshot icon from x ~745
.equ TOTAL_RIGHT0, TOTAL_RIGHT1 - TOTAL_WIDE - 16
.equ TOTAL_TOP, 24                  @ centred on the title bar's icon (y ~12..46); a 16-character name ends near x 530
.equ NTRACK, 34                     @ 32 block labels and 2 totals a buffer
.equ VALID, 0x80000000              @ a label: value | left << 10 | top << 20 | PATH2 | TOTAL | VALID
.equ TOTAL, 0x40000000
.equ PATH2, 0x20000000
.equ METER, 0x200                  @ a total's value bit 9: drawn as "Pn" and a bar (value then 0..511)
.equ BAR_X, 20                      @ the bar after "Pn"
.equ BAR_W, 50
.equ GREEN, 0x0300                  @ RGB555 (0, 24, 0): up to 60% of the 75
.equ YELLOW, 0x7f00                 @ (31, 24, 0): to 90%
.equ RED, 0x7c00                    @ (31, 0, 0)
.equ EDGE, 0x4210                   @ (16, 16, 16)
.equ G_SLASH, 10                    @ glyphs past the digits
.equ G_P, 11
.equ G_SPACE, 12

.thumb_func
dm_paint:                           @ r0 the frame, r1 the home view
    push {r4-r11, lr}
    sub sp, #140                    @ 0 the 32 records' costs (-1 none), 128 the stock's result, 132 the model
    mov r4, r0
    mov r5, r1
    adr.w r6, dm_cfg                @ the two Preferences settings, as stored now (a failed read keeps the last)
    movs r0, #ID_BLOCKS
    add r1, sp, #128
    ldr r3, =GET_VALUE
    blx r3
    cmp r0, #0
    blt dm_cfg_paths
    ldr r0, [sp, #132]
    cmp r0, #0
    it ne
    movne r0, #1
    strb r0, [r6]
dm_cfg_paths:
    movs r0, #ID_PATHS
    add r1, sp, #128
    ldr r3, =GET_VALUE
    blx r3
    cmp r0, #0
    blt dm_cfg_read
    ldr r0, [sp, #132]
    cmp r0, #2
    it hi
    movhi r0, #2
    strb r0, [r6, #1]
dm_cfg_read:
    movs r6, #0
    mvn r0, #0
dm_none:
    str.w r0, [sp, r6, lsl #2]
    adds r6, #1
    cmp r6, #32
    bne dm_none
    ldr r7, =DSP_MODEL
    ldr r7, [r7]
    str r7, [sp, #132]
    cbz r7, dm_costed
    movs r0, #0
    ldr r3, =DSP_LOCK
    blx r3
    movs r6, #0
dm_cost:
    mov r0, r6
    bl cost_of
    str.w r0, [sp, r6, lsl #2]
    adds r6, #1
    cmp r6, #32
    bne dm_cost
    movs r0, #0
    ldr r3, =DSP_UNLOCK
    blx r3
dm_costed:
    ldr r3, =WLOCK
    blx r3
    adr.w r9, dm_track
    ldr r3, =FB0
    cmp r4, r3
    it ne
    addne r9, r9, #(NTRACK * 4)
    movs r6, #0                     @ i: 16 p + k, then 32 + p for the totals
dm_item:
    movs r10, #0                    @ the label this buffer should have
    cmp r6, #32
    bhs dm_total
    adr.w r0, dm_cfg
    ldrb r0, [r0]
    cmp r0, #0
    beq dm_place                    @ block labels off
    ldr.w r11, [sp, r6, lsl #2]
    cmp r11, #0
    blt dm_place
    lsrs r0, r6, #4
    mov.w r1, #PATH_SLOTS
    mul r0, r0, r1
    and r1, r6, #15
    movs r2, #WIDGET
    mla r0, r1, r2, r0
    add r0, r5
    add.w r8, r0, #SLOTS            @ the slot's image widget
    ldrb.w r0, [r8, #0x1d]
    cmp r0, #0
    beq dm_place                    @ hidden
    adds r0, r11, #50
    movs r1, #100
    udiv r11, r0, r1                @ the cost in per cent, rounded
    ldrb.w r3, [r8, #0x1c]          @ the anchor 0..8: column picks no, half or whole width left of x, row the same above y
    movs r2, #3
    udiv r1, r3, r2
    mls r0, r1, r2, r3
    ldr r2, [r8, #0x14]
    mul r0, r0, r2
    ldr r3, [r8, #0xc]
    sub.w r3, r3, r0, asr #1
    add.w r3, r3, r2, asr #1        @ the icon's centre x
    ldr r2, [r8, #0x18]
    mul r1, r1, r2
    ldr r0, [r8, #0x10]
    sub.w r0, r0, r1, asr #1
    add r0, r2
    add.w r8, r0, #GAP              @ the label's top
    mov r0, r11
    bl ndigits
    lsls r0, r0, #3
    subs r0, #SCALE                 @ its width
    sub.w r3, r3, r0, asr #1        @ its left
    cmp r3, #0
    blt dm_place
    add r0, r3
    cmp.w r0, #W
    bgt dm_place
    cmp.w r8, #0
    blt dm_place
    add.w r0, r8, #TALL
    cmp.w r0, #H
    bgt dm_place
    orr.w r10, r11, r3, lsl #10
    orr.w r10, r10, r8, lsl #20
    orr.w r10, r10, #VALID
    b dm_place
dm_total:                           @ path i - 32: its blocks' sum, each rounded as shown
    ldr r0, [sp, #132]
    cmp r0, #0
    beq dm_place                    @ no model: none
    adr.w r0, dm_cfg
    ldrb r0, [r0, #1]
    cmp r0, #0
    beq dm_place                    @ path totals off
    sub.w r0, r6, #32
    lsls r7, r0, #4
    add.w r8, r7, #16
    movs r11, #0
dm_sum:
    ldr.w r0, [sp, r7, lsl #2]
    cmp r0, #0
    blt dm_summed
    adds r0, #50
    movs r1, #100
    udiv r0, r0, r1
    add r11, r0
dm_summed:
    adds r7, #1
    cmp r7, r8
    bne dm_sum
    adr.w r0, dm_cfg
    ldrb r0, [r0, #1]
    cmp r0, #2
    bne dm_numbers
    cmp r11, #0xff                  @ meters: "Pn" and a bar, the slot's whole width (the bar stops at 75)
    it hi
    movhi r11, #0xff
    orr r11, r11, #METER
    movs r0, #TOTAL_WIDE
    b dm_wide
dm_numbers:
    movw r0, #999
    cmp r11, r0
    it hi
    movhi r11, r0
    mov r0, r11
    bl ndigits
    adds r0, #6                     @ "Pn " and "/75"
    lsls r0, r0, #3
    subs r0, #SCALE
dm_wide:
    cmp r6, #32
    ite eq
    moveq r3, #TOTAL_RIGHT0
    movne r3, #TOTAL_RIGHT1
    sub.w r3, r3, r0                @ right-aligned in its slot (flags kept for the it ne below)
    orr.w r10, r11, r3, lsl #10
    orr.w r10, r10, #(TOTAL_TOP << 20)
    orr.w r10, r10, #(VALID | TOTAL)
    it ne
    orrne r10, r10, #PATH2
dm_place:                           @ a label that changed or went is wiped before the stock paint, which then draws
    ldr.w r0, [r9, r6, lsl #2]      @ whatever its own changes put there (a moved path line, an icon)
    cmp r0, r10
    beq dm_next
    str.w r10, [r9, r6, lsl #2]
    cbz r0, dm_next
    movs r1, #0
    bl label
dm_next:
    adds r6, #1
    cmp r6, #NTRACK
    bne dm_item
    ldr r3, =WUNLOCK
    blx r3
    mov r0, r4
    mov r1, r5
    ldr r3, =STOCK_PAINT
    blx r3
    str r0, [sp, #128]
    movs r6, #0
dm_draw:                            @ every label, every paint, in case the stock paint drew over one
    ldr.w r0, [r9, r6, lsl #2]
    cbz r0, dm_drawn
    movs r1, #1
    bl label
dm_drawn:
    adds r6, #1
    cmp r6, #NTRACK
    bne dm_draw
    adr.w r3, dm_cfg                @ Focus View (dm_cfg + 2): the paths' area blanked, a placeholder block in it
    ldrb r3, [r3, #2]
    cbz r3, dm_unfocused
    bl focus_fill
dm_unfocused:
    ldr r0, [sp, #128]
    add sp, #140
    pop {r4-r11, pc}

cost_of:                            @ r0 a block record's index, r7 the DSP model, under its lock -> r0 its cost, or -1
    movs r2, #0x54
    mla r0, r0, r2, r7
    ldr r0, [r0, #0x14]             @ the block's handle among the preset's nodes
    cmp r0, #0x4b
    bhi cost_none
    add.w r1, r7, #(NODES & 0xf000)
    ldr r1, [r1, #(NODES & 0xfff)]
    add.w r1, r1, r0, lsl #2
    ldr r1, [r1, #0x24]
    cbz r1, cost_none
    ldrb r2, [r1, #5]
    cmp r2, #1
    bne cost_none                   @ kind 1: a block object (0x2811d62e)
    ldr r0, [r1, #0x44]             @ its cost, set at block load and summed into the DSP's total
    bx lr
cost_none:
    mvn r0, #0
    bx lr

ndigits:                            @ r0 a number 0..999 -> r0 how many digits
    cmp r0, #100
    bhs nd3
    cmp r0, #10
    ite hs
    movhs r0, #2
    movlo r0, #1
    bx lr
nd3:
    movs r0, #3
    bx lr

label:                              @ r0 a label, r1 0 to wipe it (black), 1 to draw it; r4 the frame
    push {r5-r11, lr}
    sub sp, #16                     @ 0 its glyphs (9 at most), 12..14 the digits, right to left
    mov r5, r0
    mov r6, r1
    mov r0, sp                      @ where the next glyph goes
    tst r5, #TOTAL
    beq lb_value
    movs r3, #G_P
    strb r3, [r0], #1
    tst r5, #PATH2
    ite eq
    moveq r3, #1
    movne r3, #2
    strb r3, [r0], #1
    tst r5, #METER
    bne lb_counted                  @ a meter: "Pn" and its bar
    movs r3, #G_SPACE
    strb r3, [r0], #1
lb_value:
    ubfx r1, r5, #0, #10
    movw r2, #999
    cmp r1, r2
    it hi
    movhi r1, r2
    add r7, sp, #15
    movs r2, #10
lb_digit:
    udiv r12, r1, r2
    mls r3, r12, r2, r1
    strb r3, [r7, #-1]!
    movs r1, r12
    bne lb_digit
    add r2, sp, #15
lb_move:                            @ r7 the first digit
    ldrb r3, [r7], #1
    strb r3, [r0], #1
    cmp r7, r2
    bne lb_move
    tst r5, #TOTAL
    beq lb_counted
    movs r3, #G_SLASH
    strb r3, [r0], #1
    movs r3, #7
    strb r3, [r0], #1
    movs r3, #5
    strb r3, [r0], #1
lb_counted:
    str r5, [sp, #12]               @ the label (the digits' scratch is free now)
    mov r7, sp
    subs r7, r0, r7                 @ glyphs
    ubfx r8, r5, #10, #10           @ left
    ubfx r9, r5, #20, #9            @ top
    cbnz r6, lb_draw
    movs r10, #0
    mov r0, r8
    mov r1, r9
    lsls r2, r7, #3
    subs r2, #SCALE
    tst r5, #TOTAL
    beq lb_wipe
    tst r5, #METER
    it ne
    movne r2, #TOTAL_WIDE           @ a meter: its bar too
lb_wipe:
    movs r3, #TALL
    bl fill
    b lb_out
lb_draw:
    movw r10, #GREY
    tst r5, #TOTAL
    it ne
    movwne r10, #WHITE
    movs r6, #0                     @ the glyph
lb_glyph:
    ldrb r0, [sp, r6]
    adr.w r1, dm_font
    ldrh.w r11, [r1, r0, lsl #1]
    movs r5, #0                     @ the cell, row by row from the top left
lb_cell:
    tst r11, #0x4000
    beq lb_off
    movs r2, #3
    udiv r1, r5, r2
    mls r0, r1, r2, r5
    movs r2, #SCALE
    mul r0, r0, r2
    mul r1, r1, r2
    add.w r0, r0, r6, lsl #3
    add r0, r8
    add r1, r9
    movs r3, #SCALE
    bl fill
lb_off:
    lsl.w r11, r11, #1
    adds r5, #1
    cmp r5, #15
    bne lb_cell
    adds r6, #1
    cmp r6, r7
    bne lb_glyph
    ldr r5, [sp, #12]
    tst r5, #TOTAL
    beq lb_out
    tst r5, #METER
    beq lb_out
    add r8, r8, #BAR_X              @ the bar: an edge, black inside, filled to used/75 in green, yellow or red
    movw r10, #EDGE
    mov r0, r8
    mov r1, r9
    movs r2, #BAR_W
    movs r3, #1
    bl fill
    mov r0, r8
    add r1, r9, #(TALL - 1)
    movs r2, #BAR_W
    movs r3, #1
    bl fill
    mov r0, r8
    mov r1, r9
    movs r2, #1
    movs r3, #TALL
    bl fill
    add r0, r8, #(BAR_W - 1)
    mov r1, r9
    movs r2, #1
    movs r3, #TALL
    bl fill
    movs r10, #0
    add r0, r8, #1
    add r1, r9, #1
    movs r2, #(BAR_W - 2)
    movs r3, #(TALL - 2)
    bl fill
    ubfx r11, r5, #0, #9
    cmp r11, #BUDGET
    it hi
    movhi r11, #BUDGET
    movw r10, #GREEN
    cmp r11, #45                    @ 60% of 75
    blo lb_colour
    movw r10, #YELLOW
    cmp r11, #68                    @ 90%
    it hs
    movwhs r10, #RED
lb_colour:
    movs r2, #(BAR_W - 2)
    mul r2, r11, r2
    movs r1, #BUDGET
    udiv r2, r2, r1
    cbz r2, lb_out
    add r0, r8, #1
    add r1, r9, #1
    movs r3, #(TALL - 2)
    bl fill
lb_out:
    add sp, #16
    pop {r5-r11, pc}

focus_fill:                         @ r4 the frame: the paths' area blanked, the placeholder block in it
    push {r10, lr}
    movs r10, #0
    movs r0, #0
    movs r1, #FOCUS_Y
    movw r2, #W
    movw r3, #FOCUS_H
    bl fill
    bl focus_img
    pop {r10, pc}

focus_img:                          @ r4 the frame: every image of dm_imgs (index, x, y, w, h; 0xffff ends) through the stock image widget's paint
    push {r5-r7, lr}                @ (0x2808e56c: it takes the widget lock itself) on a widget of ours (on the stack): no parent,
    sub sp, #0x28                   @ visible
    adr.w r6, dm_imgs
    mov r7, sp
fi_loop:
    ldrh r0, [r6]
    movw r1, #0xffff
    cmp r0, r1
    beq fi_done
    movw r1, #SEL_PIC
    cmp r0, r1
    bne fi_have
    bl focus_pid
    cmp r0, #0
    blt fi_next
fi_have:
    str r0, [r7]
    str r0, [r7, #4]
    mvn r1, #0
    str r1, [r7, #8]                @ no mask colour
    ldrh r1, [r6, #2]
    str r1, [r7, #0xc]
    ldrh r1, [r6, #4]
    str r1, [r7, #0x10]
    ldrh r1, [r6, #6]
    str r1, [r7, #0x14]
    ldrh r1, [r6, #8]
    str r1, [r7, #0x18]
    movw r1, #0x101                 @ +0x1c the anchor (1: x is the centre), +0x1d visible
    strh r1, [r7, #0x1c]
    movs r1, #0
    str r1, [r7, #0x20]
    str r1, [r7, #0x24]
    mov r0, r4
    mov r2, r7
    ldr r3, =IMG_WIDGET_PAINT
    blx r3
fi_next:
    adds r6, #10
    b fi_loop
fi_done:
    add sp, #0x28
    pop {r5-r7, pc}

focus_pid:                          @ -> r0 the selected block's picture (ART_BASE + its preset id), or < 0 (empty, none). As the
    push {r4, lr}                   @ block title's callers (0x280a5f20): selected block, its descriptor; preset id = word at +1
    sub sp, #0x40
    add r0, sp, #0x38
    ldr r3, =SEL_BLOCK
    blx r3
    mov r4, r0
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
    cmp r0, #0
    blt fp_none
    ldr r0, [sp]
    lsrs r0, r0, #8
    ldrb r1, [sp, #4]
    orr r0, r0, r1, lsl #24
    movw r1, #N_PIDS
    cmp r0, r1
    bhs fp_none                     @ (also -1, an empty block)
    addw r0, r0, #ART_BASE
    b fp_out
fp_none:
    mvn r0, #0
fp_out:
    add sp, #0x40
    pop {r4, pc}

fill:                               @ r0 x, r1 y, r2 width, r3 height (on the screen), r10 the colour, r4 the frame
    push {r5, r6}
    mov.w r12, #W
    mla r12, r1, r12, r0
    add.w r12, r4, r12, lsl #1
fill_row:
    mov r5, r12
    mov r6, r2
fill_px:
    strh r10, [r5], #2
    subs r6, #1
    bne fill_px
    add.w r12, r12, #(W * 2)
    subs r3, #1
    bne fill_row
    pop {r5, r6}
    bx lr

.thumb_func
dm_text:                            @ the value-text function's start (trampoline): our two settings' strings, else stock
    cmp r0, #ID_BLOCKS
    beq dt_blocks
    cmp r0, #ID_PATHS
    beq dt_paths
    push.w {r4, r5, r6, r7, r8, r9, lr}  @ the 8 bytes the trampoline covers
    vpush {d8}
    ldr r12, =TEXT_REST             @ (r12 is free at a call)
    bx r12
dt_blocks:
    adr.w r12, dt_onoff
    ldr r0, [r1, #4]
    cmp r0, #1
    it hi
    movhi r0, #1
    b dt_copy
dt_paths:
    adr.w r12, dt_modes
    ldr r0, [r1, #4]
    cmp r0, #2
    it hi
    movhi r0, #2
dt_copy:                            @ r12 + 8 value: the string (8 bytes, NUL padded) into out, at most size - 1 and a NUL
    add.w r12, r12, r0, lsl #3
    subs r3, #1
    blt dt_done
dt_char:
    cbz r3, dt_end
    ldrb r0, [r12], #1
    cbz r0, dt_end
    strb r0, [r2], #1
    subs r3, #1
    b dt_char
dt_end:
    movs r0, #0
    strb r0, [r2]
dt_done:
    movs r0, #0
    bx lr

@ dm_event: the UI event post (0x2808b668) enters here through a trampoline over its first 8 bytes (push {r3-r7, lr};
@ mov r5, r0; ldr r0, =A; ldr r6, =B), which are replayed. Home (key 2, value 0 on the panel, 1 from the mirror's input)
@ pressed while the home view is the active screen flips Focus View (dm_cfg + 2); the event goes on to the stock post.
.thumb_func
dm_event:
    push {r3-r7, lr}
    mov r5, r0
    ldrb r2, [r5]
    cmp r2, #5                      @ class 5 and 6 come from the mirror only (fm_input): 12 bits of payload, code << 6 | value & 63.
    blo de_stock                    @ 5 sets the write index into dm_imgs, 6 writes a halfword there and steps on. Not passed on.
    cmp r2, #6
    bhi de_stock
    ldrb r1, [r5, #1]
    ldrb r0, [r5, #4]
    and r0, r0, #63
    orr.w r0, r0, r1, lsl #6
    adr.w r3, dm_pidx
    cmp r2, #5
    bne de_write
    strh r0, [r3]
    pop {r3-r7, pc}
de_write:
    ldrh r1, [r3]
    adr.w r2, dm_imgs
    cmp r1, #20                     @ 4 pictures of 5; the end mark stays
    it lo
    strhlo r0, [r2, r1, lsl #1]
    adds r1, #1
    strh r1, [r3]
    pop {r3-r7, pc}
de_stock:
    ldrb r2, [r5]
    cmp r2, #1
    bne de_go
    ldrb r2, [r5, #1]
    cmp r2, #2
    bne de_go
    adr.w r3, dm_cfg
    ldrb r1, [r3, #3]               @ bit 0 a repaint is due, bit 1 our own Home is being posted
    tst r1, #2
    bne de_go
    ldrb r2, [r5, #4]
    cmp r2, #1
    bhi de_rel
    ldr r2, =HOME_VIEW              @ the press: flip Focus View when the home view is the active screen
    ldr r2, [r2]
    cmp r2, #1
    bne de_go
    ldrb r2, [r3, #2]
    eor r2, r2, #1
    strb r2, [r3, #2]
    orr r1, r1, #1
    strb r1, [r3, #3]
    cbz r2, de_go
    ldr r4, =FB0                    @ on: blank both framebuffers now (the screen shows one, the next paint the other)
    bl focus_fill
    ldr r4, =FB0 + 0xbb800
    bl focus_fill
    b de_go
de_rel:
    cmp r2, #2                      @ the release: the stock only repaints what changed, so a gear menu round trip
    bne de_go                       @ (key 19, then Home) repaints the whole home screen. Done here, not in the press,
    tst r1, #1                      @ where the button task is still busy with the press
    beq de_go
    movs r1, #2
    strb r1, [r3, #3]
    sub sp, #8
    adr.w r6, dm_seq
    movs r4, #4
de_next:
    movs r0, #1
    strb r0, [sp]
    ldrb r0, [r6], #1
    strb r0, [sp, #1]
    movs r0, #0
    strh r0, [sp, #2]
    ldrb r0, [r6], #1
    str r0, [sp, #4]
    mov r0, sp
    ldr r3, =POST_ENTRY
    blx r3
    subs r4, #1
    bne de_next
    add sp, #8
    adr.w r3, dm_cfg
    movs r2, #0
    strb r2, [r3, #3]
de_go:
    ldr r0, =POST_A
    ldr r6, =POST_B
    ldr r12, =POST_BODY
    bx r12

.ltorg
.balign 4
dm_imgs:                            @ Focus View's pictures: index, centre x, top y, width, height (0xffff ends); room for 4, poked live by
    .hword SEL_PIC, 400, 110, 128, 128  @ mirror classes 5 and 6. Index SEL_PIC: the selected block's own picture
    .fill 16, 2, 0xffff
dm_pidx:
    .hword 0
dm_seq:                             @ key, value: gear menu press and release, Home press and release
    .byte 19, 1, 19, 2, 2, 1, 2, 2
.balign 4
dt_onoff:
    .ascii "Off\0\0\0\0\0On\0\0\0\0\0\0"
dt_modes:
    .ascii "Off\0\0\0\0\0Numbers\0Meters\0\0"
.balign 2
dm_font:                            @ 3x5 glyphs, bit 14 the top left cell, rows of 3 bits: 0..9, '/', 'P', ' '
    .hword 0b111101101101111, 0b010110010010111, 0b111001111100111, 0b111001111001111, 0b101101111001001
    .hword 0b111100111001111, 0b111100111101111, 0b111001001001001, 0b111101111101111, 0b111101111001111
    .hword 0b001001010100100, 0b111101111100100, 0
.balign 4
dm_cfg:                             @ block labels 0 off / 1 on; path totals 0 off / 1 numbers / 2 meters (the settings' defaults until read)
    .byte 1, 1, 0, 0
dm_track:                           @ the labels each framebuffer has (FB0's, then the other's)
    .space NTRACK * 4 * 2
