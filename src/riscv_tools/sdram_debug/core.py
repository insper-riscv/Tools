"""Primitives of the SDRAM debug port, the mem_edit of a RAM outside the FPGA.

The debug port is a second master of the SDRAM controller reached through a
Virtual JTAG instance (see Memory's docs/SDRAM_DEBUG.md). Addresses here are word
addresses counted from the base of the SDRAM. Pure mechanism, no policy: the
callers decide which words to use.
"""

from riscv_tools.jtag import JtagLink, run_tcl


def write_word(
    link: JtagLink, word_address: int, value: int, byte_enable: int = 0xF
) -> None:
    """Write one 32-bit word of the SDRAM.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    word_address : int
        Word address (not byte address) counted from the base of the SDRAM.
    value : int
        32-bit unsigned value to write.
    byte_enable : int, optional
        Which bytes to write: bit i enables byte i of the word. Defaults to 0xF.

    Returns
    -------
    None
    """
    run_tcl(link, "sdram_dbg.tcl", "write", word_address, value, byte_enable)


def read_words(link: JtagLink, word_address: int, word_count: int = 1) -> list[int]:
    """Read contiguous 32-bit words of the SDRAM.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    word_address : int
        Word address (not byte address) of the first word, counted from the
        base of the SDRAM.
    word_count : int, optional
        How many contiguous words to read. Defaults to 1.

    Returns
    -------
    list of int
        The word_count values read, in address order.

    Raises
    ------
    RuntimeError
        The script's output did not contain the expected "WORDS=" reply line.
    """
    result = run_tcl(link, "sdram_dbg.tcl", "read", word_address, word_count)
    for line in result.stdout.splitlines():
        if line.startswith("WORDS="):
            return [int(w) for w in line.split("=", 1)[1].split()]
    raise RuntimeError(f"sdram_dbg.tcl produced no WORDS= line:\n{result.stdout}")


def fill(link: JtagLink, word_address: int, word_count: int, value: int = 0) -> None:
    """Fill contiguous words of the SDRAM with one value (done by the board).

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    word_address : int
        Word address of the first word, counted from the base of the SDRAM.
    word_count : int
        How many words to write.
    value : int, optional
        The 32-bit value written to every byte of every word. Defaults to 0.

    Returns
    -------
    None
    """
    run_tcl(link, "sdram_dbg.tcl", "fill", word_address, word_count, value)
