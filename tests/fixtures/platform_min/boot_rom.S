/* Reduced boot ROM for the picolibc runtime: clears the four HTIF words
 * (tohost and fromhost, 64 bits each, at the top of RAM) and jumps to
 * FLASH_BASE, where the toolchain's crt0 (_start) is. */
    .section .text.reset
    .global _reset
_reset:
    li   t0, 0x00030000
    sw   x0, -16(t0)             // tohost low    = 0x0002FFF0
    sw   x0, -12(t0)             // tohost high   = 0x0002FFF4
    sw   x0, -8(t0)              // fromhost low  = 0x0002FFF8
    sw   x0, -4(t0)              // fromhost high = 0x0002FFFC
    li   t0, 0x00000800          // FLASH_BASE: the crt0's _start
    jr   t0

    /* Where every test ends (RV32_PASS/RV32_FAIL, _exit): the test has
     * written tohost already, so wait for the host to write fromhost and
     * start over. Fixed at 0x100 by boot_rom.ld and, for a test's image,
     * by `--defsym=rv32_wait_restart=0x100` in the specs file. */
    .section .text.wait_restart
    .global rv32_wait_restart
rv32_wait_restart:
    li   t0, 0x00030000
rv32_wait_restart_poll:
    lw   t1, -8(t0)
    beqz t1, rv32_wait_restart_poll
    j    _reset
