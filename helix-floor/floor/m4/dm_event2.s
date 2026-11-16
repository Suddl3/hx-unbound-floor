@ dm_event2.s: dev-mode rewrite of dm_event (auto/floor_homefix.py swallow): Home (class 1, key 2) pressed while the home view is the active
@ screen flips Focus View as before, but the stock never sees that press, its release or its release-before-hold: it returns without the
@ stock post, so the stock UI never hides the selected block's outline (the gear-menu round trip existed to bring it back). The redraw
@ the round trip also caused is requested directly (0x2808a0ac, the render loop's invalidate-all) at the release. dm_cfg + 3: bit 0 a
@ redraw is due, bit 1 our own post (unused now), bit 2 this press is being swallowed. Entered by a jump over dm_event's first ten bytes.
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_CFG, MODULE + 1712
.equ FOCUS_FILL, MODULE + 1050 + 1
.equ HOME_VIEW, 0x2818c21c
.equ FB0, 0x285a3f50
.equ FB1, 0x285a3f50 + 0xbb800
.equ POST_A, 0x28175a08
.equ POST_B, 0x281759d0
.equ POST_BODY, 0x2808b671
.equ REDRAW, 0x2808a0ad
.equ LAYER_H, 0x280b1741            @ list A's active node: the layer under the views (title bar, parameter panel)
.equ LAYER_D, 0x28185254
.equ REFRESH, 0x280d5ef5
.equ HANDLER, 0x280d735d             @ the home view's show / hide handler (r0 = 0, r1 = show, r2 = the view)
.thumb_func
dm_event2:                          @ r0 the event: u8 class, u8 code, u16 0, u32 value
    push {r3-r7, lr}
    mov r5, r0
    ldrb r2, [r5]
    cmp r2, #1
    bne go
    ldrb r2, [r5, #1]
    cmp r2, #2
    bne go
    ldr r3, =DM_CFG
    ldrb r1, [r3, #3]
    tst r1, #2
    bne go
    ldrb r2, [r5, #4]
    cmp r2, #1
    bhi rel
    ldr r2, =HOME_VIEW              @ the press: flip Focus View when the home view is the active screen
    ldr r2, [r2]
    cmp r2, #1
    bne go
    ldrb r2, [r3, #2]
    eor r2, r2, #1
    strb r2, [r3, #2]
    orr r1, r1, #5                  @ a redraw is due; swallow this press
    strb r1, [r3, #3]
    cbz r2, swallow
    ldr r6, =FOCUS_FILL
    ldr r4, =FB0                    @ on: blank both framebuffers now (the screen shows one, the next paint the other)
    blx r6
    ldr r4, =FB1
    blx r6
    b swallow
rel:
    tst r1, #4
    beq go                          @ not a press we took: the stock sees it
    cmp r2, #2
    bne last                        @ the release before a hold (3) or the hold (5): the last event of this press
    tst r1, #1
    beq swallow
    bic r1, r1, #1                  @ the release: ask the render loop for a redraw of everything
    strb r1, [r3, #3]
    sub sp, #8
    ldr r6, =HANDLER                @ hide and show the home view: every widget built again (the selection outline comes back)
    ldr r2, =HOME_VIEW
    movs r0, #0
    movs r1, #0
    blx r6
    ldr r2, =HOME_VIEW
    movs r0, #0
    movs r1, #1
    blx r6
    ldr r0, =HOME_VIEW              @ then the view's refresh: texts and the parameter panel from the model
    ldr r3, =REFRESH
    blx r3
    ldr r3, =REDRAW
    blx r3
    add sp, #8
    b swallow
last:
    bic r1, r1, #4
    strb r1, [r3, #3]
swallow:
    movs r0, #0
    pop {r3-r7, pc}
go:
    ldr r0, =POST_A
    ldr r6, =POST_B
    ldr r12, =POST_BODY
    bx r12
.ltorg
