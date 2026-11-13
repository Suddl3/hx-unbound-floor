@ floor_mirror.s - Helix Floor screen mirror, ported from HXtra's screen_mirror.s (wisemandenny/hxtra, GPL-3.0).
@ HX Edit's editor service (service 6) gets one more command, CMD 0x52: it replies with the rows of the LCD's frame that
@ changed since the last reply. The Floor's frame is 800 x 480 x 16 bit (750 KB), too big to keep a copy of, so each row
@ keeps only a 16-bit hash (fm_hash) and a changed row is sent whole. (A change that keeps a row's hash is missed until
@ the row changes again or the host skips a seq, which resends every row.)
@
@ Reply (the editor's own map {0x66: seq, 0x67: 0, 0x68: bin32}), the bin32 being, little-endian:
@   u16 0xF100 (format), u16 width, u16 height, u16 rows sent n,
@   u32 the LCD's frame address (UPBASE), u32 the LCD's CTRL register (pixel format),
@   u16[30] bitmap of the rows sent (bit r%16 of word r/16), then n rows of width x u16 pixels, top first,
@   u32 x 3: the µs the frame was taken at, the µs hashing took, the µs sending took.
@ A request whose seq does not follow the last one's gets every row.
@
@ fm_regall replaces the first 8 bytes of the editor's command registrations (0x280ee594, by a trampoline):
@ it runs them, then registers CMD.
.syntax unified
.thumb

.equ CMD, 0x52
.equ CMD_INPUT, 0x51                @ remote input: a UI event packed in the request's seq (fm_input)
.equ POST, 0x2808b669               @ (event): the UI's event post, every listener of the event's class called directly
.equ SERVICE, 6
.equ W, 800
.equ H, 480
.equ ROW_BYTES, W * 2
.equ FB0, 0x285a3f50                @ the first framebuffer (the boot's LCD init, 0x2808ab8a)
.equ SDRAM_LO, 0x28000000
.equ SDRAM_HI, 0x2a000000
.equ LCD, 0x40008000                @ LPC43xx LCD controller: UPBASE +0x10, CTRL +0x18
.equ REGISTER, 0x280ee19d           @ (command, {handler, check, 0}): the editor's command table
.equ NO_PARAMS, 0x280f77fd          @ the check of commands without parameters (movs r0, #0; bx lr)
.equ REGALL, 0x280ee594             @ the editor's registrations: push {r3, lr}; bl A; bl B; ...; pop {r3, pc}
.equ REGALL_A, 0x280f0529           @ its first two calls, which the trampoline covers
.equ REGALL_B, 0x280f01a5
.equ REGALL_REST, 0x280ee59f        @ where it goes on
.equ WRITER, 0x280ed571             @ (service) -> {context, write(context, bytes, n)}
.equ PREFIX_LEN, 0x280ed595         @ (service) -> the word counting the prefix bytes
.equ PREFIX, 0x280ed5b9             @ (service) -> the prefix bytes
.equ PREFIX_RESET, 0x280ed5dd       @ (service): empties it
.equ REPLY_HEAD, 0x280ed621         @ (writer, seq, status): the reply map's head
.equ LOCK, 0x10089149               @ (stream - 8)
.equ UNLOCK, 0x10089169
.equ CLOCK, 0x10009bcd              @ () -> µs (timer 1)
.equ SLEEP, 0x1008971d              @ (µs): the task sleeps
.equ BIN32, 0xc6
.equ HDR, 16 + 60                   @ the fixed part of the result, bitmap included
.equ TRAILER, 12
.equ YIELD_ROWS, 32                 @ hashing sleeps 1 ms every this many rows, so the UI runs
.equ YIELD_US, 1000

fm_regall:                          @ the editor's registrations (entered by the trampoline at REGALL), then CMD
    push {r3, lr}                   @ the caller's frame, popped by fm_after
    adr r12, fm_after
    orr r12, r12, #1
    push.w {r3, r12}                @ REGALL's own frame: its pop {r3, pc} comes back to fm_after
    ldr r3, =REGALL_A
    blx r3
    ldr r3, =REGALL_B
    blx r3
    ldr r3, =REGALL_REST
    bx r3
fm_after:
    bl fm_register
    movs r0, #0
    pop {r3, pc}

fm_register:
    push {r4, lr}
    sub sp, #16
    adr r0, fm_cmd
    orr r0, r0, #1
    ldr r1, =NO_PARAMS
    movs r2, #0
    str r0, [sp, #4]
    str r1, [sp, #8]
    str r2, [sp, #12]
    movs r0, #CMD
    add r1, sp, #4
    ldr r3, =REGISTER
    blx r3
    adr r0, fm_input
    orr r0, r0, #1
    str r0, [sp, #4]
    movs r0, #CMD_INPUT
    add r1, sp, #4
    ldr r3, =REGISTER
    blx r3
    add sp, #16
    pop {r4, pc}

@ fm_input: CMD_INPUT. The request's seq (u16) is the event: bit 15 set, class bits 14..12, code bits 11..6, value
@ bits 5..0 (signed). It posts the 8-byte UI event {class, code, 0, 0, value (s32)} through POST, as the Floor's own
@ producers do (the key function 0x2808bca0, the footswitch scan 0x2808b7e0, the pedal task), and replies 0.
@ Class 1 is a key: value 1 press, 2 release, 3 release before a hold, 5 hold. Class 2 is a knob: code 0..6, value
@ the turn (signed counts; 4 a step on an int setting). Classes 0, 3 and 4 are keys with the code plus 64, 128 and 192 (the encoder and joystick presses are above 63); 5..7 and a seq without bit 15 only get the reply.
fm_input:                           @ r0 the editor's stream, r1 the request -> r0 the stream's result
    push {r4-r7, r10, lr}
    sub sp, #16                     @ [sp] the result byte, [sp,#8] the event
    mov r10, r0
    ldrh r4, [r1, #0xc]
    tst r4, #0x8000
    beq fi_reply
    ubfx r0, r4, #12, #3            @ the class field
    ubfx r1, r4, #6, #6             @ the code field
    cmp r0, #4
    bhi fi_reply                    @ 5..7: refused (class 7 code 0 hung the unit)
    cmp r0, #1
    beq fi_ok                       @ 1: a key, code 0..63
    cmp r0, #2
    beq fi_ok                       @ 2: a knob
    cmp r0, #0
    ite eq
    moveq r2, #1
    subne r2, r0, #1                @ 0, 3, 4 -> 1, 2, 3
    lsls r2, r2, #6                 @ keys 64..127, 128..191, 192..255 (the key function treats code > 63 as a plain key)
    add r1, r2
    movs r0, #1
fi_ok:
    strb r0, [sp, #8]
    strb r1, [sp, #9]
    movs r0, #0
    strh r0, [sp, #10]
    sbfx r0, r4, #0, #6
    str r0, [sp, #12]
    add r0, sp, #8
    ldr r3, =POST
    blx r3
fi_reply:                           @ {0x66: seq, 0x67: 0, 0x68: 0}, as fm_cmd's reply but a fixint result
    movs r0, #SERVICE
    ldr r3, =WRITER
    blx r3
    mov r5, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX_LEN
    blx r3
    mov r6, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX
    blx r3
    mov r7, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX_RESET
    blx r3
    mov r0, r5
    mov r1, r4
    movs r2, #0
    ldr r3, =REPLY_HEAD
    blx r3
    movs r0, #0
    strb r0, [sp]
    ldr r0, [r5]
    ldr r3, [r5, #4]
    mov r1, sp
    movs r2, #1
    blx r3
    sub r0, r10, #8
    ldr r3, =LOCK
    blx r3
    movs r0, #0
    strh r0, [sp, #8]
    movs r0, #SERVICE
    strh r0, [sp, #10]
    ldr r0, [r6]
    str r0, [sp, #12]
    add r1, sp, #8
    movs r2, #8
    bl fm_write
    mov r1, r7
    ldr r2, [r6]
    bl fm_write
    mov r0, r10
    movs r1, #0
    ldr r3, [r10]
    ldr r3, [r3, #0xc]
    blx r3                          @ the message is complete
    mov r4, r0
    sub r0, r10, #8
    ldr r3, =UNLOCK
    blx r3
    mov r0, r4
    add sp, #16
    pop {r4-r7, r10, pc}

fm_cmd:                             @ r0 the editor's stream, r1 the request -> r0 the stream's result
    push {r4-r11, lr}
    sub sp, #28                     @ 36 saved + 28 local = 64 bytes: keep external calls 8-byte aligned
                                   @ [sp] 8-byte headers, [sp,#8] t0, [sp,#12] hashing µs, [sp,#16] frame µs, [sp,#20] fb
    mov r10, r0
    ldrh r9, [r1, #0xc]             @ the request's seq
    adr r3, fm_seq
    ldr r2, [r3]
    str r9, [r3]
    adds r2, #1
    uxth r2, r2
    movs r11, #0                    @ r11: 1 = every row
    cmp r9, r2
    it ne
    movne r11, #1
    cmp r9, #1
    it eq
    moveq r11, #1
    ldr r3, =LCD
    ldr r4, [r3, #0x10]             @ the frame on screen
    ldr r0, =SDRAM_LO
    cmp r4, r0
    blo fm_fb0
    ldr r0, =SDRAM_HI - H * ROW_BYTES
    cmp r4, r0
    blo fm_fb_ok
fm_fb0:
    ldr r4, =FB0
fm_fb_ok:
    bic r4, r4, #7
    str r4, [sp, #20]
    ldr r3, =CLOCK
    blx r3
    str r0, [sp, #8]
    str r0, [sp, #16]

    @ pass 1: hash each row; a row whose hash changed (or every row) is marked in the bitmap
    adr r5, fm_head
    movs r0, #0
    movs r1, #0
fm_clear:                           @ the bitmap: 60 bytes at fm_head + 16
    add r2, r5, r1
    str r0, [r2, #16]
    adds r1, #4
    cmp r1, #60
    blo fm_clear
    adr r6, fm_hash                 @ r6 the hash table
    movs r7, #0                     @ r7 the row
    movs r8, #0                     @ r8 rows marked
fm_row:
    mov r0, r4
    movw r1, #ROW_BYTES
    mla r0, r1, r7, r0              @ the row's pixels
    add r1, r0, #ROW_BYTES
    ldr r2, =0x811c9dc5             @ FNV-1a over words
    ldr r12, =0x01000193
fm_hash_words:
    ldm r0!, {r3, r9}
    eors r2, r3
    mul r2, r2, r12
    eor r2, r2, r9
    mul r2, r2, r12
    cmp r0, r1
    blo fm_hash_words
    eor r2, r2, r2, lsr #16         @ folded to 16 bits: the table stays in the SRAM a build has already used
    uxth r2, r2
    ldrh r3, [r6, r7, lsl #1]
    strh r2, [r6, r7, lsl #1]
    cmp r11, #0
    bne fm_mark
    cmp r2, r3
    beq fm_row_next
fm_mark:
    lsrs r0, r7, #4
    add r0, r5, r0, lsl #1
    ldrh r1, [r0, #16]
    and r2, r7, #15
    movs r3, #1
    lsls r3, r3, r2
    orrs r1, r3
    strh r1, [r0, #16]
    adds r8, #1
fm_row_next:
    adds r7, #1
    cmp r7, #H
    bhs fm_hashed
    ands r0, r7, #YIELD_ROWS - 1
    bne fm_row
    movw r0, #YIELD_US
    ldr r3, =SLEEP
    blx r3
    b fm_row
fm_hashed:
    ldr r3, =CLOCK
    blx r3
    ldr r1, [sp, #8]
    subs r0, r0, r1
    str r0, [sp, #12]

    @ the result's fixed part
    movw r0, #0xF100
    strh r0, [r5]
    movw r0, #W
    strh r0, [r5, #2]
    movw r0, #H
    strh r0, [r5, #4]
    strh r8, [r5, #6]
    str r4, [r5, #8]
    ldr r3, =LCD
    ldr r0, [r3, #0x18]
    str r0, [r5, #12]

    @ the reply, as HXtra's screen_mirror.s writes it
    movs r0, #SERVICE
    ldr r3, =WRITER
    blx r3
    mov r5, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX_LEN
    blx r3
    mov r6, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX
    blx r3
    mov r7, r0
    movs r0, #SERVICE
    ldr r3, =PREFIX_RESET
    blx r3
    mov r0, r5
    adr r3, fm_seq
    ldr r1, [r3]
    movs r2, #0
    ldr r3, =REPLY_HEAD
    blx r3
    movw r0, #ROW_BYTES
    mul r4, r8, r0
    add r4, r4, #HDR + TRAILER      @ r4 the result's bytes
    movs r0, #BIN32
    strb r0, [sp]
    lsrs r0, r4, #24
    strb r0, [sp, #1]
    lsrs r0, r4, #16
    strb r0, [sp, #2]
    lsrs r0, r4, #8
    strb r0, [sp, #3]
    strb r4, [sp, #4]
    ldr r0, [r5]
    ldr r3, [r5, #4]
    mov r1, sp
    movs r2, #5
    blx r3
    sub r0, r10, #8
    ldr r3, =LOCK
    blx r3
    movs r0, #0
    strh r0, [sp]
    movs r0, #SERVICE
    strh r0, [sp, #2]
    ldr r0, [r6]
    add r0, r4
    str r0, [sp, #4]
    mov r1, sp
    movs r2, #8
    bl fm_write
    mov r1, r7
    ldr r2, [r6]
    bl fm_write
    ldr r3, =CLOCK
    blx r3
    str r0, [sp, #8]
    adr r1, fm_head
    movs r2, #HDR
    bl fm_write

    @ pass 2: the marked rows
    adr r5, fm_head
    movs r7, #0
fm_send:
    lsrs r0, r7, #4
    add r0, r5, r0, lsl #1
    ldrh r1, [r0, #16]
    and r2, r7, #15
    lsrs r1, r1, r2
    lsls r1, r1, #31
    beq fm_send_next
    ldr r1, [sp, #20]
    movw r2, #ROW_BYTES
    mla r1, r2, r7, r1
    bl fm_write
fm_send_next:
    adds r7, #1
    cmp r7, #H
    blo fm_send

    ldr r3, =CLOCK
    blx r3
    ldr r1, [sp, #8]
    subs r0, r0, r1
    adr r1, fm_trailer
    str r0, [r1, #8]
    ldr r0, [sp, #12]
    str r0, [r1, #4]
    ldr r0, [sp, #16]
    str r0, [r1]
    movs r2, #TRAILER
    bl fm_write
    mov r0, r10
    movs r1, #0
    ldr r3, [r10]
    ldr r3, [r3, #0xc]
    blx r3                          @ the message is complete
    mov r4, r0
    sub r0, r10, #8
    ldr r3, =UNLOCK
    blx r3
    mov r0, r4
    add sp, #28
    pop {r4-r11, pc}

fm_write:                           @ r1 bytes, r2 how many: to the stream r10
    mov r0, r10
    ldr r3, [r10]
    ldr r3, [r3, #4]
    bx r3

.ltorg
.align 2
fm_seq:
    .space 4
fm_trailer:
    .space TRAILER
fm_head:                            @ the result's fixed part: 16 bytes, then the 60-byte bitmap
    .space HDR
fm_hash:                            @ a 16-bit hash a row
    .space H * 2
