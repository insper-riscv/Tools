# `board_inputs`

Reads the `platform.yaml`, `board.yaml`, `pins.yaml`, family and chips a generator consumes.

## 1. Purpose

Gathers the data files of a platform on a board into one object (`BoardInputs`). Reading and validating `board.yaml`, `pins.yaml`, family and chip is done by `board_schema` (`Catalog`); this module picks the board, loads what the platform uses and hands the typed records over as maps (`board_view`, `family_view`, `chip_view`) that the generators consume. A catalog error becomes `InputError`.

## 2. Files read

| File | Where it is looked up |
| :--- | :--- |
| `platform.yaml` | Given path |
| `board.yaml` and `pins.yaml` | `<boards>/<board>/` |
| Family | `<boards>/families/<family>.yaml` |
| Chip | `<chips>/<chip>.yaml`, only the timing chips (`sdram`, `sram`, `nor`), with `extends` resolved by the catalog |

## 3. Choosing the board

The board comes from the command line, the `board` field of the platform or the single entry of `boards`. With several entries and `board: auto`, the request fails asking for `--board`.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_inputs.py` | Loading of the six boards, chip inheritance, timing chips, board choice and V1 |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
