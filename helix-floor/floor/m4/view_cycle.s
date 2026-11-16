@ view_cycle.s: dev-mode probe (poke call, r0 = index): hide then show the view whose handler and data are in the table (the start-up's registrations
@ at 0x28093590..), to see which one owns the bottom parameter panel.
.syntax unified
.thumb
.text
.thumb_func
view_cycle:
    push {r4-r6, lr}
    adr r4, table
    lsls r0, r0, #3
    adds r4, r4, r0
    ldr r5, [r4]                    @ handler (Thumb)
    ldr r6, [r4, #4]                @ data
    sub sp, #8
    movs r0, #0
    movs r1, #0
    mov r2, r6
    blx r5
    movs r0, #0
    movs r1, #1
    mov r2, r6
    blx r5
    add sp, #8
    pop {r4-r6, pc}
.ltorg
.balign 4
table:
    .word 0x280d735d, 0x2818c21c
    .word 0x280cfc61, 0x2818a380
    .word 0x280dfc6d, 0x2818f73c
    .word 0x280cba0d, 0x28188eb8
    .word 0x280d1391, 0x2818ad84
