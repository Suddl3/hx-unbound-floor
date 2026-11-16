@ rt_refresh.s: dev-mode replacement of dm_event's repaint round trip (module + 1444, auto/floor_homefix.py refresh). What the round trip really
@ does for the screen is bring the home view back, whose handler (0x280d735c, the view's show) refreshes it with 0x280d5ef4(view): the
@ widgets' state from the model (selection outline, blocks) and then a redraw request for its layer (0x2808a060). Here the refresh is
@ called directly: no catalog, no posts that wait for the UI. Entered by a jump with r3 = dm_cfg, r5 the event; ends where the original ends.
.syntax unified
.thumb
.text
.equ MODULE, 0x1001f82c
.equ DM_CFG, MODULE + 1712
.equ DE_GO, MODULE + 1502 + 1
.equ VIEW, 0x2818c21c
.equ REFRESH, 0x280d5ef5
.thumb_func
rt_start:
    ldr r0, =VIEW
    ldr r3, =REFRESH
    blx r3
    ldr r3, =DM_CFG
    movs r2, #0
    strb r2, [r3, #3]               @ the repaint is no longer due
    ldr pc, =DE_GO
.ltorg
