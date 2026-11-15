# `board_clocks`

Decides the clocks by role (`mem`, `mem_pin`, `fetch`, `core`, `eth_tx`, `eth_tx_dly`, `pixel`, `pixel_x5`) with frequency and phase.

## 1. Purpose

The PLL, the `.sdc` and the top read the same plan, so every clock is decided once.

## 2. Origin of each value

| Role | Frequency | Phase |
| :--- | :--- | :--- |
| `core` | `clocks.core.mhz` of the platform | `clocks.core.phase_ps` |
| `fetch` | `clocks.fetch.mhz`; without the field the role uses the `core` clock | `clocks.fetch.phase_ps` |
| `mem` | The lower of `clocks.mem.mhz` and the `max_mhz` of the chips in use; above the cap is error V7 | 0 |
| `mem_pin` | That of `mem` | `memories.sdram.clk_phase_ps` of the board; `null` becomes 0 with a warning |
| `eth_tx` | 125 MHz, the free transmit clock of the RGMII Ethernet | 0 |
| `eth_tx_dly` | 125 MHz, the clock that leaves by `GTX_CLK`, shifted by a quarter of a cycle | 2000 ps |
| `pixel` | The `pixel_clock_mhz` of the resolved mode of `io.video`, or the `pixel_clock_khz` written on the peripheral; the two must agree | 0 |
| `pixel_x5` | Five times `pixel`, only when a peripheral asks for the serial clock (TMDS) | 0 |

`mem` and `mem_pin` exist only with a `dispositivo` backend (`mem_pin` only with SDRAM). `eth_tx` exists when an `eth` entry has `mode: rgmii`, and `eth_tx_dly` only when one of them leaves `shifted_txc` true (the default); with `shifted_txc` false the PHY inserts the delay and `GTX_CLK` leaves from `eth_tx` itself. `pixel` and `pixel_x5` exist only when an external peripheral has the pixel clock port and one of the two sources gives the frequency; otherwise the PLL gets no such output. The PLL outputs are ordered `mem`, `mem_pin`, `fetch`, `core`, `eth_tx`, `eth_tx_dly`, `pixel`, `pixel_x5`, and the PLL instance name is `pll_inst` in every top, so the `.sdc` does not vary with it.

## 3. Minimum period

`min_period_ns` is the smallest period among the SoC clocks (not `mem_pin`, `eth_tx`, `eth_tx_dly`, `pixel` and `pixel_x5`) and bounds the domain crossings of the `.sdc`. The video clocks are left out of the minimum because they form a domain of their own (section 4 of [sdc_generator](sdc_generator.md)).

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_ports.py` | DE0-CV clock plan, chip cap (V7) and unmeasured phase |
| `tests/test_eth_rgmii.py` | The clock requests of the RGMII, with and without the shift of `GTX_CLK` |
| `tests/test_video_clocks.py` | `pixel` and `pixel_x5` PLL outputs, minimum period without the video clocks, source of the frequency and refusal of a mismatch |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
