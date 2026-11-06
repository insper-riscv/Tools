"""Primitives of the FLASH loader, a mem_edit for the internal FLASH.

The loader is a Virtual JTAG instance in front of the second port of
the FLASH (see Memory's docs/pt-br/rom/flash_loader.md). It writes only
while the core is halted, and releasing the core restarts it from the
boot memory. Addresses here are word addresses counted from the start of
the FLASH IP. Pure mechanism, no policy: the callers decide what to
load.
"""

import tempfile
from collections.abc import Sequence
from pathlib import Path

from riscv_tools.jtag import JtagLink, run_tcl

_WORD_MASK = 0xFFFFFFFF
_TCL = "flash_loader.tcl"


def image_checksum(first_word: int, words: Sequence[int]) -> int:
    """Return the checksum the loader keeps over the words it writes.

    Parameters
    ----------
    first_word : int
        Word address of the first word of the image.
    words : sequence of int
        The 32-bit values, in address order.

    Returns
    -------
    int
        The sum of every word and its word address, modulo 2**32.
    """
    return sum(w + first_word + i for i, w in enumerate(words)) & _WORD_MASK


def halt(link: JtagLink) -> None:
    """Halt the core, which hands the FLASH second port to the loader.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to talk to.

    Returns
    -------
    None
    """
    run_tcl(link, _TCL, "halt")


def release(link: JtagLink) -> None:
    """Release the core, which restarts from the boot memory.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to talk to.

    Returns
    -------
    None
    """
    run_tcl(link, _TCL, "run")


def read_words(
    link: JtagLink, word_address: int, word_count: int = 1
) -> list[int]:
    """Halt the core and read contiguous words of the FLASH.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    word_address : int
        Word address of the first word.
    word_count : int, optional
        How many contiguous words to read. Defaults to 1.

    Returns
    -------
    list of int
        The word_count values read, in address order. The core stays
        halted.

    Raises
    ------
    RuntimeError
        The script's output did not contain the expected "WORDS=" line.
    """
    result = run_tcl(link, _TCL, "read", word_address, word_count)
    for line in result.stdout.splitlines():
        if line.startswith("WORDS="):
            return [int(w) for w in line.split("=", 1)[1].split()]
    raise RuntimeError(f"{_TCL} produced no WORDS= line:\n{result.stdout}")


def load_image(
    link: JtagLink,
    words: Sequence[int],
    word_address: int = 0,
    *,
    restart: bool = True,
) -> None:
    """Write an image into the FLASH with the core halted and check it.

    One JTAG session halts the core, writes the words in long scans,
    compares the count and the checksum the loader reports with the
    image's, and releases the core when restart is true.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    words : sequence of int
        The 32-bit values, in address order.
    word_address : int, optional
        Word address of the first word. Defaults to 0.
    restart : bool, optional
        Release the core after the check, so it runs the new image from
        the boot memory. Defaults to True; with False the core stays
        halted until release is called.

    Returns
    -------
    None

    Raises
    ------
    subprocess.CalledProcessError
        The script failed, for instance because the image arrived wrong.
    """
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "image.txt"
        image.write_text("".join(f"{w & _WORD_MASK:08x}\n" for w in words))
        run_tcl(
            link,
            _TCL,
            "load",
            word_address,
            image,
            len(words),
            image_checksum(word_address, words),
            "run" if restart else "hold",
        )
