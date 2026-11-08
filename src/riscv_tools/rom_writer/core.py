"""Load a new ROM image into an already-programmed board over JTAG."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from riscv_tools import flash_loader, mem_edit, mem_validator, nor_program
from riscv_tools.jtag import JtagLink

MEM_EDIT = "mem_edit"
JTAG_LOADER = "jtag_loader"
NOR_PROGRAM = "nor_program"
METHODS = (MEM_EDIT, JTAG_LOADER, NOR_PROGRAM)


def method_from_config(cfg: dict[str, Any]) -> str:
    """Pick the way the ROM is written from the merged project config.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses quartus.rom_write_method.

    Returns
    -------
    str
        "mem_edit" (the In-System Memory Content Editor, the default) or
        "jtag_loader" (the FLASH loader of the Memory repository) or
        "nor_program" (a program the host leaves in the SDRAM writes the
        bank of the NOR chip, see nor_program).

    Raises
    ------
    ValueError
        The key holds something else.
    """
    method = cfg["quartus"].get("rom_write_method", MEM_EDIT)
    if method not in METHODS:
        raise ValueError(
            f"quartus.rom_write_method is {method!r}, expected one of "
            f"{', '.join(METHODS)}"
        )
    return str(method)


def mif_words(mif_path: Path) -> list[int]:
    """Read a .mif into the list of its words, from address 0.

    Parameters
    ----------
    mif_path : Path
        Path to the .mif.

    Returns
    -------
    list of int
        One value per word up to the last one the file defines; the
        addresses the file leaves out are zero.
    """
    parsed = mem_validator.parse_mif_words(mif_path)
    return [parsed.get(i, 0) for i in range(max(parsed, default=-1) + 1)]


def write_rom(
    link: JtagLink,
    rom_mem_instances: Sequence[int],
    mif_path: Path,
    method: str = MEM_EDIT,
    *,
    restart: bool = True,
) -> bool:
    """Load a new ROM image into an already-programmed board over JTAG.

    With the "mem_edit" method it pairs with htif.pulse_fromhost to make
    the core jump back to _start and run the image (see crt0.S in the
    consuming project). With "jtag_loader" the loader halts the core,
    writes the single FLASH copy, checks it and releases the core, which
    restarts from the boot memory by itself.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    rom_mem_instances : sequence of int
        In-System Memory Content Editor instance indices of the ROM
        (quartus.rom_mem_instances). Every instance gets the same
        content, in order, so a ROM duplicated into several BRAMs stays
        in sync. Unused by the "jtag_loader" method.
    mif_path : Path
        Path to the .mif whose content replaces the ROM.
    method : str, optional
        "mem_edit" (default) or "jtag_loader".
    restart : bool, optional
        With "jtag_loader", release the core after the check. Defaults
        to True. With False it stays halted until
        flash_loader.release is called.

    Returns
    -------
    bool
        True when the core was released and restarts by itself, so the
        caller must not pulse fromhost; False when it must.

    Raises
    ------
    ValueError
        The method is "mem_edit" and rom_mem_instances is empty.
    """
    if method == JTAG_LOADER:
        flash_loader.load_image(link, mif_words(mif_path), restart=restart)
        return restart
    # A FLASH de uma só cópia não é instância do editor: a lista vazia é
    # válida na configuração, mas só o carregador JTAG sabe gravá-la.
    if not rom_mem_instances:
        raise ValueError(
            "the In-System Memory Content Editor has no ROM instance to "
            "write (quartus.rom_mem_instances is empty); set "
            "quartus.rom_write_method to jtag_loader"
        )
    mem_edit.write_full_multi(link, rom_mem_instances, mif_path)
    return False


def write_rom_configured(
    link: JtagLink, cfg: dict[str, Any], mif_path: Path
) -> bool:
    """Write the ROM the way the merged project config asks.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The merged project config; uses quartus.rom_write_method and,
        for "mem_edit", quartus.rom_mem_names or
        quartus.rom_mem_instances (an empty list is valid, the FLASH of
        a single copy is not an editor instance, but only "jtag_loader"
        can write it).
    mif_path : Path
        Path to the .mif whose content replaces the ROM.

    Returns
    -------
    bool
        As write_rom: True when the core restarted by itself.

    Raises
    ------
    ValueError
        The method is "mem_edit" and the ROM has no editor instance.
    """
    method = method_from_config(cfg)
    if method == NOR_PROGRAM:
        return write_nor(link, cfg, mif_path)
    # O carregador não usa o editor: não lista a placa à toa.
    instances = (
        [] if method == JTAG_LOADER else mem_edit.rom_instances(link, cfg)
    )
    return write_rom(link, instances, mif_path, method)


def write_nor(link: JtagLink, cfg: dict[str, Any], mif_path: Path) -> bool:
    """Write the program of a FLASH `.mif` into bank A of the NOR chip.

    The core is left parked in `rv32_wait_restart`, so the caller pulses
    `fromhost` to start the new program.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The merged project config; the programmer was built by
        `compile` into `<build_dir>/nor_programmer/nor_programmer.bin`,
        relative to the current directory (the project root).
    mif_path : Path
        The `.mif` of the FLASH, the bank image at `memory.rom_base`.

    Returns
    -------
    bool
        False: the core does not restart by itself.

    Raises
    ------
    RuntimeError
        The programmer did not report success.
    """
    memory = cfg["memory"]
    image = nor_program.load_bank_image(
        mif_words(mif_path), int(memory["rom_base"])
    )
    if cfg.get("flash_image", {}).get("bank", "A") != "A":
        raise ValueError("nor_program writes bank A of the NOR chip")
    dest = int(memory["rom_base"])
    programmer = (
        Path(cfg["paths"]["build_dir"])
        / "nor_programmer"
        / "nor_programmer.bin"
    )
    done = nor_program.program_bank(link, cfg, programmer, (image, dest))
    if done != 1:
        raise RuntimeError(f"the NOR programmer failed (tohost {done:#x})")
    return False
