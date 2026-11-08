# `board_clocks`

Decides the clocks by role (`mem`, `mem_pin`, `fetch`, `core`) with frequency and phase.

## 1. Purpose

The PLL, the `.sdc` and the top read the same plan, so every clock is decided once.

## 2. Origin of each value

| Role | Frequency | Phase |
| :--- | :--- | :--- |
| `core` | `clocks.core.mhz` of the platform | `clocks.core.phase_ps` |
| `fetch` | `clocks.fetch.mhz`; without the field the role uses the `core` clock | `clocks.fetch.phase_ps` |
| `mem` | The lower of `clocks.mem.mhz` and the `max_mhz` of the chips in use; above the cap is error V7 | 0 |
| `mem_pin` | That of `mem` | `memories.sdram.clk_phase_ps` of the board; `null` becomes 0 with a warning |

`mem` and `mem_pin` exist only with a `dispositivo` backend (`mem_pin` only with SDRAM). The PLL outputs are ordered `mem`, `mem_pin`, `fetch`, `core`, and the PLL instance name is `pll_inst` in every top, so the `.sdc` does not vary with it.

## 3. Minimum period

`min_period_ns` is the smallest period among the SoC clocks and bounds the domain crossings of the `.sdc`.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_ports.py` | DE0-CV clock plan, chip cap (V7) and unmeasured phase |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
