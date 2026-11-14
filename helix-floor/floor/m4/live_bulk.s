@ live_bulk.s: a bulk write for the live poke, uploaded at run time (auto/floor_poke.py bulk), nothing installed.
@ It replaces command 0x50's params check (NO_PARAMS) in the editor's command table (0x281c927c + 20 x 0x50 + 8):
@ the check gets the raw request, r1 = {buffer, end, offset of the params}. A byte string param (bin8/16, str8/16)
@ is copied to the poke pointer (the mirror's fm_ptr, whose address the host writes into bulk_ptr), which steps on.
@ Any other param (nil) does nothing; the check returns 0 like NO_PARAMS, and the command runs as before.
@ set_check / unset_check write the table's check pointer in one store (byte pokes would leave it half written).
.syntax unified
.thumb
.text
.global bulk, set_check, unset_check

.thumb_func
bulk:                               @ r0 ?, r1 the parse context
b_start:
    ldr r2, [r1]
    ldr r3, [r1, #8]
    add r2, r3
    ldrb r3, [r2], #1               @ the param's msgpack type
    cmp r3, #0xc4
    beq b_len8
    cmp r3, #0xd9
    beq b_len8
    cmp r3, #0xc5
    beq b_len16
    cmp r3, #0xda
    bne b_done
b_len16:
    ldrb r3, [r2], #1
    ldrb r0, [r2], #1
    orr r3, r0, r3, lsl #8          @ big-endian length
    b b_copy
b_len8:
    ldrb r3, [r2], #1
b_copy:
    ldr r0, bulk_ptr
    ldr r1, [r0]
b_loop:
    subs r3, #1
    bmi b_end
    ldrb r12, [r2], #1
    strb r12, [r1], #1
    b b_loop
b_end:
    str r1, [r0]
b_done:
    movs r0, #0
    bx lr

.thumb_func
set_check:
    ldr r0, check_slot
    adr r1, b_start
    orr r1, r1, #1
    str r1, [r0]
    bx lr

.thumb_func
unset_check:
    ldr r0, check_slot
    ldr r1, no_params
    str r1, [r0]
    bx lr

.balign 4
bulk_ptr:
    .word 0                         @ the mirror's fm_ptr (host-filled)
check_slot:
    .word 0x281c98c4                @ command 0x50's check pointer
no_params:
    .word 0x280f77fd
