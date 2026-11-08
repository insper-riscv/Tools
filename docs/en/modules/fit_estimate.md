# `fit_estimate`

Estimates whether a profile fits a board and judges the result. The estimate adds the cost of each block of the profile with the calibration table of the family (a data file, replaceable); the same policy judges the estimate and the fit report of the Quartus.

## 1. Policy

The constants belong to the Tools and there is no option to force the result.

| Utilization $u$ of a resource | Result |
| :--- | :--- |
| $u \le 0.85$ | passes |
| $0.85 < u \le 1.00$ | warning (the estimate is off by a few percentage points; only the fit decides) |
| $u > 1.00$ | error |

The estimated logic only fails when the family is validated, that is, the maximum validation error of the table is up to 10 %. Before that the result is the V18 warning and the fit decides.

## 2. Messages

| Rule | Origin | Severity |
| :--- | :--- | :--- |
| V11 | RAM blocks of the emulated memory and of the caches above the budget | error; warning between 85 % and 100 % |
| V12 | estimated logic above the capacity | error |
| V13 | estimated logic between 85 % and 100 % | warning |
| V14 | fit report exceeds resources; all are listed at once (logic, RAM bits and blocks, multipliers, PLLs, pins) | error; warning in the 85 % to 100 % band |
| V18 | family without calibration, or coefficient without measurement | warning |

## 3. Calibration table

`boards/calibration/<family>.yaml` holds the unit (`alm` or `le`), the coefficients, the error (`rms_pct`, `max_pct`, validation profiles and `map_to_fit_ratio`) and the Fmax by grade. A `null` coefficient is a measurement not yet made and makes the estimator emit V18. The keys of extensions, extras, peripherals and controllers come from the vocabulary of the catalogs, and a key outside it is refused.

The estimated logic cost is

$$ \hat{L} = r \left( L_{core} + \sum_e L_e + L_{hpm}(n, w) + \sum_c L_c(s_c) + \sum_p L_p + \sum_b L_b \right) $$

with $L_{hpm} = a_0 + a_1 n + a_2 n w$, $L_c = c_0 + c_1 s_c$ and $r$ the ratio between the fit and the synthesis (`map_to_fit_ratio`, 1 when not measured). The RAM blocks are

$$ N_{blocks} = \sum_m \left\lceil \frac{8 s_m}{b_{block}} \right\rceil + N_{caches} + N_{regs} $$

The implications of the ISA hold in the `terms` function: Zicntr and Zihpm imply Zicsr, M implies Zmmul, and Sscofpmf needs Zihpm and interrupts. The calibration uses the same function to fit, so the fit and the estimate do not diverge.

## 4. Functions

| Function | Does |
| :--- | :--- |
| `estimate(spec, table, capacity, board)` | blocks, logic and the V11, V12, V13 and V18 messages |
| `terms(spec, bits_per_block)` | value of each term of the model for a profile |
| `estimate_logic(spec, table, bits_per_block)` | sum of the terms with a coefficient and the list of those without |
| `blocks_needed(spec, bits_per_block)` | RAM blocks of the profile |
| `report_findings(usage, capacity)` | V14 from the fit report |
| `classify(used, total)` | applies the policy |
| `capacity_from_resources(map)`, `load_capacity(file)` | capacities from the `resources` of a `board.yaml` |
| `load_table(file, vocabulary)`, `table_from_mapping`, `empty_table` | calibration table |

## 5. Command

```bash
riscv-tools --root . check-fit --reports <folder with *.fit.summary> --board boards/<board>/board.yaml
```

Lists every resource over the capacity and exits with status 1 when there is an error.

## 6. Tests

`tests/test_fit_estimate.py` covers the thresholds, the absence of a force option, the ISA implications, the sum over made-up tables, each V11 to V14 and V18 message, the empty table, the vocabulary validation and the `check-fit` command.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
