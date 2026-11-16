@ rt_knob.s: dev-mode replacement of dm_event's repaint round trip (module + 1444, auto/floor_homefix.py knob): instead of the gear menu
@ round trip (four posts, the block catalog opening and closing) one UI event is posted that changes nothing (knob 6, 0 counts):
@ the UI loop handles it and repaints, which is all the round trip was needed for now that fe_pre cleans the frames.
@ Entered by a jump with r3 = dm_cfg, r5 the event; ends where the original ends (de_go).
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_CFG, MODULE + 1712
.equ DE_GO, MODULE + 1502 + 1
.equ POST_ENTRY, 0x2808b669
.thumb_func
rt_start:
    movs r1, #2
    strb r1, [r3, #3]               @ our own post: dm_event lets it through
    sub sp, #8
    movs r0, #2
    strb r0, [sp]                   @ class 2: a knob
    movs r0, #6
    strb r0, [sp, #1]               @ knob 6
    movs r0, #0
    strh r0, [sp, #2]
    str r0, [sp, #4]                @ 0 counts
    mov r0, sp
    ldr r3, =POST_ENTRY
    blx r3
    add sp, #8
    ldr r3, =DM_CFG
    movs r2, #0
    strb r2, [r3, #3]
    ldr pc, =DE_GO
.ltorg
