# `quartus_project`

Generates the `.qpf` and the `.qsf` (without pins) with family, device and the source list.

## 1. Purpose

Writes the project revision, the device, the top, the `.sdc`, the optimization mode, the seed and the sources, each with the assignment type of its extension (`VHDL_FILE`, `VERILOG_FILE`, `SYSTEMVERILOG_FILE`, `QIP_FILE`).

## 2. Data origin

| Data | Origin |
| :--- | :--- |
| Family text | `quartus_family` of the family file |
| Device | `device` of `board.yaml` |
| Sources | The `sources` closure (`--target`), plus the generated files |
| Pins and PLL assignments | Appended at the end, written by the pin and PLL generators |

The module writes no per-pin assignments, and a source list only enters through the `provides` closure.

## 3. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | Family, device, top, `.sdc` and generated sources in the `.qsf` |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
