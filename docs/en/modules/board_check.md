# `board_check`

Checks what a platform requires against what its boards offer. The platform declares what it needs (regions, backends, clocks, console, I/O roles) and the board declares what it has. The module derives both sides and compares them, and each difference is an error (`E`) or warning (`W`) message with a rule code. The files it reads are the ones of [board_schema](board_schema.md).

## 1. Where it runs

The check runs inside `check-memory-map`, next to the check of the map, and not in `platform sync`. A platform that writes neither `board` nor `boards` is not checked, so the platforms that predate the catalog keep passing. With `board: auto` and no `boards`, the board is only known at run time and nothing is checked here.

An error makes the command exit with status 1, and a warning is only printed. The `--accept-inferred-pins` option allows the use of a pin that the `pins.yaml` marks as `inferred`.

## 2. Where `requires` and `provides` come from

Both sides are computed and never written. `requires` gathers what the `platform.yaml` asks for and the union of the `needs` keys of the components in the closure of the top. `provides` comes from the `board.yaml`, from the chip of the catalog and from the `pins.yaml`.

The `needs` key sits beside `sources` and `requires` in the `paths.yaml` of the repository that owns the component, with the types `block_ram`, `sdram`, `sram`, `nor`, `onchip_flash`, `serial_flash` and `vjtag`. `sources` and this module walk the closure with the same code, so there is no second format and no second graph; the `top` field of the platform picks the starting point.

## 3. Rules

| Rule | Level | What it checks |
| :--- | :--- | :--- |
| V1 | E | The board, the family and the chips exist and the files follow the schema |
| V2 | E | Every `needs` type is on the board, and the sum of the regions of a device fits in it |
| V3 | E | The device of a `dispositivo` backend exists on the board |
| V4 | E | The `pinos` console requires `console.uart` |
| V5 | E | `required` role missing or with fewer units |
| V6 | W | `optional` role missing or with fewer units; the peripheral is omitted |
| V7 | E | Clock above the PLL range of the family or the ceiling of the chip |
| V8 | W | Core clock above the measured Fmax of the family and grade |
| V9 | E | FLASH bank off the sector multiple, counted from the start of the region |
| V10 | E | Region bigger than the capacity of the device |
| V15 | E | More PLL outputs (distinct clocks plus the SDRAM clock) than the board offers |
| V16 | E | `inferred` pin in use without `--accept-inferred-pins` |
| V17 | E | The JTAG chain read from the cable is not the board's |
| V18 | W | Family without a calibration file, or `null` capacity on the board |
| V19 | E | Bus width the backend cannot slice |

Rules V11 to V14 (fit) belong to the estimator.

### 3.1. Details

- In V9 the sector comes from the chip of a `dispositivo` NOR FLASH, or from the `sector_bytes` of an `emulado` FLASH.
- In V15 a PLL output is a pair of frequency and phase, and the number of PLLs needed is the ceiling of the division by the outputs of one PLL of the family.
- In V16 the pins in use are the one of the reference clock, the reset, the ones of the requested roles, the UART ones when the console is `pinos` and the ones that start with the prefixes of the memories in use.
- In V17 the check is the `check_chain` function, which receives the IDCODEs read from the cable; the command that identifies the board by the JTAG is the one that reads them.
- In V19 the accepted widths are 8 and 16 for the NOR, 16 and 32 for the SRAM and 16 and 32 for the SDRAM (the chip width times the number of chips).

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_check.py::test_the_base_platform_passes_without_a_message` | The base platform produces no message |
| `tests/test_board_check.py::test_a_platform_without_a_board_is_not_checked` | Without `board` nothing is checked |
| `tests/test_board_check.py::test_v1_unknown_board` | V1, unknown board |
| `tests/test_board_check.py::test_v1_unknown_family` | V1, unknown family |
| `tests/test_board_check.py::test_v1_unknown_chip` | V1, unknown chip |
| `tests/test_board_check.py::test_v1_a_malformed_board_is_reported` | V1, board outside the schema |
| `tests/test_board_check.py::test_v2_size_across_regions` | V2, sum of the regions above the device |
| `tests/test_board_check.py::test_v2_needs_of_the_closure` | V2, `needs` of the closure that the board does not offer |
| `tests/test_board_check.py::test_v2_top_that_cannot_be_resolved` | V2, top that no manifest declares |
| `tests/test_board_check.py::test_v3_device_the_board_lacks` | V3 |
| `tests/test_board_check.py::test_v4_console_on_pins_without_a_uart` | V4 |
| `tests/test_board_check.py::test_v5_required_role_missing_or_short` | V5 |
| `tests/test_board_check.py::test_v6_optional_role_missing_or_short` | V6 |
| `tests/test_board_check.py::test_v7_clock_over_the_chip_limit` | V7, chip ceiling |
| `tests/test_board_check.py::test_v7_clock_over_the_pll_range` | V7, PLL range |
| `tests/test_board_check.py::test_v8_core_above_the_measured_fmax` | V8 |
| `tests/test_board_check.py::test_v9_flash_bank_not_aligned_to_the_sector` | V9, NOR sector |
| `tests/test_board_check.py::test_v9_emulated_sector` | V9, emulated sector |
| `tests/test_board_check.py::test_v10_region_above_the_device` | V10 |
| `tests/test_board_check.py::test_v15_more_clocks_than_pll_outputs` | V15 |
| `tests/test_board_check.py::test_v16_inferred_pin_in_use` | V16, with and without the option |
| `tests/test_board_check.py::test_v17_chain_that_is_not_the_boards` | V17 |
| `tests/test_board_check.py::test_v18_family_without_calibration` | V18, family |
| `tests/test_board_check.py::test_v18_capacity_that_is_not_known` | V18, `null` capacity |
| `tests/test_board_check.py::test_v19_bus_width_the_backend_cannot_slice` | V19, three widths |
| `tests/test_board_check.py::test_the_catalog_check_finds_what_a_board_cites_wrongly` | Cited signal that does not exist and repeated pin |
| `tests/test_board_check.py::test_the_catalog_check_passes_a_consistent_catalog` | A consistent catalog passes |
| `tests/test_board_check.py::test_the_subcommands_exit_with_the_findings` | `check-memory-map` and `check-boards` exit with status 1 |
| `tests/test_manifest_needs.py::test_needs_of_the_closure_are_the_union` | Only the components of the closure contribute |
| `tests/test_manifest_needs.py::test_an_unknown_need_is_a_manifest_problem` | An unknown `needs` type is refused |

## 5. Usage

```bash
uv run riscv-tools --root <Insper-RISC-V> check-memory-map --platform src/cyclone-v/de0-cv/platform.yaml
uv run riscv-tools --root <Insper-RISC-V> check-memory-map --platform <platform> --accept-inferred-pins
```

It needs no `--config`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
