/* Minimal startup for the HTIF fixture programs — not the consuming
 * project's real crt0.S, just enough to call main() and signal HTIF
 * completion for tests/test_generate_golden.py. */
.section .text.start
.global _start
_start:
    la sp, _stack_top
    call main

    /* HTIF: 1 = pass. No mailbox/go_flag protocol here (that's the
     * real project's concern) — this fixture only needs to prove
     * generate_golden can find tohost, wait for it, and read memory
     * back correctly. */
    li   t0, 1
    la   t1, tohost
    sw   t0, 0(t1)
1:
    j 1b
