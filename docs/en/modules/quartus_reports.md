# `quartus_reports`

Reads the resource summaries that the Quartus writes at the end of the synthesis and of the fit. The module only reads: the capacities of the board, the limits and the fit policy live in `fit_estimate`.

## 1. Files read

| File | Contents |
| :--- | :--- |
| `<revision>.map.summary` | Synthesis summary, `Name : value` lines; the logic line of the ALM families holds `N/A` |
| `<revision>.map.rpt` | The "Analysis & Synthesis Resource Usage Summary" table (estimate of ALMs or logic elements) and the hierarchy by entity |
| `<revision>.fit.summary` | Fit summary, with each resource and its capacity (`8,058 / 18,480 ( 44 % )`) |
| `<revision>.fit.rpt` | The "Fitter Resource Usage Summary" table, used when there is no `fit.summary` |

## 2. Units by family

| Family | Logic | Multipliers | Internal RAM |
| :--- | :--- | :--- | :--- |
| Cyclone V | ALMs | `Total DSP Blocks` (DSP blocks; the 5CEBA4 has 66) | `Total block memory bits` and `Total RAM Blocks` |
| Cyclone IV E, MAX 10, Cyclone 10 LP | `Total logic elements` | `Embedded Multiplier 9-bit elements` | `Total memory bits` |

## 3. Functions

| Function | Does |
| :--- | :--- |
| `parse_summary(text)` | reads a `*.map.summary` or `*.fit.summary`; a text with no resource line is an error |
| `parse_map_report(report, summary)` | reads the logic estimate of the synthesis, the pins and PLLs of the summary and the hierarchy down to a depth |
| `parse_fit_report(report, summary)` | reads the fit, each resource with its capacity |
| `parse_entities(report, depth)` | rows of the table of use by entity (ALUTs, registers and memory bits, with the ones of the children) |
| `parse_quantity(text)` | reads `8,058 / 18,480 ( 44 % )` or `4638`; `N/A` gives `None` |
| `succeeded(usage)` | true when the status of the step starts with `Successful` |

## 4. Tests

`tests/test_quartus_reports.py` reads the real files of a synthesis and of a fit of the Cyclone V (`tests/fixtures/quartus_reports/cyclone-v`) and a summary of a logic element family, and checks the error of a file with no resources.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
