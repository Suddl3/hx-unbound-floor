@ unbound_info.s: editor command 0x53 ("which firmware am I") for HX Edit Unbound (env NAM_UNBOUND_INFO=1, unbound_info.py).
@
@ The reply's result is a MessagePack map the build writes after this code (ui_len, then the bytes): the NAM blocks' preset
@ ids and DSP costs, the optional features and a format number, so the editor can offer the blocks this image has and
@ declare their real loads. Nothing on the unit changes: the command only reads its own table.
@
@ ui_regall replaces the first 8 bytes of the editor's command registrations (0x280ee594, by a trampoline). It calls
@ ui_impl (the screen mirror's fm_regall when the mirror is built in, which runs the registrations and registers its own
@ commands; else ui_stock, which runs the registrations the same way), then registers CMD. So the mirror needs no change
@ and only one trampoline sits at 0x280ee594.
.syntax unified
.thumb

.equ CMD, 0x53
.equ SERVICE, 6
.equ REGISTER, 0x280ee19d           @ (command, {handler, check, 0}): the editor's command table
.equ NO_PARAMS, 0x280f77fd          @ the check of commands without parameters (movs r0, #0; bx lr)
.equ REGALL_A, 0x280f0529           @ the registrations' first two calls, which the trampoline covers
.equ REGALL_B, 0x280f01a5
.equ REGALL_REST, 0x280ee59f        @ where the registrations go on
.equ WRITER, 0x280ed571             @ (service) -> {context, write(context, bytes, n)}
.equ PREFIX_LEN, 0x280ed595         @ (service) -> the word counting the prefix bytes
.equ PREFIX, 0x280ed5b9             @ (service) -> the prefix bytes
.equ PREFIX_RESET, 0x280ed5dd       @ (service): empties it
.equ REPLY_HEAD, 0x280ed621         @ (writer, seq, status): the reply map's head
.equ LOCK, 0x10089149               @ (stream - 8)
.equ UNLOCK, 0x10089169

ui_regall:                          @ the registrations (entered by the trampoline at REGALL), then CMD
    push {r4, lr}
    ldr r3, ui_impl
    blx r3
    bl ui_register
    movs r0, #0
    pop {r4, pc}

ui_stock:                           @ the stock registrations as a function (fm_regall's frame trick, without its commands)
    push {r3, lr}                   @ the caller's frame, popped by ui_stock_after
    adr r12, ui_stock_after
    orr r12, r12, #1
    push.w {r3, r12}                @ REGALL's own frame: its pop {r3, pc} comes back to ui_stock_after
    ldr r3, =REGALL_A
    blx r3
    ldr r3, =REGALL_B
    blx r3
    ldr r3, =REGALL_REST
    bx r3
ui_stock_after:
    movs r0, #0
    pop {r3, pc}

ui_register:
    push {r4, lr}
    sub sp, #16
    adr r0, ui_cmd
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
    add sp, #16
    pop {r4, pc}

ui_cmd:                             @ r0 the editor's stream, r1 the request -> r0 the stream's result
    push {r4-r7, r10, lr}           @ reply {0x66: seq, 0x67: 0, 0x68: <the table's map>}, as the mirror's fm_input
    sub sp, #16
    mov r10, r0
    ldrh r4, [r1, #0xc]
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
    sub r0, r10, #8
    ldr r3, =LOCK
    blx r3
    movs r0, #0
    strh r0, [sp, #8]
    movs r0, #SERVICE
    strh r0, [sp, #10]
    ldr r0, [r6]
    ldr r1, ui_len
    add r0, r1
    str r0, [sp, #12]               @ the message's length: the prefix (the map's head) and the table
    add r1, sp, #8
    movs r2, #8
    bl ui_write
    mov r1, r7
    ldr r2, [r6]
    bl ui_write
    adr r1, ui_table
    ldr r2, ui_len
    bl ui_write
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

ui_write:                           @ r1 bytes, r2 how many: to the stream r10
    mov r0, r10
    ldr r3, [r10]
    ldr r3, [r3, #4]
    bx r3

.ltorg
.balign 4
ui_impl:                            @ the build writes the mirror's fm_regall | 1 here, else ui_stock | 1 (its address)
    .word 0
ui_len:                             @ the table's length, then the table (written by the build)
    .word 0
ui_table:
