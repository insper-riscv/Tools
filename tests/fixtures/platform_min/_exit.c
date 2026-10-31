/* What the toolchain's hosted crt0 needs: exit() ends in _exit(). Code 0
 * is a PASS (tohost 1), anything else a FAIL (tohost (code << 1) | 1),
 * then the boot ROM's rv32_wait_restart takes over. */
extern void rv32_wait_restart(void) __attribute__((noreturn));

void _exit(int code)
{
    volatile unsigned int *tohost = (volatile unsigned int *)0x0002FFF0u;

    tohost[0] = code == 0 ? 1u : ((unsigned int)code << 1) | 1u;
    tohost[1] = 0u;
    rv32_wait_restart();
}
