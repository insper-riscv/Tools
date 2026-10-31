"""Read the HTIF tohost word and write fromhost over JTAG."""

from typing import Any

from riscv_tools import ram_target
from riscv_tools.jtag import JtagLink

#: tohost low word of a test that passed. A failure is (code << 1) | 1,
#: with code != 0.
PASS = 1


def is_done(tohost: int) -> bool:
    """Tell whether a tohost low word means the test has ended.

    Parameters
    ----------
    tohost : int
        The low word of tohost.

    Returns
    -------
    bool
        True when bit 0 is set (a pass or a failure).
    """
    return bool(tohost & 1)


def fail_code(tohost: int) -> int:
    """Return the failure code that a tohost low word carries.

    Parameters
    ----------
    tohost : int
        The low word of a finished test (bit 0 set).

    Returns
    -------
    int
        0 for a pass, otherwise the code passed to RV32_FAIL().
    """
    return 0 if tohost == PASS else tohost >> 1


def word_offset(ram_base: int, addr: int, *, relative: bool = True) -> int:
    """Convert a byte address into a word offset.

    - relative=True (default): offset from the RAM base, (addr -
      ram_base) // 4, which is what the In-System Memory Content Editor
      expects.
    - relative=False: absolute word offset, addr // 4, for code that
      reads the CPU's raw address bus (for example a cocotb testbench),
      which always carries absolute addresses.

    The two differ whenever ram_base != 0; picking the wrong one
    silently misses every tohost and fromhost access.

    Parameters
    ----------
    ram_base : int
        RAM's base byte address (memory.ram_base). Ignored when
        relative=False.
    addr : int
        The byte address to convert (for example memory.tohost_addr),
        always absolute either way.
    relative : bool
        Which convention to use. Defaults to True, the JTAG convention.

    Returns
    -------
    int
        The word offset, in whichever convention `relative` selected.
    """
    if relative:
        return (addr - ram_base) // 4
    return addr // 4


def read_tohost(
    link: JtagLink,
    ram_mem_instance: ram_target.RamTarget,
    ram_base: int,
    tohost_addr: int,
) -> int:
    """Read the low word of tohost.

    It is 0 while the test runs, 1 for a pass and (code << 1) | 1 for a
    failure; a test writes it through RV32_PASS() and RV32_FAIL().

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached (see ram_target).
    ram_base : int
        RAM's base byte address (memory.ram_base).
    tohost_addr : int
        Byte address of tohost (memory.tohost_addr).

    Returns
    -------
    int
        The tohost low word.
    """
    words = ram_target.read_words(
        link, ram_mem_instance, word_offset(ram_base, tohost_addr), 1
    )
    return words[0]


def pulse_fromhost(
    link: JtagLink,
    ram_mem_instance: ram_target.RamTarget,
    ram_base: int,
    fromhost_addr: int,
) -> None:
    """Write a nonzero word to fromhost, the restart request.

    A core waiting in rv32_wait_restart (crt0.S) then jumps back to
    _start and runs whatever ROM content is currently loaded.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached (see ram_target).
    ram_base : int
        RAM's base byte address (memory.ram_base).
    fromhost_addr : int
        Byte address of fromhost (memory.fromhost_addr).
    """
    ram_target.write_word(
        link, ram_mem_instance, word_offset(ram_base, fromhost_addr), 1
    )


def clear_tohost(
    link: JtagLink,
    ram_mem_instance: ram_target.RamTarget,
    ram_base: int,
    tohost_addr: int,
) -> None:
    """Set both words of tohost back to 0 before a test starts.

    Without this, a test is judged by what the previous test left in
    tohost, so a boot code that does not clear it makes the host read
    the old result at once and report a test that never ran.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached (see ram_target).
    ram_base : int
        RAM's base byte address (memory.ram_base).
    tohost_addr : int
        Byte address of tohost (memory.tohost_addr).
    """
    offset = word_offset(ram_base, tohost_addr)
    ram_target.write_word(link, ram_mem_instance, offset, 0)
    ram_target.write_word(link, ram_mem_instance, offset + 1, 0)


def read_tohost_configured(link: JtagLink, cfg: dict[str, Any]) -> int:
    """Read the tohost of the RAM that the project's config describes.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    cfg : dict of {str: Any}
        The loaded config.yaml; needs `memory` and the RAM backend.

    Returns
    -------
    int
        The tohost low word (see read_tohost).
    """
    memory = cfg["memory"]
    return read_tohost(
        link,
        ram_target.target_from_config(cfg),
        memory["ram_base"],
        memory["tohost_addr"],
    )


def clear_tohost_configured(link: JtagLink, cfg: dict[str, Any]) -> None:
    """Clear the tohost of the RAM that the project's config describes.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The loaded config.yaml; needs `memory` and the RAM backend.
    """
    memory = cfg["memory"]
    clear_tohost(
        link,
        ram_target.target_from_config(cfg),
        memory["ram_base"],
        memory["tohost_addr"],
    )


def pulse_fromhost_configured(link: JtagLink, cfg: dict[str, Any]) -> None:
    """Write fromhost of the RAM that the project's config describes.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The loaded config.yaml; needs `memory` and the RAM backend.
    """
    memory = cfg["memory"]
    pulse_fromhost(
        link,
        ram_target.target_from_config(cfg),
        memory["ram_base"],
        memory["fromhost_addr"],
    )
