/* Minimal standalone linker script for the HTIF fixture programs used
 * by tests/test_generate_golden.py — NOT the consuming project's real
 * link.ld/crt0.S, just enough to prove
 * mem_validator.generate_golden's Spike orchestration actually works
 * end to end. 0x80000000 matches Spike's default DRAM base, so no
 * extra spike flags are needed to run this. */
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 64K
}

SECTIONS
{
    .text : { *(.text.start) *(.text*) } > RAM
    .data : { *(.data*) } > RAM
    .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM

    .tohost (NOLOAD) : {
        . = ALIGN(8);
        PROVIDE(tohost = .);
        . += 8;
        PROVIDE(fromhost = .);
        . += 8;
    } > RAM

    _stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
