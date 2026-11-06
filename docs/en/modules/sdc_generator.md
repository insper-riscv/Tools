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
| 5 | False paths of the reset, switches, keys, LEDs and displays |

## 3. Crossing bound

Each crossing is bounded by a delay shorter than the latency of the two-flip-flop synchronizer, with no hold check. The bound is the smallest period among the SoC clocks,

$$ b = \min_{r} T_r $$

which gives 10 ns for the DE0-CV at 50 MHz core and 100 MHz controller, and follows the core period when it changes.

## 4. PLL clock nodes

The node name comes from the family field `pll.clock_node_pattern`, with `{instance}` and `{index}`. A family without the pattern (`altpll` still unmeasured) fails with `SdcError`.

## 5. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_equivalence.py` | The generated DE0-CV `.sdc` has the constraints of the hand-written `de0-cv.sdc` |
| `tests/test_board_generate.py` | `.sdc` of the boards with a test PLL |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
