@ sharc_ramboot.s: SHARC dev mode. Boots both DSPs from an LDR image held in RAM instead of the eMMC, by calling the
@ firmware's own DSP boot (0x100059e0, the call the start-up makes at 0x281157ac through the veneer 0x28156718) with two fake
@ stream objects whose read copies from RAM. Nothing is written to the eMMC; a restart brings back the installed Entry 2.
@
@ The boot takes an array of two stream objects (one per DSP) and uses only slot 0 of each object's class: read(obj, buf, n)
@ -> n, or < 0 (stock read 0x100043bc: obj +8 buffer, +0xc, +0x10 sector, +0x14 position). Here an object is
@ {class, pos, base, len}; the class is 8 words, slot 0 = sr_read, the rest return 0.
@
@ Control block at CTL (host writes +4 base and +8 len before the call; the stub builds the rest):
@   +0 result (0 = booted, < 0 error; the host sets 0x7fffffff first: still that afterwards = the stub did not finish)
@   +4 image base, +8 image length
@   +0x20 / +0x40 stream objects for DSP 0 / 1, +0x60 their array, +0x80 the class
.syntax unified
.thumb
.text
.equ CTL, 0x29f05000
.equ BOOT, 0x100059e1               @ the DSP boot (Thumb)

.thumb_func
sr_read:                            @ r0 = object, r1 = buffer, r2 = bytes
    push {r4, lr}
    ldr r3, [r0, #4]                @ position
    ldr r4, [r0, #12]               @ length
    subs r4, r4, r3                 @ bytes left
    cmp r2, r4
    bhi 3f
    ldr r4, [r0, #8]
    adds r4, r4, r3                 @ source
    adds r3, r3, r2
    str r3, [r0, #4]
    mov r3, r2
1:  cbz r3, 2f
    ldrb ip, [r4], #1
    strb ip, [r1], #1
    subs r3, r3, #1
    b 1b
2:  mov r0, r2
    pop {r4, pc}
3:  mvn r0, #0
    pop {r4, pc}

.thumb_func
sr_ret0:
    movs r0, #0
    bx lr

.balign 4
.thumb_func
sr_run:
    push {r4-r8, lr}                @ six words: calls stay 8-byte aligned
    ldr r4, =CTL
    ldr r5, [r4, #4]                @ image base
    ldr r6, [r4, #8]                @ image length
    adds r7, r4, #0x80              @ the class
    adr r0, sr_read
    orr r0, r0, #1
    str r0, [r7]
    adr r0, sr_ret0
    orr r0, r0, #1
    movs r1, #1
4:  str r0, [r7, r1, lsl #2]
    adds r1, r1, #1
    cmp r1, #8
    bne 4b
    adds r0, r4, #0x20              @ object 0
    adds r1, r4, #0x40              @ object 1
    movs r2, #0
    str r7, [r0]
    str r2, [r0, #4]
    str r5, [r0, #8]
    str r6, [r0, #12]
    str r7, [r1]
    str r2, [r1, #4]
    str r5, [r1, #8]
    str r6, [r1, #12]
    str r0, [r4, #0x60]
    str r1, [r4, #0x64]
    adds r0, r4, #0x60              @ the array
    ldr r3, =BOOT
    blx r3
    str r0, [r4]
    pop {r4-r8, pc}
.ltorg

@ sr_relink: experiment. After sr_run the DSPs are fresh but the ARM's link driver still holds the old state. Calls the
@ driver's per-DSP start (0x1000e035, as the start-up does at 0x28115890..0x281158a2 with 0x1000e299 in between) for DSP 0 and 1
@ and stores both results at CTL + 4 * 0x10 + (0, 4).
.equ LINK_START, 0x1000e035
.balign 4
.thumb_func
sr_relink:
    push {r4-r6, lr}
    ldr r4, =CTL
    ldr r5, =LINK_START
    movs r0, #0
    blx r5
    str r0, [r4, #0x10]
    movs r0, #1
    blx r5
    str r0, [r4, #0x14]
    pop {r4-r6, pc}
.ltorg

@ sr_full: experiment 2. Tear the ARM's DSP link driver down (0x1000e2d1: contexts and its two tasks), boot the DSPs from the
@ RAM image (sr_run), then repeat the start-up's bring-up in its own order (0x2811582c..0x281158a8): the two eMMC streams
@ (opened again: their positions moved on), the graph library header (0x28156b30), 0x28114cac, the driver init 0x28156a48
@ (-> 0x1000e201: tasks and per-DSP contexts), 0x281569e8 for DSP 0 and 1, 0x281568b8 (resume tasks), 0x28156cb8 for DSP 0 and 1.
@ CTL + 0x18 = the step reached (1.. 11, 99 = done), CTL + 0x1c = the failing step's result.
.macro STEP n
    movs r7, #\n
    str r7, [r4, #0x18]
.endm
.macro CALL a
    ldr r7, =\a
    blx r7
.endm
.balign 4
.thumb_func
sr_full:
    push {r4-r8, lr}
    ldr r4, =CTL
    STEP 1
    CALL 0x1000e2d1                 @ teardown
    STEP 2
    adr r7, sr_run
    orr r7, r7, #1
    blx r7
    ldr r0, [r4]
    cmp r0, #0
    bne sf_fail
    STEP 3
    CALL 0x28114c65                 @ the boot mode: 0 = a normal boot (the start-up's default branch 0x28115b54)
    cmp r0, #0
    bne sf_fail
    movw r5, #0x890d                @ Entry 4's sector
    movw r6, #0x9110                @ Entry 5's
    STEP 4
    ldr r0, =0x282c5780
    ldr r1, =0x2971dbd4
    movs r2, #0xb
    mov r3, r5
    CALL 0x28156c69
    cmp r0, #0
    blt sf_fail
    STEP 5
    ldr r0, =0x282c57ec
    ldr r1, =0x2981dbd4
    movs r2, #2
    mov r3, r6
    CALL 0x28156c69
    cmp r0, #0
    blt sf_fail
    STEP 6
    ldr r0, =0x282c5780
    CALL 0x28156b31
    cmp r0, #0
    blt sf_fail
    STEP 7
    CALL 0x28114cad
    cmp r0, #0
    blt sf_fail
    movs r1, #0                     @ the link layer's two "context in use" bytes: the teardown leaves them set (a second
    ldr r2, =0x2817298c             @ bring-up then fails with -9 in 0x1000f280)
    strb r1, [r2]
    strb r1, [r2, #1]
    STEP 8
    ldr r0, =0x282c57ec
    ldr r1, =0x282c57e4
    ldr r1, [r1]
    ldr r2, =0x282c580c
    CALL 0x28156a49
    cmp r0, #0
    blt sf_fail
    STEP 9
    movs r0, #0
    ldr r1, =0x282c5754
    CALL 0x281569e9
    cmp r0, #0
    blt sf_fail
    STEP 10
    movs r0, #1
    ldr r1, =0x282c5758
    CALL 0x281569e9
    cmp r0, #0
    blt sf_fail
    STEP 11
    CALL 0x281568b9
    STEP 12
    movs r0, #0
    CALL 0x28156cb9
    cmp r0, #0
    blt sf_fail
    STEP 13
    movs r0, #1
    CALL 0x28156cb9
    cmp r0, #0
    blt sf_fail
    movs r7, #99
    str r7, [r4, #0x18]
    movs r0, #0
    b sf_fail
sf_stop:
    movs r0, #0x7e
sf_fail:
    str r0, [r4, #0x1c]
    pop {r4-r8, pc}
.ltorg

@ sr_spawn: runs sr_full in its OWN task (the firmware's task create 0x10088cb4(entry, priority, stack, stack bytes, arg), as the link
@ driver makes its tasks), so a step that blocks stalls only that task and the editor task keeps answering the host: the step
@ reached stays readable (CTL + 0x18). The task handle goes to CTL + 0xc. The stack is 8 KB at 0x29f10000 (the create fills it with 0xff).
.balign 4
.thumb_func
sr_task:
    push {r4, r7, r8, lr}
    adr r0, sr_full
    orr r0, r0, #1
    blx r0
1:  movw r0, #10000                 @ done: sleep forever (a task must not return)
    ldr r3, =0x1008971d             @ the firmware's delay (ms), as the start-up uses it
    blx r3
    b 1b
.balign 4
.thumb_func
sr_spawn:
    push {r4, lr}
    sub sp, #8
    adr r0, sr_task
    orr r0, r0, #1
    movs r1, #0x41
    ldr r2, =0x29f10000
    movw r3, #0x2000
    movs r4, #0
    str r4, [sp]                    @ the task's argument
    CALL 0x10088cb5
    ldr r1, =CTL
    str r0, [r1, #0xc]
    add sp, #8
    pop {r4, r7, r8, pc}
.ltorg
