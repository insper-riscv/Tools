"""Fast estimate of the fit of a profile, without the Quartus.

The estimate adds the cost of each block of the profile with the
coefficients of the calibration table of the family (section 7.2 of the
plan). The mapping from the profile to the terms is one function,
``terms``, that the calibration also uses to fit the coefficients, so
the fit and the estimate cannot disagree about what a term means.
"""

import math
from dataclasses import dataclass, field

from riscv_tools.fit_estimate.policy import (
    Capacity,
    Finding,
    blocks_finding,
    logic_finding,
    uncalibrated_finding,
)
from riscv_tools.fit_estimate.table import CalibrationTable

BITS_PER_KBIT = 1024
CSR_EXTENSIONS = ("Zicsr", "Zicntr", "Zihpm")
FLAG_EXTENSIONS = ("Zicclsm", "Zifencei", "Zimop", "Zicond")
FLAG_EXTRAS = ("Zihintntl", "Zihintpause", "Interrupts")


@dataclass(frozen=True)
class ProfileSpec:
    """What the estimate needs to know about a profile.

    Parameters
    ----------
    base : str
        ``"rv32i"`` or ``"rv32e"``.
    extensions : frozenset of str
        Extensions of the profile, as the Core's matrix names them.
    extras : frozenset of str
        ``extras`` of the platform.
    hpm_counters : int
        Counters of the Zihpm (0 to 29).
    hpm_width : int
        Bits of each counter.
    icache_kbit : float or None
        Instruction cache in kbit, None without it.
    dcache_kbit : float or None
        Data cache in kbit, None without it.
    peripherals : frozenset of str
        Peripherals counted by the table (those it separates).
    backends : tuple of str
        Controllers of device (``sdram_16``, ``nor``, ...).
    emulated_bytes : tuple of int
        Bytes of each emulated memory.
    register_blocks : int
        Blocks of RAM used by register files and buffers.
    """

    base: str = "rv32i"
    extensions: frozenset[str] = frozenset()
    extras: frozenset[str] = frozenset()
    hpm_counters: int = 0
    hpm_width: int = 0
    icache_kbit: float | None = None
    dcache_kbit: float | None = None
    peripherals: frozenset[str] = frozenset()
    backends: tuple[str, ...] = ()
    emulated_bytes: tuple[int, ...] = ()
    register_blocks: int = 0


@dataclass(frozen=True)
class Estimate:
    """Result of the estimate of one profile on one board.

    Parameters
    ----------
    logic : float or None
        Logic estimated in the unit of the family, already multiplied by
        the ratio fit / synthesis; None without calibration.
    blocks : int
        Blocks of RAM the profile needs.
    findings : list of Finding
        V11, V12, V13 and V18.
    missing : tuple of str
        Terms of the profile whose coefficient is null.
    """

    logic: float | None
    blocks: int
    findings: list[Finding] = field(default_factory=list[Finding])
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Tell whether no finding is an error."""
        return all(finding.severity != "E" for finding in self.findings)


def _has(spec: ProfileSpec, name: str) -> bool:
    """Tell whether an extension is on, whichever list names it."""
    return name in spec.extensions or name in spec.extras


def terms(
    spec: ProfileSpec, bits_per_block: int | None = None
) -> dict[str, float]:
    """Map a profile to the value of each term of the model.

    The implications of the ISA are applied here: Zicntr and Zihpm imply
    Zicsr, M implies Zmmul, and Sscofpmf needs the Zihpm and the
    interrupts. A term absent from the result is zero.

    Parameters
    ----------
    spec : ProfileSpec
        The profile.
    bits_per_block : int, optional
        Bits of a block of RAM; with it the term of the glue of the
        emulated memories counts their blocks.

    Returns
    -------
    dict of {str: float}
        Coefficient path to the value it multiplies.
    """
    out: dict[str, float] = {f"core.{spec.base}": 1.0}
    has_m = "M" in spec.extensions
    if any(name in spec.extensions for name in CSR_EXTENSIONS):
        out["extensions.Zicsr"] = 1.0
    if "Zicntr" in spec.extensions:
        out["extensions.Zicntr"] = 1.0
    if has_m or "Zmmul" in spec.extensions:
        out["extensions.Zmmul"] = 1.0
    if has_m:
        out["extensions.M"] = 1.0
    out.update(
        {f"extensions.{n}": 1.0 for n in FLAG_EXTENSIONS if _has(spec, n)}
    )
    out.update({f"extras.{n}": 1.0 for n in FLAG_EXTRAS if _has(spec, n)})
    hpm = "Zihpm" in spec.extensions
    if hpm:
        count = float(spec.hpm_counters)
        out["zihpm.a0"] = 1.0
        out["zihpm.a1"] = count
        out["zihpm.a2"] = count * spec.hpm_width
    if hpm and _has(spec, "Sscofpmf") and _has(spec, "Interrupts"):
        out["extras.Sscofpmf"] = 1.0
    for cache, kbit in (
        ("icache", spec.icache_kbit),
        ("dcache", spec.dcache_kbit),
    ):
        if kbit is not None:
            out[f"cache.{cache}.c0"] = 1.0
            out[f"cache.{cache}.c1"] = float(kbit)
    out.update({f"peripherals.{name}": 1.0 for name in spec.peripherals})
    out.update({f"backends.{name}": 1.0 for name in spec.backends})
    if bits_per_block and spec.emulated_bytes:
        out["per_block_glue"] = float(
            sum(
                math.ceil(8 * size / bits_per_block)
                for size in spec.emulated_bytes
            )
        )
    return out


def blocks_needed(spec: ProfileSpec, bits_per_block: int) -> int:
    """Count the blocks of RAM of a profile (section 7.2 of the plan).

    Parameters
    ----------
    spec : ProfileSpec
        The profile.
    bits_per_block : int
        Bits of one block of the family.

    Returns
    -------
    int
        Blocks of the emulated memories, of the caches and of the
        registers.
    """
    memories = sum(
        math.ceil(8 * size / bits_per_block) for size in spec.emulated_bytes
    )
    caches = sum(
        math.ceil(kbit * BITS_PER_KBIT / bits_per_block)
        for kbit in (spec.icache_kbit, spec.dcache_kbit)
        if kbit is not None
    )
    return memories + caches + spec.register_blocks


def estimate_logic(
    spec: ProfileSpec, table: CalibrationTable, bits_per_block: int | None
) -> tuple[float, tuple[str, ...]]:
    """Add the known terms of the table.

    Parameters
    ----------
    spec : ProfileSpec
        The profile.
    table : CalibrationTable
        Calibration of the family.
    bits_per_block : int or None
        Bits of a block of RAM of the family.

    Returns
    -------
    tuple
        The sum of the terms with a coefficient and the paths of the
        terms that have none (null or absent from the table).
    """
    total = 0.0
    missing: list[str] = []
    values = terms(spec, bits_per_block)
    for path, value in values.items():
        if value == 0.0:
            continue
        coefficient = table.coefficients.get(path)
        if coefficient is None:
            missing.append(path)
        else:
            total += coefficient * value
    return total, tuple(missing)


def estimate(
    spec: ProfileSpec,
    table: CalibrationTable,
    capacity: Capacity,
    board: str,
) -> Estimate:
    """Estimate whether a profile fits a board (V11, V12, V13, V18).

    There is no option to force a result: the thresholds are constants
    of the policy. The logic is only an error when the family is
    validated (maximum error up to 10 %); until then the check gives
    V18 and the fit decides.

    Parameters
    ----------
    spec : ProfileSpec
        The profile with its backends.
    table : CalibrationTable
        Calibration of the family of the board.
    capacity : Capacity
        ``resources`` of the board.
    board : str
        Name of the board, for the messages.

    Returns
    -------
    Estimate
        The numbers and the findings.
    """
    blocks = blocks_needed(spec, capacity.bits_per_block)
    findings: list[Finding] = []
    block_issue = blocks_finding(blocks, capacity, board)
    if block_issue:
        findings.append(block_issue)
    total, missing = estimate_logic(spec, table, capacity.bits_per_block)
    known = any(v is not None for v in table.coefficients.values())
    if not known:
        findings.append(uncalibrated_finding(table.family))
        return Estimate(None, blocks, findings, missing)
    ratio = table.map_to_fit_ratio or 1.0
    logic = total * ratio
    if missing:
        findings.append(uncalibrated_finding(table.family, ", ".join(missing)))
    if not table.logic_error_enabled:
        findings.append(
            uncalibrated_finding(
                table.family, "a validated error (maximum above 10 %)"
            )
        )
        return Estimate(logic, blocks, findings, missing)
    issue = logic_finding(
        round(logic), capacity, board, table.error.get("max_pct")
    )
    if issue and not (missing and issue.severity == "W"):
        findings.append(issue)
    return Estimate(logic, blocks, findings, missing)
