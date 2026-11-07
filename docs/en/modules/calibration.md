# `calibration`

Measures the area of the profiles of a family with the compile command of the project and fits the coefficients of the `fit_estimate` estimator. The module does not synthesize by itself. With a hand-written project it runs the script the project already has (`de0-cv_synth.tcl map`); with a board project (`project.board` in the profile list) it writes the project with `board generate` and runs the single `compile.tcl` of `program`, only up to the synthesis (`quartus_map`) or, with `--stop-after fit`, also up to the fitter.

## Measuring a profile

For each profile of the list the loop does, in this order:

1. copies the project to a work folder (the original project never changes);
2. writes the profile into the `platform.yaml` of the copy (profile, `extras`, cache sizes) and regenerates the memory map package with `generate-memory-map`;
3. completes the package with the interrupt constants that the top still reads when the profile has no interrupts;
4. with `project.board`, writes the board project with `riscv-tools --board <board> board generate --target ...`, so the memory map package of the copy enters the `.qsf` as a source;
5. hashes the sources the Quartus reads (those of the `.qsf` and the `platform.yaml`);
6. takes the machine lock (`/tmp/quartus-<machine>.lock`, the same one the other tracks use) and runs `quartus_sh -t <script> <seed> <map|fit> [GENERIC=value ...]`, where the script is the project's or the `compile.tcl` of `program --stop-after`;
7. reads `*.map.rpt` and `*.map.summary` (and, with `fit`, `*.fit.rpt` and `*.fit.summary`) and writes a YAML record.

A profile whose record already holds the same hash, seed and generics is skipped, so an interrupted run resumes where it stopped.

## Raw record

One file per profile, in `boards/calibration/raw/<family>/<id>.yaml`.

| Field | Contents |
| :--- | :--- |
| `id`, `group`, `profile`, `extras`, `icache_kbit`, `dcache_kbit`, `generics`, `holdout` | the measured profile |
| `seed` | seed passed to the script |
| `tool` | Quartus version |
| `sources_hash` | SHA-256 of the paths and contents of the sources |
| `revisions` | commit of the project and of each submodule (the Core's identifies the calibrated core) |
| `added_constants` | constants completed in the package |
| `command` | compile command that ran |
| `result` | logic, registers, RAM bits, multipliers, PLLs and pins after the synthesis |
| `fit_result` | the same fields read from the fitter (only with `--stop-after fit`) |
| `entities` | hierarchy down to the first level |

## Fit

The model is linear in the coefficients, and the fit is a least squares over the profiles that are not validation ones. Columns that no combination of the earlier ones separates stay `null` (list `unseparated`). The terms that the fixed top of the board carries in every measurement go to `fixed` with value zero (the SDRAM, the FLASH, the display, the JTAG UART and the FLASH controller stay inside the core term), and the term of each cache is $c_0 = -s_{ref}\,c_1$, because the reference size is already in the core.

The recorded error holds the root mean square error over the fit profiles (`rms_pct`), the largest absolute error over the validation ones (`max_pct`) and the ratio between the fit and the synthesis estimate (`map_to_fit_ratio`). The ratio is the mean of `fit_result.logic` over `result.logic` of the records that carry `fit_result` (`fit_ratio_check`); with none, the known range of the full profile applies (`known_fit` of the profile list, used on the Cyclone V).

## Functions

| Function | Does |
| :--- | :--- |
| `load_profile_list(file)` | reads the profile list of a family |
| `run_all(plan, settings, ids)` | measures the profiles, one at a time |
| `measure(plan, profile, settings)` | measures one profile and writes the record |
| `machine_lock(file)` | exclusive lock of the machine (`flock`) |
| `load_records(folder)`, `fit_table(plan, records)`, `write_table(content, file)` | fits and writes the calibration table |
| `fit_ratio_check(plan, records)` | fit over synthesis ratio measured on the records with `fit_result` |

## Command

```bash
riscv-tools --root <Insper-RISC-V> calibrate run --profiles boards/calibration/profiles/cyclone-v.yaml --raw boards/calibration/raw/cyclone-v [--only id1,id2] [--stop-after map|fit] [--riscv-tools "<command>"] [--work-dir FOLDER] [--lock FILE] [--keep]
riscv-tools --root <Insper-RISC-V> calibrate fit --profiles boards/calibration/profiles/cyclone-v.yaml --raw boards/calibration/raw/cyclone-v --table boards/calibration/cyclone-v.yaml
```

## Tests

`tests/test_calibration.py` uses a fake `riscv-tools` and a fake `quartus_sh` and covers the profile names, writing the profile into the `platform.yaml`, completing the package, the sources hash, the record, resuming, the synthesis error, the lock and the fit that recovers known coefficients.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
