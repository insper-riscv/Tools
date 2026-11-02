# `memory_map`

Checks that every hand-written copy of a platform's memory map agrees. The map (region bases and sizes, the words the boot ROM reserves at the top of RAM, the boot entry points, the peripheral windows) is needed in many files: linker flags, boot ROM, C runtime, VHDL, Quartus IPs, the project's `config.yaml`. Each copy is only noticed when it disagrees on the board. One YAML file, the platform, is the source of truth; this module reads each copy and reports every disagreement.

## Configuration

No `config.yaml` section: the platform file is self-describing and is passed with `--platform`.

```yaml
regions:                      # the map itself
  - {name: BOOT_ROM, base: 0x0,    size: 2K,   kind: rom, exec: true}
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
- Before the copies are read the map itself is validated: regions and reserved words do not overlap, reserved words sit inside a RAM region, `boot.entry` is in an executable region, `boot.wait_restart` is in the first region, each peripheral base matches its id.

## Generating the files of the map

The same YAML can say, in the `generate` section, which files come out of it, so no copy of the map has to be written by hand.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `specs` | GCC specs file | The linker flags: `__flash`, `__flash_size`, `__ram`, `__ram_size` and `rv32_wait_restart`. The RAM of the linker ends where the reserved word `ram_limit` begins |
| `boot_ld` | Boot ROM linker script | The `boot_rom` memory in the first region and the `RESET_RESERVED` from `boot.wait_restart` |
| `vhdl` | VHDL package | The constants `BOOT_ROM_BITS`, `ROM_END_KIB`, `RAM_BASE_KIB`, `RAM_END_KIB`, `EXT_BASE_KIB` and `PERIPH_BASE_KIB`, the `ROM_EXTERNAL` and `RAM_EXTERNAL` flags and the base of each peripheral |

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout}
  boot_ld: {path: runtime/boot_rom.ld}
  vhdl:
    path: rtl/map_pkg.vhd
    package: map_pkg
    rom: FLASH
    ram: RAM
    ext_base: 0x40000000
    periph_base: 0x80000000
```

The limits of the VHDL package are the generics of the `core`, in KiB, so an address that is not a multiple of 1 KiB is an error. The map is validated before generating, and an inconsistent map generates nothing.

```bash
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml --check
```

With `--check` nothing is written, and the command exits with status 1 when a file is missing or differs from what the map would generate. It needs no `--config`.

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
| `tests/test_generate_memory_map.py` | The specs, the linker script and the VHDL package come out of the map; `--check` catches a missing or edited file; an address off the KiB grid and an inconsistent map are rejected; the command writes and checks. |

## Usage

```bash
uv run riscv-tools --root <project> check-memory-map --platform platforms/internal-mem.yaml
```

No `--config` needed. Exit status 1 and one `MISMATCH` line per disagreement when a copy diverges; meant for CI.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
