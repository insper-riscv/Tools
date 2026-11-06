# `pll_generator`

Computes the PLL counters and writes the family primitive (`altera_pll` ready, `altpll` as an extension point).

## 1. Purpose

Replaces the regular-expression edit of the PLL file. Changing the core frequency means generating the PLL again with another `clocks.core.mhz`.

## 2. Computation

For the reference $f_{ref}$ and the requested clocks, `solve` searches for the lowest VCO $f_{vco} = f_{ref} M / N$ inside the family `vco_mhz` range such that

$$ \frac{f_{vco}}{f_i} \in \{1, \dots, 511\} \quad \text{and} \quad \phi_i \in \mathbb{Z} \cdot \frac{1}{8 f_{vco}} $$

for each output $i$. The second condition says the phase is a multiple of one eighth of the VCO period, and for the DE0-CV it picks the 1000 MHz VCO (125 ps step), the same as the hand-written PLL. With no solution, or with more outputs than `outputs_max`, the error names the requests (V7 and V15).

## 3. Primitive per family

| Family IP | Writer |
| :--- | :--- |
| `altera_pll` (Cyclone V, Cyclone V SoC) | Ready, with the compensation, reset and bandwidth instance assignments |
| `altpll` (Cyclone IV E, MAX 10, Cyclone 10 LP) | Extension point: without a writer, `PllIpPendingError` points at the missing measurement |

Whoever writes `altpll` calls `register_renderer("altpll", function)`, with a function `(module, solution) -> RenderedPll`. The rest of the flow does not change.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_pll_generator.py` | DE0-CV 1000 MHz VCO, text equal to the hand-written PLL, phase off the step, missing divider, V15 and the `altpll` extension point |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
