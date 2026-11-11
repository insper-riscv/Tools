"""The addresses that follow from the sizes of the memories."""

from dataclasses import dataclass

from riscv_tools.new_project.spec import BANK_COUNT

STDOUT_BELOW_TOP = 0x420
TOHOST_BELOW_TOP = 0x18
FROMHOST_BELOW_TOP = 0x10


@dataclass(frozen=True)
class Bank:
    """One bank of the FLASH.

    Parameters
    ----------
    name : str
        `A` or `B`.
    base : int
        First address of the bank.
    size : int
        Size of the bank in bytes.
    """

    name: str
    base: int
    size: int


def reserved_bases(ram_base: int, ram_bytes: int) -> dict[str, int]:
    """Place the words the host shares with the program.

    They sit at the top of the RAM: the `stdout` buffer, then the
    `tohost` and `fromhost` words.

    Parameters
    ----------
    ram_base : int
        First address of the RAM.
    ram_bytes : int
        Size of the RAM in bytes.

    Returns
    -------
    dict of {str: int}
        The base address of `stdout`, `tohost` and `fromhost`.
    """
    top = ram_base + ram_bytes
    return {
        "stdout": top - STDOUT_BELOW_TOP,
        "tohost": top - TOHOST_BELOW_TOP,
        "fromhost": top - FROMHOST_BELOW_TOP,
    }


def flash_banks(base: int, size: int, sector: int) -> tuple[Bank, ...]:
    """Split the FLASH into two banks of whole sectors.

    Parameters
    ----------
    base : int
        First address of the FLASH.
    size : int
        Size of the FLASH in bytes.
    sector : int
        Erase sector of the FLASH in bytes.

    Returns
    -------
    tuple of Bank
        Banks A and B, side by side; the first takes the larger half
        when the sectors do not divide evenly.
    """
    sectors = size // sector
    first = (sectors + BANK_COUNT - 1) // BANK_COUNT * sector
    return (
        Bank("A", base, first),
        Bank("B", base + first, size - first),
    )


def size_text(size: int) -> str:
    """Write a size the way `platform.yaml` does.

    Parameters
    ----------
    size : int
        Size in bytes.

    Returns
    -------
    str
        `4M`, `64K` or the plain number of bytes.
    """
    for suffix, unit in (("M", 1 << 20), ("K", 1 << 10)):
        if size % unit == 0:
            return f"{size // unit}{suffix}"
    return str(size)
