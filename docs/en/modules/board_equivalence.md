# `board_equivalence`

Compares the generated project with the hand-written files: pins, constraints, PLL, sources and assignments.

## 1. Purpose

Shows what generation loses, changes or adds against today's files, without replacing them. The comparison is normalized.

## 2. Sections

| Section | Comparison |
| :--- | :--- |
| `pins` | Set of (signal, pin, I/O standard) of the `.qsf` |
| `assignments` | Per-instance assignments that are not I/O standards, with optional text swaps (the PLL module name) |
| `project` | `FAMILY`, `DEVICE`, `VHDL_INPUT_VERSION`, `OPTIMIZATION_MODE` and `SEED` |
| `sources` | Source file names, minus those in `ignored_sources` |
| `constraints` | `.sdc` commands with `set` variables expanded and brace sets sorted |
| `pll` | Frequency, phase and ratio to the reference of each output |

Each section lists what exists only by hand, only in the generated output and what changed. The report is equivalent when nothing exists only by hand and nothing changed; what exists only in the generated output is an addition.

## 3. Result on the DE0-CV

Against today's `de0-cv.qsf`, `de0-cv.sdc` and `sdram_platform_pll.v`, `pins`, `assignments`, `project`, `constraints` and `pll` are equivalent. There are 107 assigned pins. The generated output adds two false paths (switches and keys, which today's top does not wire). `sources` differs only by the top, the PLL, the chip package and the sources of the `provides` closure.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_equivalence.py` | Generated DE0-CV against the real files (fixtures), pin count, additions and detection of a changed pin, phase and delay |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
