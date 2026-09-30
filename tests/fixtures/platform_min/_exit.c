/* What the toolchain's hosted crt0 needs: exit() ends in _exit(). Code 0
 * is PASS (mailbox 1), anything else FAIL (mailbox 2), then the boot
 * ROM's rv32_wait_restart takes over. */
extern void rv32_wait_restart(void) __attribute__((noreturn));

void _exit(int code)
{
    *(volatile unsigned int *)0x0002FFFCu = code == 0 ? 1u : 2u;
    rv32_wait_restart();
}
