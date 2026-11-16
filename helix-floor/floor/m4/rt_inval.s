@ rt_inval.s: dev-mode replacement of dm_event's repaint round trip (module + 1444, auto/floor_homefix.py inval): the gear menu round trip
@ is replaced by the render loop's own redraw request, 0x2808a0ac (found in the render task's callers: it sets both layers' request
@ bytes 0x281752f0 / 0x28175304 to 1 under their lock and gives the render task's semaphore 0x281752e8). No UI event, no catalog
@ opening, nothing posted that waits for the UI. Entered by a jump with r3 = dm_cfg, r5 the event; ends where the original ends (de_go).
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_CFG, MODULE + 1712
.equ DE_GO, MODULE + 1502 + 1
.equ REDRAW, 0x2808a0ad            @ invalidate everything (Thumb)
.thumb_func
rt_start:
    ldr r3, =REDRAW
    blx r3
    ldr r3, =DM_CFG
    movs r2, #0
    strb r2, [r3, #3]               @ the repaint is no longer due
    ldr pc, =DE_GO
.ltorg
