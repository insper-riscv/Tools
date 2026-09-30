/* What the boot ROM does at the end of a test, for the ELF Spike runs. On
 * the hardware rv32_wait_restart is boot ROM code at a fixed address
 * (rv32im-fpga.specs), and a test's own image has nothing there. Spike runs
 * the test's image alone, so this file, linked into that ELF only (built
 * with -DRV32_SPIKE, which leaves the fixed address out of the link),
 * provides it: the mailbox translated to HTIF (1 = pass, 3 = fail) in
 * tohost, where Spike stops. */
    .section .bss
    .balign 8
    .global tohost
tohost:   .space 8
    .global fromhost
fromhost: .space 8

    .section .text
    .global rv32_wait_restart
rv32_wait_restart:
    li   t0, 0x00030000
    lw   t1, -4(t0)              // mailbox = 0x0002FFFC
    li   t2, 1
    li   t3, 1
    beq  t1, t2, 1f
    li   t3, 3
1:
    la   t0, tohost
    sw   t3, 0(t0)
2:  j    2b
