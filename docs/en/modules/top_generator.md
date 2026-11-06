# `top_generator`

Generates the thin board top, which only wires the PLL, the SoC, one backend per region and the pin ring.

## 1. Purpose

The generated top has no logic besides the reset. It wires, in this order, the board ports, the PLL, the polarity normalization of the I/O roles (K8), the SoC instance, one backend instance per external region and the tri-state pin ring.

## 2. Content

| Part | Origin |
| :--- | :--- |
| Generics `HPM_COUNTERS` and `HPM_WIDTH` | Present when the profile has Zihpm, passed to the SoC |
| Reset | User reset normalized to active `'1'`, SoC reset released two `core` cycles after the PLL locks |
| Polarity | `not` on switches, keys, LEDs and displays with `active: low` |
| `emulado` backend | Region size, `latency.first` and `latency.next`, `sector_bytes` |
| `dispositivo/sdram` backend | `DQ_WIDTH` from the ports, and one `tristate_buffer_1bit` per data bit in a `generate` |
| `sram` and `nor` backends | One connection per board port |

## 3. Contract with the SoC and the backends

The names of the SoC entity (`soc`), of the backends and of their ports are all constants of the module, so adjusting them to the entities published by Core and Memory is a change in one file.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | DE0-CV top content, latencies, pin ring, polarity and syntax accepted by GHDL |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
