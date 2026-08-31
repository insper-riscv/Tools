/* Minimal standalone linker script for the HTIF fixture programs used
 * by tests/test_generate_golden.py — NOT the consuming project's real
 * link.ld/crt0.S, just enough to prove
 * golden_generator.generate_golden's Spike orchestration actually works
 * end to end. 0x80000000 matches Spike's default DRAM base — test_generate_golden.py
 * still passes it explicitly via mem_regions (generate_golden always
 * requires that now — see its own docstring), but picking the same
 * address Spike would have used by default keeps this fixture
 * unsurprising. */
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
