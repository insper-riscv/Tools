"""Generic In-System Memory Content Editor primitives, shared by
rom_writer/ram_zero/ram_dump/mailbox. Pure mechanism, no policy: each
of those modules decides WHICH instance/address/content to use."""
from pathlib import Path

from riscv_tools.jtag import JtagLink, run_tcl


def write_full(link: JtagLink, instance: int, mif_path: Path) -> None:
    """Overwrites a memory instance's ENTIRE depth from a .mif."""
    run_tcl(link, "write_full.tcl", instance, mif_path)


def write_word(link: JtagLink, instance: int, word_offset: int, value: int) -> None:
    """Overwrites exactly one word, leaving the rest of the instance
    untouched."""
    run_tcl(link, "write_word.tcl", instance, word_offset, value)


def read_words(link: JtagLink, instance: int, word_offset: int, word_count: int = 1) -> list[int]:
    result = run_tcl(link, "read_words.tcl", instance, word_offset, word_count, capture=True)
    for line in result.stdout.splitlines():
        if line.startswith("WORDS="):
            return [int(w) for w in line.split("=", 1)[1].split()]
    raise RuntimeError(f"read_words.tcl produced no WORDS= line:\n{result.stdout}")


def dump(link: JtagLink, instance: int, out_mif: Path) -> None:
    """Saves a memory instance's entire content to a .mif."""
    run_tcl(link, "dump_mem.tcl", instance, out_mif)
