"""Read the PASS/FAIL mailbox and pulse the restart "go flag" over JTAG."""

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink

PASS = 1
FAIL = 2


def word_offset(ram_base: int, addr: int, *, relative: bool = True) -> int:
    """Convert a byte address into a word offset.

    Two different things both call themselves "the word offset of the
    mailbox", and they're NOT the same number whenever ram_base != 0:

    - relative=True (default): offset relative to RAM's own base —
      (addr - ram_base) // 4. What mem_edit's JTAG primitives expect,
      since the In-System Memory Content Editor addresses RAM through
      its own 0-based internal word index, not the CPU's byte address.
    - relative=False: absolute word offset — addr // 4, no ram_base
      subtraction. For code snooping the CPU's own raw address bus
      directly (e.g. a cocotb testbench watching a DUT's ram_addr
      signal) rather than going through a JTAG debug port — that bus
      always carries the real, absolute address, never a RAM-relative
      one, regardless of where ram_base is mapped.

    Picking the wrong one silently misses every mailbox/go-flag access
    whenever ram_base != 0 (found via RV32IM's own sim testbench
    hardcoding the relative=True math against a raw bus signal after
    RV32IM moved off ram_base=0 — see docs/DATA_HARVARD_BUG.md).

    Parameters
    ----------
    ram_base : int
        RAM's base byte address (memory.ram_base in the project's
        config.yaml). Ignored when relative=False.
    addr : int
        The byte address to convert (e.g.
        memory.mailbox_addr/go_flag_addr) — always absolute either
        way.
    relative : bool
        Which convention to use — see above. Defaults to True (the
        JTAG/mem_edit convention every in-tree real-hardware caller
        needs).

    Returns
    -------
    int
        The word offset, in whichever convention `relative` selected.
    """
    if relative:
        return (addr - ram_base) // 4
    return addr // 4


def read_mailbox(
    link: JtagLink, ram_mem_instance: int, ram_base: int, mailbox_addr: int
) -> int:
    """Read the PASS(1)/FAIL(2)/still-running(0) mailbox word.

    A test program writes this via RV32_PASS()/RV32_FAIL() before
    restarting.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    ram_mem_instance : int
        In-System Memory Content Editor instance index of the RAM.
    ram_base : int
        RAM's base byte address (memory.ram_base).
    mailbox_addr : int
        Byte address of the mailbox word (memory.mailbox_addr in the
        project's config.yaml).

    Returns
    -------
    int
        The current mailbox value: PASS (1), FAIL (2), or 0 if the
        test hasn't finished yet.
    """
    words = mem_edit.read_words(
        link, ram_mem_instance, word_offset(ram_base, mailbox_addr), 1
    )
    return words[0]


def pulse_go_flag(
    link: JtagLink, ram_mem_instance: int, ram_base: int, go_flag_addr: int
) -> None:
    """Set the restart "go" flag.

    Makes a core sitting in rv32_wait_restart (crt0.S) jump back to
    _start and run whatever ROM content is currently loaded — see
    rom_writer.write_rom.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    ram_mem_instance : int
        In-System Memory Content Editor instance index of the RAM.
    ram_base : int
        RAM's base byte address (memory.ram_base).
    go_flag_addr : int
        Byte address of the restart flag word (memory.go_flag_addr in
        the project's config.yaml).

    Returns
    -------
    None
    """
    mem_edit.write_word(link, ram_mem_instance, word_offset(ram_base, go_flag_addr), 1)
