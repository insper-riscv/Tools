from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink

PASS = 1
FAIL = 2


def word_offset(ram_base: int, addr: int) -> int:
    """Converts a byte address into a word offset relative to RAM's base.

    Args:
        ram_base: RAM's base byte address (memory.ram_base in the
            project's config.yaml).
        addr: The byte address to convert (e.g.
            memory.mailbox_addr/go_flag_addr).

    Returns:
        (addr - ram_base) // 4 — the word address mem_edit's JTAG
        primitives expect.
    """
    return (addr - ram_base) // 4


def read_mailbox(link: JtagLink, ram_mem_instance: int, ram_base: int, mailbox_addr: int) -> int:
    """Reads the PASS(1)/FAIL(2)/still-running(0) word a test program
    writes via RV32_PASS()/RV32_FAIL() before restarting.

    Args:
        link: Which JTAG cable/chip to read from.
        ram_mem_instance: In-System Memory Content Editor instance
            index of the RAM.
        ram_base: RAM's base byte address (memory.ram_base).
        mailbox_addr: Byte address of the mailbox word
            (memory.mailbox_addr in the project's config.yaml).

    Returns:
        The current mailbox value: PASS (1), FAIL (2), or 0 if the
        test hasn't finished yet.
    """
    words = mem_edit.read_words(link, ram_mem_instance, word_offset(ram_base, mailbox_addr), 1)
    return words[0]


def pulse_go_flag(link: JtagLink, ram_mem_instance: int, ram_base: int, go_flag_addr: int) -> None:
    """Sets the restart "go" flag to make a core sitting in
    rv32_wait_restart (crt0.S) jump back to _start and run whatever
    ROM content is currently loaded — see rom_writer.write_rom.

    Args:
        link: Which JTAG cable/chip to write to.
        ram_mem_instance: In-System Memory Content Editor instance
            index of the RAM.
        ram_base: RAM's base byte address (memory.ram_base).
        go_flag_addr: Byte address of the restart flag word
            (memory.go_flag_addr in the project's config.yaml).

    Returns:
        None.
    """
    mem_edit.write_word(link, ram_mem_instance, word_offset(ram_base, go_flag_addr), 1)
