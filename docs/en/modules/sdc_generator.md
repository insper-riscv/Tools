# `sdc_generator`

Generates the `.sdc` with clocks, chip I/O delays, read paths and domain crossings.

## 1. Purpose

Writes the timing constraints of a platform on a board from the clock plan, the ports, the chip delays and the family clock node pattern.

## 2. File order

| # | Block |
| ---: | :--- |
| 1 | `create_clock` of the reference input, `derive_pll_clocks` and `derive_clock_uncertainty` |
| 2 | Generated clock of the SDRAM pin and the chip I/O delays |
| 3 | Memory read path (multicycle 2 and 1) |
| 4 | Crossings between the `mem`, `core` and `fetch` domains, and between them and the JTAG clock |
| 5 | RGMII Ethernet clocks: the 125 MHz `RXC` as an input clock, `GTX_CLK` as a generated clock of the PLL node, a group asynchronous to the SoC and false paths of MDC, MDIO, INT_N and RESET_N |
| 6 | The 10 MHz `ADC_CLK_10` clock of the MAX 10 ADC, with the group asynchronous to the SoC |
| 7 | The `CLK` clock of the MIPI camera as a 200 MHz input clock (a ceiling of 400 Mbit/s per lane), with the group asynchronous to the SoC |
| 8 | False paths of the pins of the Wi-Fi module, which are slow and asynchronous to the core |
| 9 | False paths of the pairs and the `hpd` of the direct TMDS HDMI output, which leave from the DDR register of the serial clock and have no timing requirement |
| 10 | False paths of the reset, switches, keys, LEDs, displays and the pins of the NOR FLASH and the SRAM |

## 3. Crossing bound

Each crossing is bounded by a delay shorter than the latency of the two-flip-flop synchronizer, with no hold check. The bound is the smallest period among the SoC clocks,

$$ b = \min_{r} T_r $$

which gives 10 ns for the DE0-CV at 50 MHz core and 100 MHz controller, and follows the core period when it changes.

## 4. Pixel clock

With the `pixel` output in the plan, the `.sdc` declares the pixel clock node and bounds the two crossings with the core domain by the smaller of the pixel period and the bound of section 3. `pixel_x5` is one more node, from the same PLL, and joins the pixel in the `video_clocks` set, so the two crossings with the core hold for both clocks.

## 5. PLL clock nodes

The node name comes from the family field `pll.clock_node_pattern`, with `<instance>` and `[N]`, replaced by the PLL instance name and the output index. A family without the pattern (`altpll` still unmeasured) fails with `SdcError`.

## 6. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_video_clocks.py` | The pixel clock domain, the crossings |
| `tests/test_board_equivalence.py` | The generated DE0-CV `.sdc` has the constraints of the hand-written `de0-cv.sdc` |
| `tests/test_board_generate.py` | `.sdc` of the boards with a test PLL |
| `tests/test_eth_rgmii.py` | The RGMII Ethernet block and the crossing bound without its clocks |
| `tests/test_external_top.py` | The MIPI camera clock and its asynchronous group, and the false paths of the Wi-Fi module and the TMDS output |
| `tests/test_vendor_ip.py` | The ADC clock, the IP and the script in the project, the USB `dreq` and `dack`, and rule V25 |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
