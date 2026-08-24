from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink

PASS = 1
FAIL = 2


def word_offset(ram_base: int, addr: int) -> int:
    return (addr - ram_base) // 4


def read_mailbox(link: JtagLink, ram_mem_instance: int, ram_base: int, mailbox_addr: int) -> int:
    """Reads the PASS(1)/FAIL(2)/still-running(0) word a test program
    writes via RV32_PASS()/RV32_FAIL() before restarting."""
    words = mem_edit.read_words(link, ram_mem_instance, word_offset(ram_base, mailbox_addr), 1)
    return words[0]


def pulse_go_flag(link: JtagLink, ram_mem_instance: int, ram_base: int, go_flag_addr: int) -> None:
    """Sets the restart "go" flag to make a core sitting in
    rv32_wait_restart (crt0.S) jump back to _start and run whatever
    ROM content is currently loaded — see rom_writer.write_rom."""
    mem_edit.write_word(link, ram_mem_instance, word_offset(ram_base, go_flag_addr), 1)
