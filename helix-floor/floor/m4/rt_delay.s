@ rt_delay.s: dev-mode experiment for the Home double-press bug (auto/floor_homefix.py). dm_event's release branch (module + 1444, 'movs r1, #2')
@ posts the repaint round trip (gear menu press and release, Home press and release) in one burst. Here the same four posts, with a
@ pause after the gear menu's release, so the UI has opened and drawn the block catalog before Home brings the home view back (a fast
@ second Home otherwise folds both round trips into one without a full repaint). Entered by a jump over the original code with
@ r3 = dm_cfg, r5 the event; ends where the original ends (de_go).
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_SEQ, MODULE + 1634
.equ DM_CFG, MODULE + 1712
.equ DE_GO, MODULE + 1502 + 1
.equ POST_ENTRY, 0x2808b669
.equ DELAY, 0x1008971d              @ (ticks x 10: the argument is divided by 10, rounded up)
.equ DELAY_ARG, 600                 @ 60 ms
.thumb_func
rt_start:
    movs r1, #2
    strb r1, [r3, #3]
    sub sp, #8
    ldr r6, =DM_SEQ
    movs r4, #4
1:  movs r0, #1
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
    cmp r4, #3                      @ the gear menu's release has just been posted
    bne 2f
    movw r0, #DELAY_ARG
    ldr r3, =DELAY
    blx r3
2:  subs r4, #1
    bne 1b
    add sp, #8
    ldr r3, =DM_CFG
    movs r2, #0
    strb r2, [r3, #3]
    ldr pc, =DE_GO
.ltorg
