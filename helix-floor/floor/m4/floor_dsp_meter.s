@ floor_dsp_meter.s - Helix Floor DSP meter, ported from HXtra's dsp_meter.s (wisemandenny/hxtra, GPL-3.0).
@ The home view shows each block's DSP cost in whole per cent under its icon, in grey, and each path's blocks' sum against
@ what blocks may use on its DSP (90% less the firmware's fixed 15%) as "P1 used/75" and "P2 used/75", in white, in the
@ title bar left of the snapshot icon (the paths' own ends move with the layout: a full path 2 lifts its output).
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

.equ STOCK_PAINT, 0x280d6be9        @ the home view's paint (fb, view)
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
.equ G_SLASH, 10                    @ glyphs past the digits
.equ G_P, 11
.equ G_SPACE, 12

.thumb_func
dm_paint:                           @ r0 the frame, r1 the home view
    push {r4-r11, lr}
    sub sp, #140                    @ 0 the 32 records' costs (-1 none), 128 the stock's result, 132 the model
    mov r4, r0
    mov r5, r1
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
    movw r0, #999
    cmp r11, r0
    it hi
    movhi r11, r0
    mov r0, r11
    bl ndigits
    adds r0, #6                     @ "Pn " and "/75"
    lsls r0, r0, #3
    subs r0, #SCALE
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
lb_out:
    add sp, #16
    pop {r5-r11, pc}

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

.ltorg
.balign 2
dm_font:                            @ 3x5 glyphs, bit 14 the top left cell, rows of 3 bits: 0..9, '/', 'P', ' '
    .hword 0b111101101101111, 0b010110010010111, 0b111001111100111, 0b111001111001111, 0b101101111001001
    .hword 0b111100111001111, 0b111100111101111, 0b111001001001001, 0b111101111101111, 0b111101111001111
    .hword 0b001001010100100, 0b111101111100100, 0
.balign 4
dm_track:                           @ the labels each framebuffer has (FB0's, then the other's)
    .space NTRACK * 4 * 2
