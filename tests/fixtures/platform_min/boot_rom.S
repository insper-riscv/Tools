/* Reduced boot ROM for the picolibc runtime: clears the four fixed words
 * and jumps to FLASH_BASE, where the toolchain's crt0 (_start) is. */
    .section .text.reset
    .global _reset
_reset:
    li   t0, 0x00030000
    sw   x0, -4(t0)              // mailbox   = 0x0002FFFC
    sw   x0, -8(t0)              // go_flag   = 0x0002FFF8
    sw   x0, -16(t0)             // fromhost  = 0x0002FFF0
    sw   x0, -12(t0)
    sw   x0, -24(t0)             // tohost    = 0x0002FFE8
    sw   x0, -20(t0)
    li   t0, 0x00000800          // FLASH_BASE: the crt0's _start
    jr   t0

    /* Where every test ends (RV32_PASS/RV32_FAIL, _exit): translate the
     * mailbox to HTIF (1 = pass, 3 = fail), then wait for the go flag and
     * start over. Fixed at 0x100 by boot_rom.ld and, for a test's image, by
     * `--defsym=rv32_wait_restart=0x100` in the specs file. */
    .section .text.wait_restart
    .global rv32_wait_restart
rv32_wait_restart:
    li   t0, 0x00030000
    lw   t1, -4(t0)
    li   t2, 1
    li   t3, 1
    beq  t1, t2, 1f
    li   t3, 3
1:
    sw   t3, -24(t0)
rv32_wait_restart_poll:
    lw   t1, -8(t0)
    beqz t1, rv32_wait_restart_poll
    j    _reset
