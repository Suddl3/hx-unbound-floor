@ event_log.s: dev-mode logger of the UI's key events (auto/floor_evlog.py). A 10-byte jump (nop; ldr.w pc, [pc]; .word) over
@ dm_event's first five instructions sends every UI event post here; the key events (class 1) go to a ring in RAM (head u32 at
@ RING, 64 entries from RING + 16: 16 bytes each: the event's {class, code, 0, 0} word, its value word, the module's dm_cfg word (Focus View is byte 2,
@ bit 0 of byte 3 a repaint is due, bit 1 our own Home is posted) and the home view's active word), then the replaced
@ instructions run and the code goes on in dm_event. RAM only: a restart brings back the installed firmware.
.syntax unified
.thumb
.text
.equ RING, 0x29f06000
.equ DM_CFG, MODULE + 1712
.equ HOME_VIEW, 0x2818c21c
.equ MODULE, 0x1001f82c
.equ DE_GO, MODULE + 1502 + 1       @ dm_event's "bne de_go" target
.equ DE_CONT, MODULE + 1372 + 1     @ the instruction after the ten replaced bytes (ldrb r2, [r5, #1])

.thumb_func
ev_log:                             @ r0 the event: u8 class, u8 code, u16 0, u32 value
    push {r1-r3, r12}
    ldrb r12, [r0]
    cmp r12, #1
    bne 1f
    ldr r1, =RING
    ldr r2, [r1]
    and r3, r2, #63
    add r3, r1, r3, lsl #4
    adds r3, r3, #16
    ldr r12, [r0]
    str r12, [r3]
    ldr r12, [r0, #4]
    str r12, [r3, #4]
    ldr r12, =DM_CFG
    ldr r12, [r12]
    str r12, [r3, #8]
    ldr r12, =HOME_VIEW
    ldr r12, [r12]
    str r12, [r3, #12]
    adds r2, r2, #1
    str r2, [r1]
1:  pop {r1-r3, r12}
    push {r3-r7, lr}                @ dm_event's first five instructions
    mov r5, r0
    ldrb r2, [r5]
    cmp r2, #1
    beq 2f
    ldr pc, =DE_GO
2:  ldr pc, =DE_CONT
.ltorg
