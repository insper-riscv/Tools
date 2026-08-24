"""Generic In-System Memory Content Editor primitives.

Shared by rom_writer/ram_zero/ram_dump/mailbox. Pure mechanism, no
policy: each of those modules decides WHICH instance/address/content
to use.
"""

from pathlib import Path

from riscv_tools.jtag import JtagLink, run_tcl


def write_full(link: JtagLink, instance: int, mif_path: Path) -> None:
    """Overwrite a memory instance's ENTIRE depth from a .mif.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    instance : int
        In-System Memory Content Editor instance index of the target
        memory (Quartus assigns these in declaration order in the
        project).
    mif_path : Path
        Path to the .mif whose content replaces the instance's entire
        depth.

    Returns
    -------
    None
    """
    run_tcl(link, "write_full.tcl", instance, mif_path)


def write_word(link: JtagLink, instance: int, word_offset: int, value: int) -> None:
    """Overwrite exactly one word, leaving the rest of the instance untouched.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    instance : int
        In-System Memory Content Editor instance index of the target
        memory.
    word_offset : int
        Word address (not byte address) to write.
    value : int
        32-bit unsigned value to write at word_offset.

    Returns
    -------
    None
    """
    run_tcl(link, "write_word.tcl", instance, word_offset, value)


def read_words(
    link: JtagLink, instance: int, word_offset: int, word_count: int = 1
) -> list[int]:
    """Read N contiguous words from a memory instance.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    instance : int
        In-System Memory Content Editor instance index of the target
        memory.
    word_offset : int
        Word address (not byte address) of the first word to read.
    word_count : int, optional
        How many contiguous words to read, starting at word_offset.
        Defaults to 1.

    Returns
    -------
    list of int
        The word_count values read, in address order (word_offset
        first).

    Raises
    ------
    RuntimeError
        The tcl script's output didn't contain the expected "WORDS="
        reply line.
    """
    result = run_tcl(
        link, "read_words.tcl", instance, word_offset, word_count, capture=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("WORDS="):
            return [int(w) for w in line.split("=", 1)[1].split()]
    raise RuntimeError(f"read_words.tcl produced no WORDS= line:\n{result.stdout}")


def dump(link: JtagLink, instance: int, out_mif: Path) -> None:
    """Save a memory instance's entire content to a .mif.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    instance : int
        In-System Memory Content Editor instance index of the target
        memory.
    out_mif : Path
        Path to write the .mif to (overwritten if it already exists).

    Returns
    -------
    None
    """
    run_tcl(link, "dump_mem.tcl", instance, out_mif)
