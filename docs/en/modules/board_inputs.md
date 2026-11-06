# `board_inputs`

Reads the `platform.yaml`, `board.yaml`, `pins.yaml`, family and chips a generator consumes.

## 1. Purpose

Gathers the data files of a platform on a board into one object (`BoardInputs`). It reads only the fields the generators use and refuses what is missing with a message that names the file. The full type validation belongs to the schema module, which replaces this reader without changing its callers.

## 2. Files read

| File | Where it is looked up |
| :--- | :--- |
| `platform.yaml` | Given path |
| `board.yaml` and `pins.yaml` | `<boards>/<board>/` |
| Family | `<boards>/families/<family>.yaml` |
| Chip | `<chips>/<chip>.yaml`, with the `extends` chain deeply merged and a cycle refused |

## 3. Choosing the board

The board comes from the command line, the `board` field of the platform or the single entry of `boards`. With several entries and `board: auto`, the request fails asking for `--board`. The `board_idcode` function returns the IDCODE of the `fpga: true` entry of the JTAG chain, which `program --board` uses to pick the cable.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_inputs.py` | Loading of the six boards, chip inheritance, cycle, board choice, V1 and IDCODE |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
