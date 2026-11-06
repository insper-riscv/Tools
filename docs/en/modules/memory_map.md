# `memory_map`

Checks that every hand-written copy of a platform's memory map agrees. The map (region bases and sizes, the words the boot memory reserves at the top of RAM, the boot entry points, the peripheral windows) is needed in many files: linker flags, boot memory, C runtime, VHDL, Quartus IPs, the project's `config.yaml`. Each copy is only noticed when it disagrees on the board. One YAML file, the platform, is the source of truth; this module reads each copy and reports every disagreement.

## Configuration

No `config.yaml` section: the platform file is self-describing and is passed with `--platform`.

```yaml
regions:                      # the map itself
  - {name: BOOT_MEMORY, base: 0x0,    size: 2K,   kind: rom, exec: true}
  - {name: FLASH,    base: 0x800,  size: 30K,  kind: rom, exec: true}
  - {name: RAM,      base: 0x8000, size: 160K, kind: ram}
reserved:                     # words at the top of RAM (inside a ram region)
  stdout:  {base: 0x2FBE0, size: 1K+8}
  tohost:  {base: 0x2FFF0, size: 16}
boot: {entry: 0x800, wait_restart: 0x100}
peripherals:                  # base = 0x80000000 | id << 28
  - {name: GPIO, base: 0xA0000000, id: 2}
checks:                       # where each copy lives
  - name: config ram base
    file: tools/riscv_build/config.yaml      # relative to --root
    yaml: memory.ram_base                     # dotted path, or:
    expect: RAM.base
  - name: specs ram size
    file: rv32im-fpga.specs
    pattern: '--defsym=__ram_size=(\S+)'      # one capture group
    expect: RAM.size - (RAM.end - stdout.base)
```

- **Symbols** in `expect`: `<REGION>.base|size|end|words`, `<reserved>.base|size|end`, `boot.entry|wait_restart`, `<PERIPHERAL>.base|id`.
- **Numbers** accept hexadecimal, decimal, VHDL-based (`16#800#`), suffixes (`30K`, `0x800u`) and `+ - * /` (exact division), plus `log2()` (exact) and `clog2()` (rounded up, for address widths).
- A check whose pattern matches nothing **fails** ("the copy moved"); `optional: true` skips a file that is absent. A pattern with several matches must agree at every match.
- Before the copies are read the map itself is validated: regions and reserved words do not overlap, reserved words sit inside a RAM region, `boot.entry` is in an executable region, `boot.wait_restart` is in the first region, each peripheral base matches its id, and every region ends at or below `0x80000000` (the lower 2 GiB belong to the BOOT_MEMORY, the ROM and the RAM, the upper 2 GiB to the peripherals).

## Generating the files of the map

The same YAML can say, in the `generate` section, which files come out of it, so no copy of the map has to be written by hand.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `specs` | GCC specs file | The linker flags: `__flash`, `__flash_size`, `__ram`, `__ram_size` and `rv32_wait_restart`. The RAM of the linker ends where the reserved word `ram_limit` begins |
| `boot_ld` | Boot memory linker script | The `boot_memory` memory in the first region and the `RESET_RESERVED` from `boot.wait_restart` |
| `runtime` | Runtime header (`.h`, also included by `.S`) | `RV32_RAM_END` (end of the `ram` region), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` and `RV32_STDOUT_BASE`, from the `reserved` ranges the map has, `RV32_BOOT_ENTRY` (where the boot memory jumps) and `RV32_<NAME>_BASE` for each peripheral; the runtime in C and assembly (`_exit.c`, `stdio.c`, `boot_memory.S`, `spike_exit.S`) uses these names instead of hand-written addresses |
| `vhdl` | VHDL package | The constants `BOOT_MEMORY_BITS`, `BOOT_MEMORY_SIZE_BYTES`, `ROM_BASE_KIB`, `ROM_END_KIB`, `ROM_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES`, `RAM_LAST_PAGE`, `EXT_BASE_KIB` and `PERIPH_BASE_KIB`, the `ROM_EXTERNAL` and `RAM_EXTERNAL` flags (from `generate.vhdl` or from the `memory` section), the cache constants of the `memory` section and, for each peripheral, `<NAME>_BASE` and `<NAME>_ID` |

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout}
  boot_ld: {path: runtime/boot_memory.ld}
  runtime: {path: runtime/memory_map.h, ram: RAM}
  vhdl:
    path: rtl/map_pkg.vhd
    package: map_pkg
    rom: FLASH
    ram: RAM
```

`ext_base` and `periph_base` are optional and default to `0x80000000`, the peripheral window. `ROM_STORAGE_BYTES` and `RAM_STORAGE_BYTES` are the smallest power of two that covers the end of the ROM and the size of the RAM, and `RAM_LAST_PAGE` is bits 31:12 of the last 4 KiB page of the RAM.

The limits of the VHDL package are the generics of the `core`, in KiB, so an address that is not a multiple of 1 KiB is an error. The map is validated before generating, and an inconsistent map generates nothing.

```bash
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml --check
```

With `--check` nothing is written, and the command exits with status 1 when a file is missing or differs from what the map would generate. It needs no `--config`.

## The FLASH banks

The `flash` section of the `platform.yaml` splits the FLASH into banks, each holding an image in the format of [`flash_image`](flash_image.md), for the program update in the field.

```yaml
flash:
  region: FLASH
  banks:
    - {name: A, base: 0x1000,  size: 124K}
    - {name: B, base: 0x20000, size: 128K}
generate:
  bank_specs:
    - {path: runtime/bank-b.specs, rom: BANK_B_PAYLOAD, ram: RAM, ram_limit: stdout}
  banks_h: {path: runtime/flash_banks.h}
```

Each bank starts with a 256-byte header page, so its program is linked from `base + 256`. For the bank `A` the map gains the symbols `BANK_A.base|size|end|words` and `BANK_A_PAYLOAD.base|size|end|words` (the part after the header), which serve as `expect` in the checks and as `rom` in the specs sections.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `bank_specs` | List of GCC specs files, one per entry | Like `specs`, with `__flash` and `__flash_size` of the region chosen in `rom`, usually `BANK_<name>_PAYLOAD` |
| `banks_h` | Header (`.h`, also included by `.S`) | `RV32_IMAGE_MAGIC`, `RV32_IMAGE_HEADER_SIZE` and, for each bank, `RV32_BANK_<NAME>_BASE`, `_SIZE` and `_ENTRY` (where the program starts) |

The map refuses banks that are not aligned to the 4 KiB sector, that leave no room for a program after the header, that leave the region named in `flash.region`, that overlap or that repeat a name.

## The profile of the platform

The platform picks its profile in `profile:` (`rv32im`, `rv32em_zicsr`, ...) and says where the specification of the profiles is in `profiles:`, a path relative to the `platform.yaml` (the `profiles/matrix.yaml` of the Core). The name starts with `rv32i` (32 registers) or `rv32e` (16) and must be one of the profiles of the specification. It gives:

| Output | Content |
| :--- | :--- |
| VHDL package | `HAS_E` (true on the RV32E) and one boolean `HAS_<EXTENSION>` per extension of the core (`HAS_M`, `HAS_ZMMUL`, `HAS_ZICSR`, `HAS_ZICNTR`, `HAS_ZIHPM`, `HAS_ZIMOP`, `HAS_ZICOND`, `HAS_ZIHINTNTL`, `HAS_ZIHINTPAUSE`, `HAS_ZIFENCEI`, `HAS_ZICCLSM`, `HAS_INTERRUPTS`, `HAS_SSCOFPMF`) |
| `config.yaml` | `isa.base`, which picks `-march` and `-mabi` of the programs and of the boot memory (`rv32e` with `ilp32e`, the others with `ilp32`), and the `sim.parameters` `HAS_E` and `HAS_*` that the runner passes to GHDL |

`--profile NAME`, a global option of `riscv-tools`, replaces the `profile:` of the platform without editing it, to run the same platform over many profiles in a test matrix. It applies to `generate-memory-map` (writes the package of that profile), to `platform sync` and to every command that reads the configuration. A name that the specification does not list is rejected before anything runs.

`extras:` turns on what the profile does not turn on, by extension name (`extras: [Zihintntl, Zihintpause, Interrupts, Sscofpmf]`; `Sscofpmf` needs Zihpm in the profile and `Interrupts` in the extras, and generation fails without them), and it also holds with `--profile`. The matrix of the Core lists Zimop and Zicond as profile extensions, so only the names the matrix does not list depend on `extras:`; the first two are still accepted there. Every switch that neither the profile nor the extras turn on comes out `false` in the package.

```bash
uv run riscv-tools --root <project> --profile rv32em_zicsr generate-memory-map --platform src/platform/platform.yaml
```

## The interrupts of the platform

A platform with the machine interrupts turns on the `Interrupts` extra (the core enables them only with `Zicsr`), lists the `CLINT` and, for the external lines, the `EXT_IRQ` among the `peripherals`, and describes the clock in the `interrupts` section.

```yaml
extras: [Interrupts]
peripherals:
  - {name: CLINT,   base: 0xE0000000, id: 6}
  - {name: EXT_IRQ, base: 0xF0000000, id: 7}
interrupts:
  clock_hz: 50000000   # clock of the domain of the core and the CLINT
  mtime_hz: 1000000    # rate at which the mtime of the CLINT counts
```

The `mtime` of the CLINT is a counter of its own, set by `mtime_hz`, and it is independent of the CSR `time` of Zicntr, which the core serves. `clock_hz` must be a multiple of `mtime_hz`, the profile must turn on `has_interrupts`, and the `peripherals` list must have the `CLINT`; the absence of any of them is an error before generating and in `check-memory-map`.

| Output | Constants |
| :--- | :--- |
| VHDL package (`vhdl`) | `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES` (clock cycles per increment of `mtime`, the `tick_cycles` generic of the CLINT), besides `CLINT_BASE`, `CLINT_ID`, `EXT_IRQ_BASE` and `EXT_IRQ_ID` |
| Runtime header (`runtime`) | `RV32_CLINT_BASE`, `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` and `RV32_MTIME_HZ`, which `FreeRTOSConfig.h` uses in `configMTIMECMP_BASE_ADDRESS`, `configMTIME_BASE_ADDRESS` and `configCPU_CLOCK_HZ` |

The offsets of the registers inside the 64 KiB window of the CLINT follow the SiFive layout that the FreeRTOS port expects.

### PLIC and interrupt sources

A platform with a PLIC lists it in `peripherals` with a `size` (the window it decodes, a power of two of at least `0x200008` bytes) and describes it in `interrupts`.

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, id: 7, size: 4M}
interrupts:
  plic: {priority_bits: 3}
  sources:                 # ids of the lines wired to the PLIC
    - {name: UART, id: 1}
    - {name: TIMER, id: 5}
```

| Output | Constants |
| :--- | :--- |
| VHDL package (`vhdl`) | `PLIC_N_SOURCES` (the largest id), `PLIC_PRIORITY_BITS`, `PLIC_ADDR_WIDTH` (the window in words, as a power of two) and `IRQ_<NAME>` per source |
| Runtime header (`runtime`) | `RV32_PLIC_PRIORITY`, `RV32_PLIC_PENDING`, `RV32_PLIC_ENABLE`, `RV32_PLIC_THRESHOLD`, `RV32_PLIC_CLAIM` and `RV32_IRQ_<NAME>` per source |

Repeated ids, ids outside 1 to 1023, `priority_bits` outside 1 to 32 and a window with no `size` or an invalid one are errors before generating.

$$ \text{msip} = base, \quad \text{mtimecmp} = base + \texttt{0x4000}, \quad \text{mtime} = base + \texttt{0xBFF8} $$

## The clock of the SDRAM controller

A platform with an SDRAM describes the clock of the controller and the phase of the `DRAM_CLK` pin against it in the `sdram` section. Both values come from the PLL of the platform and from the Quartus timing report, and the section is their single source.

```yaml
sdram:
  clock_hz: 100000000       # controller clock (PLL output 0)
  dram_clk_phase_ps: 4000   # phase of DRAM_CLK against it (PLL output 1)
```

| Output | Content |
| :--- | :--- |
| VHDL package (`vhdl`) | `SDRAM_CLOCK_HZ` and `SDRAM_TCK_PS`, the period in picoseconds with which the controller and the chip model convert the chip timings into cycles |
| `checks` symbols | `SDRAM.clock_mhz`, `SDRAM.tck_ps` and `SDRAM.dram_clk_phase_ps`, which keep the PLL file equal to the map |

`clock_hz` must have a whole period in picoseconds and the phase must lie inside one period; both fields are required, and the absence of either is an error before generating and in `check-memory-map`.

## The memories and caches of the platform

The `memory` section of the `platform.yaml` picks four independent things per platform, and the 16 combinations come out of them. No field has a default, so forgetting one is an error and the platform never builds a combination other than the one its author wrote. A platform without the section keeps generating the package it generated before.

```yaml
memory:
  rom:    {external: true}
  ram:    {external: true}
  icache: {enabled: true, size_bits: 4096}
  dcache: {enabled: true, size_bits: 4096}
```

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `rom.external` | boolean | The FLASH sits outside the chip |
| `ram.external` | boolean | The RAM sits outside the chip |
| `icache.enabled` | boolean | An instruction cache exists |
| `icache.size_bits` | power of two, at least 256 | Size of the instruction cache in bits; required only with `enabled: true` |
| `dcache.enabled` | boolean | A data cache exists |
| `dcache.size_bits` | power of two, at least 256 | Size of the data cache in bits; required only with `enabled: true` |

The `rom_external` and `ram_external` fields of `generate.vhdl` are derived from the `memory` section, and having both together is an error.

### Generated constants

The VHDL package gains the constants below. `ROM_VIA_PORT` and `RAM_VIA_PORT` are the values of the `rom_external` and `ram_external` generics of the core, because a cache can only exist on the side of the core port protocol.

| Constant | Type | Value |
| :--- | :--- | :--- |
| `ROM_EXTERNAL` | boolean | `memory.rom.external` |
| `RAM_EXTERNAL` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, or 256 without the cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, or 256 without the cache |
| `ROM_VIA_PORT` | boolean | `ROM_EXTERNAL or HAS_ICACHE` |
| `RAM_VIA_PORT` | boolean | `RAM_EXTERNAL or HAS_DCACHE` |

In the `config.yaml` the same values arrive as `sim.parameters` with the same names (`ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` and `DCACHE_SIZE_BITS`), and the simulation top must declare the matching generics. Without `config.addr_widths` in the platform, the address widths come from the choice, and the `boot_memory` and each internal memory are listed, since an external memory is a chip sized by the top itself. With `config.addr_widths` listed, the list wins.

### Validation

| Rule | Condition | Result |
| :--- | :--- | :--- |
| V1 | The four booleans exist and there is no unknown key | Error |
| V2 | `size_bits` is a power of two and at least 256 | Error |
| V3 | With any cache, the ROM and the RAM each fit one aligned 64 MiB window | Error |
| V4 | With the ROM through the core port, its size fits the 1024 KiB window of the router | Error |
| V5 | An `exec` region in the RAM needs an external RAM and the ROM through the port (external ROM or instruction cache) | Error |
| V7 | An `exec` region in the RAM behind the instruction cache needs Zifencei in the profile | Error |
| V8 | Instruction cache over an internal ROM or data cache over an internal RAM | Warning |
| V9 | Platform with peripherals | Note |
| V10 | With any cache, `reserved.fromhost` exists and sits in the last 4 KiB page of the RAM, the one the cache skips | Error |

An external ROM without an instruction cache is valid. The warning and the note are printed as `NOTE` on the standard error of `generate-memory-map`, and errors stop the generation.

### The `--memory` option

`--memory`, a global option of `riscv-tools`, replaces fields of the `memory` section without editing the platform, to run the same platform over the 16 combinations. The value is a comma list of `key=value` pairs.

| Key | Values |
| :--- | :--- |
| `rom`, `ram` | `int` or `ext` |
| `icache`, `dcache` | `on`, `off` or a size in bits, which turns the cache on |

A key that is not named keeps the choice of the platform, and a platform without the `memory` section needs the four keys. `on` without a size uses the `size_bits` of the platform, or 4096 if it has none. A malformed value is rejected before anything runs.

```bash
uv run riscv-tools --root <project> --memory rom=ext,ram=int,icache=on,dcache=off generate-memory-map --platform src/platform/platform.yaml
```

## Reading the configuration from the map

A project `config.yaml` declares `memory_map: <path of the platform.yaml>`, and the configuration loader replaces the keys the map fixes with the map's own: `isa.base`, `memory.boot_memory_base`, `boot_memory_words`, `rom_base`, `rom_words`, `ram_base`, `ram_words`, `tohost_addr`, `fromhost_addr` `sim.env.TOHOST_ADDR`, `sim.env.STDOUT_ADDR` (the testbench reads the address from the environment) and, for the memories the `config.addr_widths` section of the map lists, `sim.parameters.<memory>_addr_width`. What the map fixes wins over what the file or its `extends` say, so no address or size is written twice.

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_memory, rom, ram]
```

`platform sync` writes the values already replaced, so Tests and Certification do not need the `platform.yaml`.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_memory_map.py::test_evaluate_number_notations` | Hex, VHDL-based, `K`, `u` suffix and arithmetic. |
| `tests/test_memory_map.py::test_evaluate_symbols_and_log2` | Symbols in expressions, `log2`/`clog2`, and `log2` rejecting non powers of two. |
| `tests/test_memory_map.py::test_evaluate_rejects_unknown_symbol_inexact_division_and_code` | Unknown symbols, inexact division and arbitrary code are rejected. |
| `tests/test_memory_map.py::test_symbols_flattens_regions_reserved_boot_and_peripherals` | The symbol table. |
| `tests/test_memory_map.py::test_the_reference_platform_is_consistent` | A consistent map has no problems. |
| `tests/test_memory_map.py::test_validate_platform_reports_an_inconsistent_map` | Overlaps, reserved outside RAM, bad boot entries and peripheral ids. |
| `tests/test_memory_map.py::test_check_passes_when_every_copy_agrees` | Five copies in five formats agree. |
| `tests/test_memory_map.py::test_check_fails_when_one_copy_diverges` | Changing any one copy fails exactly its check. |
| `tests/test_memory_map.py::test_check_reports_every_divergent_match_of_one_pattern` | Each divergent match is reported. |
| `tests/test_memory_map.py::test_check_fails_when_a_copy_no_longer_matches_the_pattern` | A reformatted copy is noticed. |
| `tests/test_memory_map.py::test_check_fails_on_a_missing_file_unless_optional` | Missing file fails unless `optional`. |
| `tests/test_memory_map.py::test_check_stops_at_an_inconsistent_map` | No copy is read when the map itself is inconsistent. |
| `tests/test_memory_map.py::test_load_platform_rejects_a_non_mapping` | A non-mapping file is rejected. |
| `tests/test_memory_map.py::test_cmd_check_memory_map_exit_status` | The command prints OK, or exits 1 listing the mismatches. |
| `tests/test_interrupts.py` | The package has `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES`, the header has the registers of the CLINT and the rate of `mtime`, and an inconsistent section (rate, missing CLINT, profile without the interrupts) is rejected. |
| `tests/test_memory_choice.py` | The `memory` section and the `--memory` option make the 16 combinations 16 different packages, the constants and the simulation parameters come from the choice, and rules V1 to V5, V7 and V10 fail with a clear message. |
| `tests/test_config_from_platform.py` | The `memory` keys, the `tohost` and `stdout` environment and the address widths come from the map, and the map wins over the file and its `extends`. |
| `tests/test_generate_memory_map.py` | The specs, the linker script and the VHDL package come out of the map; `--check` catches a missing or edited file; an address off the KiB grid and an inconsistent map are rejected; the command writes and checks. |

## Usage

```bash
uv run riscv-tools --root <project> check-memory-map --platform platforms/internal-mem.yaml
```

No `--config` needed. Exit status 1 and one `MISMATCH` line per disagreement when a copy diverges; meant for CI.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
