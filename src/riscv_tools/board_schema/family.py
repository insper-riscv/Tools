"""Read a device family file (`boards/families/<family>.yaml`)."""

from typing import Any

from riscv_tools.board_schema.fields import Section, present, raise_if
from riscv_tools.board_schema.model import Family, PllSpec

LOGIC_UNITS = ("alm", "le")
PLL_IPS = ("altera_pll", "altpll")
ONCHIP_FLASH_IPS = ("altera_onchip_flash",)
VCO_BOUNDS = 2


def _pll(parent: Section) -> PllSpec | None:
    """Read the `pll` section.

    Parameters
    ----------
    parent : Section
        The family.

    Returns
    -------
    PllSpec or None
        The PLL, None when the section is invalid.
    """
    pll = parent.section("pll")
    if pll is None:
        return None
    ip = pll.text("ip", choices=PLL_IPS)
    vco = pll.items("vco_mhz")
    pattern = pll.text("clock_node_pattern")
    outputs = pll.integer("outputs_max", minimum=1)
    pll.done()
    numbers = [v for v in vco if isinstance(v, int | float)]
    if len(vco) != VCO_BOUNDS or len(numbers) != VCO_BOUNDS:
        pll.fail("vco_mhz", "must be [min, max]")
        return None
    if numbers[0] > numbers[1]:
        pll.fail("vco_mhz", "must be [min, max] with min not above max")
        return None
    if ip is None or pattern is None or outputs is None:
        return None
    return PllSpec(
        ip, (float(numbers[0]), float(numbers[1])), pattern, outputs
    )


def _fmax(parent: Section) -> dict[str, float | None]:
    """Read the measured frequency of each speed grade.

    Parameters
    ----------
    parent : Section
        The family.

    Returns
    -------
    dict of str to float or None
        The core frequency in MHz, keyed by speed grade.
    """
    fmax = parent.section("fmax")
    if fmax is None:
        return {}
    grades = fmax.section("core_mhz_by_grade")
    fmax.done()
    if grades is None:
        return {}
    found = {
        key: grades.number(key, nullable=True, minimum=0)
        for key in grades.names()
    }
    grades.done()
    return found


def _block_ram(parent: Section) -> tuple[str | None, int | None]:
    """Read the `block_ram` section.

    Parameters
    ----------
    parent : Section
        The family.

    Returns
    -------
    tuple of (str or None, int or None)
        The kind of the block and its bits.
    """
    block = parent.section("block_ram")
    if block is None:
        return None, None
    kind = block.text("kind")
    bits = block.integer("bits_per_block", minimum=1)
    block.done()
    return kind, bits


def parse_family(raw: Any, label: str = "family") -> Family:
    """Read a family file, checking every field.

    Parameters
    ----------
    raw : Any
        The parsed YAML.
    label : str, optional
        The name used in the messages.

    Returns
    -------
    Family
        The family.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section(label, raw, problems)
    name = top.text("family")
    quartus = top.text("quartus_family")
    unit = top.text("logic_unit", choices=LOGIC_UNITS)
    pll = _pll(top)
    kind, bits = _block_ram(top)
    memory_ip = top.text("memory_ip")
    jtag = top.flag("virtual_jtag")
    flash = top.text("onchip_flash", nullable=True, choices=ONCHIP_FLASH_IPS)
    fmax = _fmax(top)
    calibration = top.text("calibration", required=False, nullable=True)
    slew_rate = top.flag("slew_rate", required=False, default=True)
    qsf = tuple(top.texts("qsf", required=False))
    top.done()
    raise_if(problems)
    return Family(
        present(name),
        present(quartus),
        present(unit),
        present(pll),
        present(kind),
        present(bits),
        present(memory_ip),
        jtag,
        flash,
        fmax,
        calibration,
        slew_rate,
        qsf,
    )
