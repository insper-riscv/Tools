/* Linker script for boot_rom.S alone: the boot ROM image. */

MEMORY
{
  boot_rom (rx) : ORIGIN = 0x00000000, LENGTH = 2K
}

RESET_RESERVED = 0x100;

OUTPUT_ARCH("riscv")
ENTRY(_reset)

SECTIONS
{
  .text.reset 0x00000000 : { *(.text.reset) } > boot_rom
  ASSERT(SIZEOF(.text.reset) <= RESET_RESERVED,
         "_reset grew past RESET_RESERVED: move rv32_wait_restart or grow the reservation")

  .text.wait_restart RESET_RESERVED : { *(.text.wait_restart) } > boot_rom

  . = ALIGN(4);
  ASSERT(. <= ORIGIN(boot_rom) + LENGTH(boot_rom), "boot_rom.S exceeds the boot ROM")
}
