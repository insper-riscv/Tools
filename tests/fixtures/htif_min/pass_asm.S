// Writes a known, byte-distinguishable pattern to a fixed address —
// the assembly counterpart to pass_c.c, so
// tests/test_generate_golden.py exercises generate_golden against
// both a compiled C test and a hand-written asm test, same as the
// consuming project's own tests/c/real/*.c and *.S.
.section .text
.globl main
main:
    li   t0, 0x80000100
    li   t1, 0x11223344
    sw   t1, 0(t0)
    ret
