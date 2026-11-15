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
| Video modes | `boards/video-modes.yaml` | Timing and pixel clock of each mode, shared by every board |

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

The signals of `io.<role>` follow the grammar of the `pins.yaml`: `LEDR[9:0]` are bits 0 to 9, and `HEX[5:0][6:0]` are digits 0 to 5 (first range, the index in the name) with segments 0 to 6 (second range). A signal `NAME[i]` also finds the pin `NAMEi` of the file (`HSMC_CLKIN_N[1]` finds `HSMC_CLKIN_N1`).

| Role | Pins | Polarity |
| :--- | :--- | :--- |
| `leds`, `switches`, `keys`, `display`, `video` | The basic roles | `active` is required (except for `video`) |
| `leds_green` | Green LEDs (`LEDG[8:0]`) | `active` required |
| `gpio` | General-use headers (DE2-115: `GPIO[35:0]`; DE0-CV: `GPIO_0[35:0]` and `GPIO_1[35:0]`) | No polarity |
| `ex_io` | `EX_IO[6:0]` (DE2-115) | No polarity |
| `hsmc` | The 82 `HSMC_*` pins (DE2-115) | No polarity |
| `clock_extra` | `CLOCK2_50`, `CLOCK3_50`, `SMA_CLKIN` (input) and `SMA_CLKOUT` (output) | No polarity |

`signals` is one group or a list of groups, and the pins of the role are numbered in the order of the list (`GPIO_0` from 0 to 35, `GPIO_1` from 36 to 71). The optional field `bidirectional: true` (or `direction: inout`) asks the top generator for `inout` ports, and in the roles without polarity `active` may be absent (it is `high` and is not used). On the platform the roles `gpio`, `ex_io`, `hsmc`, `leds_green` and `clock_extra` accept only `need: optional`.


### 3.1. The `video` role and the catalog of modes

The `video` role is one of the I/O roles and the only one with no `active`.

| `io.video` field | Rule |
| :--- | :--- |
| `kind` | `vga` or `hdmi` |
| `channel_bits` | `4` or `8`, the bits of each color channel the board wires |
| `signals` | Prefix of the video signals in the `pins.yaml` (`VGA` cites every signal that starts with `VGA_`) |
| `default_mode` | Mode used when the platform asks for none; it must be in `modes` |
| `modes` | Modes the manual of the board specifies, written `<width>x<height>@<hertz>` |

The catalog `boards/video-modes.yaml` has the key `modes`, a map from the mode name to its timing. The name repeats the visible area, and the reader refuses a name that disagrees with it.

```yaml
modes:
  640x480:
    pixel_clock_mhz: 25
    source: VESA monitor timing   # optional
    horizontal: {visible: 640, front_porch: 16, sync: 96, back_porch: 48, total: 800, polarity: negative}
    vertical:   {visible: 480, front_porch: 10, sync: 2,  back_porch: 33, total: 525, polarity: negative}
```

On each axis, `visible + front_porch + sync + back_porch` must equal `total`, and `polarity` is `negative` or `positive`, the polarity of the synchronism pulse. How the mode of a platform is resolved is in [board_video](board_video.md).

### 3.2. The `buses` section

The `buses` section of `board.yaml` says, for each role of an external peripheral, which signal of `pins.yaml` wires each pin of the peripheral. The key is the role (the "Board role" column of section 9.6 of [memory_map](memory_map.md), except for `video`, which stays in `io.video`) and the value is a mapping, or a list of mappings when the board has more than one copy of the role (the two PS/2 channels of the DE0-CV).

```yaml
buses:
  ps2:
    - {clk: PS2_CLK, dat: PS2_DAT}
    - {clk: PS2_CLK2, dat: PS2_DAT2}
  sd: {clk: SD_CLK, cmd: SD_CMD, dat: "SD_DAT[3:0]"}
  adc:
    - {chip: ltc2308, convst: ADC_CONVST, sck: ADC_SCK, sdi: ADC_SDI, sdo: ADC_SDO}
```

A value is a signal (`SD_CLK`) or a bus (`SD_DAT[3:0]`) of `pins.yaml`. The order of the copies is the one of `instance` in `peripherals`. The table shows the pins of each role, with the direction seen from the top of the board; the suffix `?` marks an optional pin.

| Role | Pins (direction) |
| :--- | :--- |
| `ps2` | `clk` and `dat` (inout) |
| `sd` | `clk` (out), `cmd` and `dat` (inout) |
| `ir` | `rxd` (in) |
| `lcd` | `data` (inout), `rs`, `rw`, `en`, `power` and `blon?` (out) |
| `usb` | `addr`, `cs_n`, `rd_n`, `wr_n` and `rst_n` (out), `data` (inout), `int` (in) |
| `i2c` | `scl` and `sda` (inout) |
| `audio` | `xck`, `bclk`, `adclrck`, `daclrck` and `dacdat` (out), `adcdat` (in) |
| `eth` (MII) | `rx_clk`, `rxd`, `rx_dv`, `rx_er`, `tx_clk` and `int_n?` (in), `txd`, `tx_en`, `tx_er`, `mdc` and `rst_n` (out), `mdio` (inout) |
| `hdmi` | `d`, `clk`, `de`, `hs` and `vs` (out), `int` (in), `scl` and `sda` (inout) |
| `hdmi_audio` | `mclk`, `sclk`, `lrclk` and `i2s0` (out), the four I2S lines of the HDMI transmitter |
| `serial` | `rx` and `cts?` (in), `tx` and `rts?` (out) |
| `tv` | `data` and `clk27` (in), `reset_n` (out) |
| `adc` with `chip: adc128s022` | `cs_n`, `sclk` and `saddr` (out), `sdat` (in) |
| `adc` with `chip: ltc2308` | `convst`, `sck` and `sdi` (out), `sdo` (in) |
| `adc` with `chip: max10` | no pin, only the presence of the internal ADC |
| `spi` | `sclk`, `mosi` and `cs_n` (out), `miso` (in) |
| `adxl345` | `cs_n` and `sclk` (out), `mosi` (inout), `miso?` and `int1?` (in) |

An unknown role, a pin the role does not have, a missing required pin and a `chip` that is missing or outside the registry are problems of the file, and `check-boards` refuses every cited signal that `pins.yaml` lacks.

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
| `io.video` | Every field is optional. `width` and `height` (together), `aspect` (`4:3` or `16:9`, quoted or not), `refresh_hz`, `channel_bits` (`4` or `8`), `fb_width` and `fb_height` (together), `pixel_format` (`indexed`, the default, or `direct`), `scale` and `outside_manual`. Writing an empty `io.video`, or listing the `VIDEO` peripheral, asks for the default mode of the board |
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
| `tests/test_io_roles.py` | The roles of general use: several groups of signals, `bidirectional` and `direction: inout`, optional `active`, the count per role, `need: optional` on the platform, the flat pin name and the `inout` ports in list order. |
| `tests/test_board_schema.py::test_signal_groups_expand_as_the_format_says` | Expansion of buses and buses of buses |
| `tests/test_board_schema.py::test_platform_fields_are_read_and_typed` | The new platform fields load |
| `tests/test_board_schema.py::test_platform_field_problems` | Each invalid use of the new fields is a typed problem |
| `tests/test_board_schema.py::test_platform_extends_is_resolved_by_the_config_reader` | A platform variant says only what changes |
| `tests/test_board_video.py` | The `video` role, the catalog of modes and the video request of the platform |

## 7. Usage

```bash
uv run riscv-tools --root <Insper-RISC-V> check-boards
```

It needs no `--config`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
