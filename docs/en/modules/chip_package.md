# `chip_package`

Generates the VHDL package with the timings of a catalog chip and hands the I/O delays to the `.sdc`.

## 1. Purpose

The timings of a chip exist only in its catalog file. This module writes them as the VHDL package `chip_<chip>_pkg` (one per chip the board uses), read by the controller and by the model, and as I/O delays for the `.sdc`.

## 2. Constants

Catalog keys `t<name>_<unit>` become `T_<NAME>_<UNIT>` (`trcd_ps` becomes `T_RCD_PS`), with the same names `sdram_pkg.vhd` has today. The other keys become the upper-case name.

| Source | Constants |
| :--- | :--- |
| `timing` | One per timing, rounded up |
| `organization` | `ROW_BITS`, `COL_BITS`, `DQ_WIDTH` |
| Chip root | `SECTOR_BYTES`, `BOOT_SECTOR_BYTES` when present |
| SDRAM | `CAS_LATENCY`, `BANK_BITS` and `MODE_REG` |

The mode register is $A_{2:0} = \log_2 B$ for burst $B$, $A_{3} = 0$ (sequential) and $A_{6:4} = CL$. The burst is $32 / (n_{chips} \cdot w)$, and for a 16-bit chip a burst of 2 reproduces `0000000110001`. An SDRAM missing any of the eleven required timings is refused.

## 3. I/O delays

`chip_io_delays` returns the four `.sdc` delays from `io_timing`.

| Delay | Source |
| :--- | :--- |
| Output max | `input_setup_ns` |
| Output min | $-$`input_hold_ns` |
| Input max | `access_ns` |
| Input min | `output_hold_ns` |

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_chip_package.py` | Names and values equal to those of `sdram_pkg.vhd`, mode register by burst, organization, NOR, missing timing and `.sdc` delays |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
