# `top_generator`

Generates the thin board top, which only wires the PLL, the SoC, one backend per region and the pin ring.

## 1. Purpose

The generated top has no logic besides the reset. It wires, in this order, the board ports, the PLL (a Verilog module, instantiated by component), the `soc` entity instance, the boot memory, the I/O roles, the console and one backend per external region, with the tri-state pin ring.

## 2. Content

| Part | Origin |
| :--- | :--- |
| Generics `HPM_COUNTERS` and `HPM_WIDTH` | Present when the profile has Zihpm, passed to the SoC |
| Reset | User reset normalized to active `'1'`, SoC reset released two `core` cycles after the PLL locks |
| SoC generics | Constants of the map package (`generate.vhdl.package`); without a PLIC in the platform, the PLIC and CLINT generics take the SoC defaults, so the top never reads constants the package lacks |
| Polarity | The SoC generics `switches_active_low`, `keys_active_low` and `display_active_low`; switches and keys are `inout` ports wired straight to the GPIO pins |
| `emulado` FLASH backend | `flash_chip` (latencies from `memory.rom.latency`), the dual-port `flash`, `flash_loader` and `flash_jtag_shell`; the loader holds the SoC in reset while it writes |
| `emulado` RAM backend | `onchip_ram_port` over the `ram` block, with the requested latency |
| `dispositivo/sdram` backend | Two bridges (data and instruction), `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` and one `tristate_buffer_1bit` per data bit in a `generate` |

## 3. What the top does not wire

A backend without an entity (`nor`, `sram`, an SDRAM whose width is not 16 bits) generates no instance: the top warns and leaves the region idle. The SoC does not export the LED role, and the LED pins stay at the off level. The text of each backend lives in `templates/`, with the real names and ports of the Memory entities.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | DE0-CV top content, latencies, pin ring, polarity and syntax accepted by GHDL |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
