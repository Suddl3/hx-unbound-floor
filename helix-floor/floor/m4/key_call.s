@ key_call.s: dev-mode key injection through the firmware's own key function 0x2808bca0(code, down), as the button scan calls it (it keeps
@ its down/hold tables and posts value 1 on a press and 2, then 3 on a release): code 2 (Home), down = the poke call's argument (0/1).
.syntax unified
.thumb
.text
.thumb_func
key_call:
    mov r1, r0
    and r1, r1, #1
    movs r0, #2
    ldr r3, =0x2808bca1
    bx r3
.ltorg
