"""Run the ACT4 ELFs on the board, from the SDRAM.

Each ELF is one flat image that starts at the base of the SDRAM. The
host loads it through the SDRAM debug port while the core is parked in
the boot ROM, then lets the core go:

1. Once, the FLASH gets a three-instruction stub (`fence.i`,
   `lui t0, base`, `jr t0`) that sends the core to the ELF.
2. For each ELF, the host zeroes the SDRAM region, writes the image,
   restarts the core by writing fromhost and reads the HTIF `tohost`
   word until it is odd (1 is a PASS) or the time runs out.
3. With `act.board_display` set, the display shows `AC` and the ELF
   number (`AC0001`), and the first red LED stays lit after a failure.

The board must be programmed with the SDRAM platform and the core
parked.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

from riscv_tools import (
    bin_to_image,
    display,
    htif,
    rom_writer,
    sdram_debug,
)
from riscv_tools.certify import core as certify_core
from riscv_tools.certify.flash import image_words, write_flash_stub
from riscv_tools.certify.segments import load_segments, region_image
from riscv_tools.certify.symbols import elf_symbol
from riscv_tools.jtag import JtagLink

_DEFAULT_REGION_BYTES = 0x100000


_DEFAULT_TIMEOUT_S = 30


# What run_elf's result means: True is a PASS, False a FAIL and None a
# timeout.
VERDICTS = {True: "PASS", False: "FAIL", None: "TIMEOUT"}


@dataclass(frozen=True)
class SdramRegion:
    """Where and for how long an ELF runs in the SDRAM."""

    base: int
    words: int
    timeout_s: float


def run_elf(
    link: JtagLink,
    cfg: dict[str, Any],
    elf: Path,
    region: SdramRegion,
) -> tuple[bool | None, int, float]:
    """Load one ELF into the SDRAM, run it and read its `tohost`.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    cfg : dict of {str: Any}
        The merged project config: memory.ram_base/fromhost_addr and the
        RAM backend.
    elf : Path
        The ACT4 ELF.
    region : SdramRegion
        The first address of the SDRAM, the words of it that the ELF
        may use (zeroed before the load) and how long to wait for
        `tohost`.

    Returns
    -------
    tuple of (bool or None, int, float)
        True for a PASS, False for a FAIL, None for a timeout; the
        number of words loaded; the seconds from the restart to the end.
    """
    tohost_word = (elf_symbol(elf, "tohost") - region.base) // 4
    words = image_words(elf, region.base)
    sdram_debug.fill(link, 0, region.words, 0)
    sdram_debug.load_words(link, 0, words)

    htif.pulse_fromhost_configured(link, cfg)
    started = time.monotonic()
    while time.monotonic() - started < region.timeout_s:
        (tohost,) = sdram_debug.read_words(link, tohost_word, 1)
        if tohost & 1:
            return tohost == 1, len(words), time.monotonic() - started
    return None, len(words), time.monotonic() - started


def run_elf_flash(
    link: JtagLink,
    cfg: dict[str, Any],
    elf: Path,
    region: SdramRegion,
    build_dir: Path,
) -> tuple[bool | None, int, float]:
    """Load one ELF into the FLASH and the SDRAM, run it, read `tohost`.

    The code and the constants of the ELF go to the storage of the
    FLASH chip over the memory editor, the data to the SDRAM through
    the debug port. The boot ROM jumps to the FLASH after the restart,
    with a `fence.i` that drops the lines of the previous ELF.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    cfg : dict of {str: Any}
        The merged project config: memory.ram_base/fromhost_addr,
        quartus.rom_mem_instances, act.flash_base and act.flash_words
        (the words of the FLASH storage in the FPGA).
    elf : Path
        The ACT4 ELF of the target with the FLASH behind the caches.
    region : SdramRegion
        The first address of the SDRAM, the words of it that the ELF
        may use (zeroed before the load) and how long to wait for
        `tohost`.
    build_dir : Path
        Where the FLASH image goes.

    Returns
    -------
    tuple of (bool or None, int, float)
        True for a PASS, False for a FAIL, None for a timeout; the
        number of words of code in the FLASH; the seconds from the
        restart to the end.

    Raises
    ------
    ValueError
        The code of the ELF does not fit in the FLASH storage.
    """
    flash_words = int(cfg["act"]["flash_words"])
    flash_base = int(str(cfg["act"]["flash_base"]), 0)
    image = region_image(load_segments(elf), flash_base, region.base)
    if len(image) > flash_words * 4:
        raise ValueError(
            f"{elf.stem}: the code takes {len(image)} bytes, "
            f"the FLASH storage {flash_words * 4}"
        )
    bin_path = build_dir / "flash_image.bin"
    mif_path = build_dir / "flash_image.mif"
    bin_path.write_bytes(image or bytes(4))
    bin_to_image.bin_to_mif(bin_path, mif_path, depth=flash_words)

    tohost_word = (elf_symbol(elf, "tohost") - region.base) // 4
    sdram_debug.fill(link, 0, region.words, 0)
    sdram_debug.load_words(link, 0, image_words(elf, region.base))
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instances"], mif_path)

    htif.pulse_fromhost_configured(link, cfg)
    started = time.monotonic()
    while time.monotonic() - started < region.timeout_s:
        (tohost,) = sdram_debug.read_words(link, tohost_word, 1)
        if tohost & 1:
            return tohost == 1, len(image) // 4, time.monotonic() - started
    return None, len(image) // 4, time.monotonic() - started


@dataclass(frozen=True)
class BoardRun:
    """Where the scratch files go and whether the display is used."""

    build_dir: Path
    show_display: bool


class BoardOptions(TypedDict, total=False):
    """The optional settings of `run_suite_on_board`."""

    build: bool


def _find_elfs(
    act_cfg: dict[str, Any],
    root: Path,
    only: list[str] | None,
    *,
    build: bool,
) -> list[Path]:
    """List the ACT4 ELFs to run, building them first when asked.

    Parameters
    ----------
    act_cfg : dict of {str: Any}
        The `act` section of the config.
    root : Path
        The consuming project's root directory.
    only : list of str or None
        Names of the ELFs to keep; all when empty or None.
    build : bool
        Build with ACT4's own `make` first.

    Returns
    -------
    list of Path
        The ELFs to run.
    """
    return [
        e
        for e in certify_core.suite_elfs({"act": act_cfg}, root, build=build)
        if not only or e.stem in only
    ]


def run_suite_on_board(
    cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    link: JtagLink,
    only: list[str] | None = None,
    **options: Unpack[BoardOptions],
) -> dict[str, bool | None]:
    """Build the SDRAM target ACT4 ELFs and run each one on the board.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config:
        act.vendor_dir/target_config/extensions/jobs/
        sdram_base/sdram_region_bytes/board_timeout_s, memory and
        quartus.
    root : Path
        The consuming project's root directory.
    build_dir : Path
        Where scratch files go.
    link : JtagLink
        Which JTAG cable/chip to use.
    only : list of str, optional
        Names of the ELFs to run (without the extension); all when
        omitted.
    **options : Unpack[BoardOptions]
        The keyword settings, described below.
    build : bool, optional
        Build the ELFs with ACT4's own `make` first. With False the ELFs
        that an earlier build left under the ACT4 work directory are
        used: the build needs the Ruby and Sail toolchain, which a
        machine with the board may not have.

    Returns
    -------
    dict of {str: bool or None}
        The result of each ELF run: True PASS, False FAIL, None timeout.
    """
    act_cfg = cfg["act"]
    region = _sdram_region(act_cfg)
    elfs = _find_elfs(act_cfg, root, only, build=options.get("build", True))
    build_dir.mkdir(parents=True, exist_ok=True)
    if act_cfg.get("flash_base") is None:
        write_flash_stub(link, cfg, build_dir, region.base)
    return _run_elfs(
        link,
        cfg,
        elfs,
        region,
        BoardRun(build_dir, bool(act_cfg.get("board_display", False))),
    )


def _sdram_region(act_cfg: dict[str, Any]) -> SdramRegion:
    """Read the SDRAM region and the timeout from the `act:` config.

    Parameters
    ----------
    act_cfg : dict of {str: Any}
        The `act:` section of the config.

    Returns
    -------
    SdramRegion
        The base, the size in words and the per-ELF timeout.
    """
    return SdramRegion(
        base=int(str(act_cfg["sdram_base"]), 0),
        words=int(
            str(act_cfg.get("sdram_region_bytes", _DEFAULT_REGION_BYTES)), 0
        )
        // 4,
        timeout_s=float(act_cfg.get("board_timeout_s", _DEFAULT_TIMEOUT_S)),
    )


def _run_elfs(
    link: JtagLink,
    cfg: dict[str, Any],
    elfs: list[Path],
    region: SdramRegion,
    run: BoardRun,
) -> dict[str, bool | None]:
    """Run each ELF on the board, showing its number on the display.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    cfg : dict of {str: Any}
        The merged project config.
    elfs : list of Path
        The ELFs to run, in order.
    region : SdramRegion
        Where the ELFs are loaded and how long each may run.
    run : BoardRun
        The directory of the scratch files and whether to write the ELF
        number and the failure flag to the board's display.

    Returns
    -------
    dict of {str: bool or None}
        The result of each ELF run: True PASS, False FAIL, None timeout.
    """
    show_display = run.show_display
    if show_display:
        # a new session starts without a failure
        display.write_fail(link, False)
    results: dict[str, bool | None] = {}
    for index, elf in enumerate(elfs):
        if show_display:
            display.write_display(link, display.encode_act(index + 1))
        if cfg["act"].get("flash_base") is not None:
            passed, words, seconds = run_elf_flash(
                link, cfg, elf, region, run.build_dir
            )
        else:
            passed, words, seconds = run_elf(link, cfg, elf, region)
        results[elf.stem] = passed
        if show_display and passed is not True:
            # the first red LED stays lit once any ELF has failed or
            # timed out
            display.write_fail(link, True)
        verdict = VERDICTS[passed]
        print(f"{elf.stem}: {verdict} ({words * 4} bytes, {seconds:.1f}s)")
    return results
