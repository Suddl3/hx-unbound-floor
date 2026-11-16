@ fe_pre.s: dev-mode version of the Focus View exit fix (auto/floor_homefix.py install-pre). In the paint task, before the stock paint of the
@ home view: when Focus View has just gone off, the paths' area of this frame is blanked and the view's full-repaint flag (view + 0x5f:
@ the stock paint then draws every item into the frame) is set, for the next two paints (the two framebuffers). Nothing else draws the
@ scene or reads the flag, so a quick Home pair cannot leave it behind, and no gear-menu round trip is needed.
@ Entered by a jump over dm_paint's `ldr.w r3, [pc, #0x400]; blx r3; str r0, [sp, #0x80]` (module + 512, 8 bytes), r4 the frame, r5 the view.
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_CFG, MODULE + 1712
.equ RET, MODULE + 520 + 1          @ the `movs r6, #0` after the replaced instructions
.equ STOCK_PAINT, 0x280d6be9
.equ MEMSET, 0x28155f35
.equ STATE, 0x29f06f00              @ u8 Focus View at the last paint, u8 frames still to clean
.equ FROM, 52 * 1600                @ the paths' area: y 52 .. 339 (FOCUS_Y, FOCUS_H of the DSP meter module)
.equ SIZE, 288 * 1600
.thumb_func
fe_pre:
    push {r0-r3, r6-r8, r12}        @ eight words: the calls below stay 8-byte aligned
    ldr r6, =STATE
    ldr r7, =DM_CFG
    ldrb r2, [r7, #2]               @ Focus View now
    ldrb r3, [r6]                   @ at the last paint
    strb r2, [r6]
    cbnz r2, done                   @ on: the paint draws the scene itself
    cbz r3, check                   @ was off too
    movs r3, #2                     @ just went off: both framebuffers
    strb r3, [r6, #1]
check:
    ldrb r3, [r6, #1]
    cbz r3, done
    subs r3, r3, #1
    strb r3, [r6, #1]
    ldr r0, =FROM
    add r0, r4
    movs r1, #0
    ldr r2, =SIZE
    ldr r3, =MEMSET
    blx r3
    movs r3, #1
    strb r3, [r5, #0x5f]            @ the stock paint draws everything
done:
    pop {r0-r3, r6-r8, r12}
    ldr r3, =STOCK_PAINT
    blx r3
    str r0, [sp, #0x80]
    ldr pc, =RET
.ltorg
