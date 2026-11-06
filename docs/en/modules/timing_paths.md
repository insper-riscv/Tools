# `timing_paths`

Lists the worst setup paths of an already compiled Quartus project, by register. The Timing Analyzer reports the paths one bit at a time (`r_alu_out[13]`); the module asks for the worst ones of each clock domain, folds the bits of a register into one row and shows the critical path as "from this register to that one", so the stage that dominates shows up at once.

## Functions

| Function | Does |
| :--- | :--- |
| `run_timing_paths(project_dir, project_name, npaths, model)` | runs `quartus_sta` on the compiled project and returns the paths of every domain |
| `parse_paths(output)` | reads the marked lines of the output of the Tcl script; a malformed line is an error |
| `register_of(node)` | register name of a node, without the bit index, with the pipeline barrier registers written as `IF/ID`, `ID/EX`, `EX/MEM` and `MEM/WB` |
| `group_paths(paths)` | folds the bits of each pair of registers into one group, worst first |
| `format_table(groups)` | table with one row per group |

## Command

```bash
riscv-tools --config <config.yaml> timing-paths [--npaths N] [--model slow|fast] [--out FILE]
```

The project is the one of `quartus.project_dir` and `quartus.project_name` in the configuration. `--npaths` (30 by default) is the number of paths asked for in each domain, `--model` picks the slow model (1100 mV and 85 C, the default) or the fast one, and `--out` also writes the table to a file.

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_sta`) and the database of a full compilation of the project, for example the one from `de0-cv_synth.tcl`.

## Tests

`tests/test_timing_paths.py` covers the reading of the marked lines, the error of a malformed line, the register names, the folding of the bits and the table.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
