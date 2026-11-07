# `pll_generator`

Computes the PLL counters and writes the family primitive (`altera_pll` on Cyclone V and `altpll` on the others).

## 1. Purpose

Replaces the regular-expression edit of the PLL file. Changing the core frequency means generating the PLL again with another `clocks.core.mhz`.

## 2. Computation

For the reference $f_{ref}$ and the requested clocks, `solve` searches for the lowest VCO $f_{vco} = f_{ref} M / N$ inside the family `vco_mhz` range such that

$$ \frac{f_{vco}}{f_i} \in \{1, \dots, 511\} \quad \text{and} \quad \phi_i \in \mathbb{Z} \cdot \frac{1}{8 f_{vco}} $$

for each output $i$. The second condition says the phase is a multiple of one eighth of the VCO period, and for the DE0-CV it picks the 1000 MHz VCO (125 ps step), the same as the hand-written PLL. With no solution, or with more outputs than `outputs_max`, the error names the requests (V7 and V15).

## 3. Primitive per family

| Family IP | Writer |
| :--- | :--- |
| `altera_pll` (Cyclone V, which includes the DE10-Nano) | Per-output parameters and the compensation, reset and bandwidth instance assignments |
| `altpll` (Cyclone IV E, MAX 10, Cyclone 10 LP) | Multiplier/divider ratio and phase per output, family in `intended_device_family`, inner instance `altpll_component` |

The choice follows the per-family synthesis measurement: `altera_pll` only synthesizes on Cyclone V (error 12024 on the others), and `altpll` synthesizes on all four. Both writers share the VCO, divider and phase computation (`solve`) and register in `RENDERERS`. Another primitive enters through `register_renderer(ip, function)`, with a function `(module, solution, family) -> RenderedPll`; an IP without a writer fails with `PllIpPendingError`.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_pll_generator.py` | DE0-CV 1000 MHz VCO, text equal to the hand-written PLL, phase off the step, missing divider, V15 and the `altpll` extension point |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
