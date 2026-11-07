# `board_generate`

Composes the generators into the Quartus project of a platform on a board (`riscv-tools board generate`).

## 1. Purpose

Calls each generator and joins the text, writing no content of its own. The output folder is a build folder and is not versioned.

## 2. Generated files

| File | Generator |
| :--- | :--- |
| `<platform>_<board>_top.vhd` | `top_generator` |
| `<platform>_<board>_pll.v` | `pll_generator` |
| `<platform>_<board>.sdc` | `sdc_generator` |
| `<platform>_<board>.qpf` and `.qsf` | `quartus_project`, with the pins of `pin_assignments` |
| `chip_<chip>_pkg.vhd` | `chip_package`, one per board chip |

The project lives in `<out>/<platform>-<board>/`. The compile command is `program` (see [quartus_program](quartus_program.md)).

## 3. Usage

```bash
uv run riscv-tools --root <workspace> board generate \
    --platform <platform>.yaml --board de0-cv --out build \
    --target de0_cv_map --target soc --target Memory/flash_chip
```

| Option | Effect |
| :--- | :--- |
| `--board` (global) | Board; without it the `board` field or the single `boards` entry applies |
| `--boards-dir`, `--chips-dir` | Defaults `<root>/boards` and `<root>/Memory/chips` |
| `--target` | Component whose source closure goes in the `.qsf`; repeatable |
| `--seed` | Seed of the `.qsf`, default 5 |
| `--accept-inferred-pins` | Accept building with an `inferred` pin |
| `--hand-qsf`, `--hand-sdc`, `--hand-pll`, `--ignore-source` | Print the [board_equivalence](board_equivalence.md) report against the hand-written files |

Warnings (unmeasured `DRAM_CLK` phase, missing optional role, backend without an entity) go to `stderr`. Exits with status 2 when an input is invalid, and with status 1 when the equivalence report finds a loss.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | Files of the six boards (the `altpll` ones with a test writer), `.qsf`, determinism and writing |
| `tests/test_board_generate_cli.py` | The command writes the folder, prints the report and exits with 2 on an invalid input |
| `tests/test_generator_uniqueness.py` | Each kind of generated text has a single writer module |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
