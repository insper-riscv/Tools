/* Linker script for boot_memory.S alone: the boot memory image. */

MEMORY
{
  boot_memory (rx) : ORIGIN = 0x00000000, LENGTH = 2K
}

RESET_RESERVED = 0x100;

OUTPUT_ARCH("riscv")
ENTRY(_reset)

SECTIONS
{
  .text.reset 0x00000000 : { *(.text.reset) } > boot_memory
  ASSERT(SIZEOF(.text.reset) <= RESET_RESERVED,
         "_reset grew past RESET_RESERVED: move rv32_wait_restart or grow the reservation")

  .text.wait_restart RESET_RESERVED : { *(.text.wait_restart) } > boot_memory

  . = ALIGN(4);
  ASSERT(. <= ORIGIN(boot_memory) + LENGTH(boot_memory), "boot_memory.S exceeds the boot memory")
}
