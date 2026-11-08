# `board_schema`

Reads and checks the files of the board catalog: the `board.yaml` and the `pins.yaml` of each board, the device family and the memory chip. The new fields of the `platform.yaml` (the board, the backend of the external memories, the clocks, the console and the roles of inputs and outputs) go through the same reader. Each piece of data lives in one file, and this module is the only one that knows the schema of each.

## 1. Where the files are

The catalog is found from the project root.

| File | Path | Schema |
| :--- | :--- | :--- |
| Board | `boards/<board>/board.yaml` | Device, JTAG chain, capacities, clocks, I/O roles, memories and console |
| Pins | `boards/<board>/pins.yaml` | Pin, I/O standard, direction and certainty seal of each signal |
| Family | `boards/families/<family>.yaml` | Logic unit, PLL, RAM block, measured Fmax by grade and calibration |
| Chip | `Memory/chips/<chip>.yaml`, or `chips/<chip>.yaml` when the root is Memory itself | Organization, timings and clock ceiling |

The name inside a file is the name of the file (or of the folder, for a board), and a file that says another name is refused.

## 2. Reading and types

Each field is read with its expected type (string, integer, number, boolean, mapping or list), and every key the schema does not define is an error, so a misspelled field does not pass silently. The reader gathers all the problems of a file before it fails, each with the dotted path of the field (`board de0-cv.jtag.chain[0].idcode must be 8 hexadecimal digits`).

The catalog reuses the `extends` mechanism of the config files. A chip says `extends: <chip>` and inherits the named chip, which the reader looks up in the same folder; the fields of the extending chip win over the inherited ones, with the same recursive merge the `config.yaml` files use. A cycle of `extends` is refused. The platform also reads its `extends` through the same config reader.

## 3. Fields the board accepts

Besides the fields of the schema in the architecture document, the `board.yaml` accepts the fields the boards package uses.

| Field | Meaning |
| :--- | :--- |
| `target_level` | Target support level, from `N0` to `N4` |
| `console.default` | Default console, `jtag` |
| `jtag.cable_name` | Name `jtagconfig` gives the cable |
| `jtag.usb[]` | USB IDs `vid:pid` of the cable, with `state` and the `confirmed` seal |
| `jtag.samd21`, `jtag.external_pads` | Free descriptions of the emulated cable and of the external pads |
| `jtag.chain[].hps` | Chain device that is the HPS; exactly one chain item is the FPGA |
| `jtag.chain[].confirmed` | `manual`, `repo`, `inferred` or `measured` |
| `memories.<kind>.signals` | Prefix of the signals in the `pins.yaml`, or a list of prefixes |

The signals of `io.<role>` follow the grammar of the `pins.yaml`: `LEDR[9:0]` are bits 0 to 9, and `HEX[5:0][6:0]` are digits 0 to 5 (first range, the index in the name) with segments 0 to 6 (second range).

## 4. New fields of the `platform.yaml`

| Field | Rule |
| :--- | :--- |
| `board`, `boards` | `auto` or a board name, and the list of boards the platform is built on |
| `memory.<rom or ram>.backend` | `emulado` or `dispositivo`, required with `external: true` |
| `memory.<rom or ram>.device` | Only with `dispositivo`, and of the kind of the region (`nor`, `flash-interna`, `serial` for the ROM; `sdram`, `sram` for the RAM) |
| `memory.<rom or ram>.latency` | `{first, next}`, only with `emulado` |
| `memory.rom.sector_bytes` | Power of 2, only in an `emulado` FLASH |
| `clocks.core`, `clocks.fetch`, `clocks.mem` | `{mhz, phase_ps}`; `core` is required and `mem` is required with a `dispositivo` backend |
| `console` | `jtag` (default) or `pinos` |
| `io.<role>` | `{count, need}` with `need` equal to `required` or `optional` |
| `top` | Component, or list of components, whose `requires` closure gathers the `needs` for the validator |

The fields of the map (regions, peripherals, profile) are still read and checked by the `memory_map` module.

## 5. Checking the catalog

The `check-boards` command reads the whole catalog and checks each file against its schema and against the others. A board names a family and chips that exist, and every signal it cites (clock, reset, I/O groups, UART and the memory prefixes) exists in the `pins.yaml`. A pin used by two signals must be in `conflicts`.

## 6. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_schema.py::test_a_chip_extends_another_by_name` | The extending chip keeps what it does not say and overrides the rest |
| `tests/test_board_schema.py::test_a_chip_extends_loop_is_refused` | A cycle of `extends` fails |
| `tests/test_board_schema.py::test_a_chip_file_must_carry_its_own_name` | The file name and the chip name match |
| `tests/test_board_schema.py::test_unknown_names_list_what_exists` | A missing board, family or chip says what exists |
| `tests/test_board_schema.py::test_the_catalog_reads_a_board_with_its_pins` | Board, family and pins load together |
| `tests/test_board_schema.py::test_chip_problems_are_all_reported` | Every wrong field of the chip shows at once |
| `tests/test_board_schema.py::test_an_sdram_chip_needs_its_organization` | Banks and address bits are required for an SDRAM |
| `tests/test_board_schema.py::test_family_types_are_checked` | A wrong type and a reversed VCO range are refused |
| `tests/test_board_schema.py::test_a_board_must_name_exactly_one_fpga` | The chain has exactly one FPGA |
| `tests/test_board_schema.py::test_a_board_accepts_the_fields_of_the_boards_package` | The fields of the boards package are accepted |
| `tests/test_board_schema.py::test_a_board_rejects_a_wrong_idcode_and_unknown_key` | Malformed IDCODE and unknown key |
| `tests/test_board_schema.py::test_pins_signals_and_conflicts` | The certainty seal of a pin is checked and `conflicts` is accepted |
| `tests/test_board_schema.py::test_signal_groups_expand_as_the_format_says` | Expansion of buses and buses of buses |
| `tests/test_board_schema.py::test_platform_fields_are_read_and_typed` | The new platform fields load |
| `tests/test_board_schema.py::test_platform_field_problems` | Each invalid use of the new fields is a typed problem |
| `tests/test_board_schema.py::test_platform_extends_is_resolved_by_the_config_reader` | A platform variant says only what changes |

## 7. Usage

```bash
uv run riscv-tools --root <Insper-RISC-V> check-boards
```

It needs no `--config`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
