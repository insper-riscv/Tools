# `top_generator`

Generates the thin board top, which only wires the PLL, the SoC, one backend per region and the pin ring.

## 1. Purpose

The generated top has no logic besides the reset. It wires, in this order, the board ports, the PLL (a Verilog module, instantiated by component), the `soc` entity instance, the boot memory, the I/O roles, the console and one backend per external region, with the tri-state pin ring.

## 2. Content

| Part | Origin |
| :--- | :--- |
| Generics `HPM_COUNTERS` and `HPM_WIDTH` | Present when the profile has Zihpm, passed to the SoC |
| Reset | User reset normalized to active `'1'`, SoC reset released two `core` cycles after the PLL locks |
| SoC generics | Constants of the map package (`generate.vhdl.package`); without a PLIC in the platform, the PLIC and CLINT generics take the SoC defaults, so the top never reads constants the package lacks; ISA extension generics are not passed, the SoC reads them from the platform `config_pkg` |
| Polarity | The SoC generics `switches_active_low`, `keys_active_low` and `display_active_low`; switches and keys are `inout` ports wired straight to the GPIO pins |
| `emulado` FLASH backend | `flash_chip` (latencies from `memory.rom.latency`), the dual-port `flash`, `flash_loader` and `flash_jtag_shell`; the loader holds the SoC in reset while it writes |
| Program update | With the `FLASH_CTRL` peripheral the SoC carries the controller (`has_flash_ctrl`) and the FLASH backend adds the `flash_cmd_port` on port B of the storage, which the loader takes while the core is stopped, and returns the rewritten region to the SoC so it drops the cache lines |
| Critical path cuts | The top turns on `registered_irqs`, `fast_icache_select` (with the fetch clock defined) and the page at the top of the RAM outside the data cache (`RAM_LAST_PAGE`), the same cuts as the hand-written top |
| `emulado` RAM backend | `onchip_ram_port` over the `ram` block, with the requested latency |
| `dispositivo/sdram` backend | Two bridges (data and instruction), `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` and one `tristate_buffer_1bit` per data bit in a `generate`; the 16 or 32-bit width and the row, column and bank bits come from the chip and from `memories.sdram.chips` |
| `dispositivo/nor` backend | 8-bit `nor_flash_ctrl` with page read and the program update commands, and the FLASH pin ring |

## 3. What the top does not wire

A backend without an entity (`sram`, `flash-interna` and `serial`) generates no instance: the top warns and leaves the region idle. The SoC does not export the LED role: the LED pins stay at the off level, except the first one, which lights with the failure flag the host writes to the display (Virtual JTAG node of index 2). The text of each backend lives in `templates/`, with the real names and ports of the Memory entities.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | DE0-CV top content, latencies, pin ring, polarity and syntax accepted by GHDL |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
