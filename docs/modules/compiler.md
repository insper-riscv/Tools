# `compiler`

Compiles one bare-metal test source (`.c` or `.S`) into a linked `.elf`/`.bin`. This is what `compile --emit mif|hex|asm` (see Usage below) calls once per test discovered in a project's `c_dir`/`asm_dir`.

## Per-test header conventions

A test's own source file declares its build/run requirements in comments at the top, parsed by this module:

| Header | Meaning |
| :--- | :--- |
| `// RV32_EXT: M` | Compiled with `-march=rv32im` (extension letters add onto the implicit `rv32i` base; comma-separated, order doesn't matter, normalized via `isa.canonical_order`). Omitted entirely means plain `rv32i`. |
| `// RV32_TEST_KIND: unit` | Default if omitted. Checked via the PASS/FAIL mailbox only (see [`mailbox`](mailbox.md)). |
| `// RV32_TEST_KIND: memory` | Also dumps RAM and compares it against a golden JSON (see [`mem_validator`](mem_validator.md), [`golden_generator`](golden_generator.md)). |
| `// RV32_TIMEOUT_S: 5` | How long [`orchestrator`](orchestrator.md) waits for this test's mailbox before falling back to a full reprogram. Defaults to `orchestrator`'s `default_timeout_s`. |

## C library

`toolchain.libc` selects what a test links against:

| Value | Flags | Use |
| :--- | :--- | :--- |
| `none` (default) | `-nostdlib` | Works with any toolchain. A test that needs `malloc` or similar gets it from the project's own `paths.syscalls`. |
| `picolibc` | `--specs=picolibc.specs -Wl,--no-gc-sections` | For a GCC configured with picolibc, such as the one Infra's `GCC_SETUP.md` builds for `rv32im`/`ilp32`. `strlen`, `memcpy`, `printf` and the rest come from picolibc. |

The startup code stays the project's own `crt0.S` (`-nostartfiles` in both cases). `picolibc.specs` turns on `--gc-sections`, which drops every section a link script neither keeps nor reaches from its entry, so it is switched off again. That toolchain has a single library variant (`rv32im`/`ilp32`), so a test built for a narrower `-march` links library code that may use instructions its core lacks, such as multiplication and division in `printf`.

## Hex output

With `sim.hex_format: verilog`, the simulation `.hex` comes straight from the linked ELF through `objcopy -O verilog --verilog-data-width=4` instead of from the flat binary. The file keeps the image's real word addresses:

```
@00000200
00100293 00200313 FF9FF06F
@00000203
DEADBEEF
```

A program linked at `0x800` starts at `@00000200` (word address), so it needs no leading zero words, and a gap between sections becomes a new `@` line. The default `words` format keeps one 32-bit word per line.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `toolchain.gcc` | GCC binary name/path (default `riscv32-unknown-elf-gcc`). |
| `toolchain.objcopy` | objcopy binary name/path (default `riscv32-unknown-elf-objcopy`). |
| `toolchain.libc` | `none` or `picolibc` (default `none`); see [C library](#c-library). |
| `isa.base` | Base ISA letter, always `i`, never written in a test's own header. |
| `isa.default_ext` | Extension string used when a test has no `RV32_EXT` header at all. Empty by default (plain `rv32i`). |
| `isa.canonical_order` | Fixed letter order extension letters get sorted into before being appended to the base ISA string, so `RV32_EXT: A,M` and `RV32_EXT: M,A` both normalize to the same `-march=` value. |
| `paths.include_dir`, `paths.crt0`, `paths.linker_script`, `paths.build_dir`, `paths.c_dir`, `paths.asm_dir` | All project-specific paths inside the consuming repo; no default, every project must set these. |

## Prerequisites

- the RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `GCC_SETUP.md`.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_compiler_headers.py::test_canonical_march_no_ext` | A test with no extension header resolves to the base ISA. |
| `tests/test_compiler_headers.py::test_canonical_march_single_ext` | One extension letter is appended to the base. |
| `tests/test_compiler_headers.py::test_canonical_march_order_independent` | Extension letters are sorted into the canonical order. |
| `tests/test_compiler_headers.py::test_parse_header_defaults` | Headers that are absent fall back to the defaults. |
| `tests/test_compiler_headers.py::test_parse_header_all_fields` | `RV32_EXT`, `RV32_TEST_KIND` and `RV32_TIMEOUT_S` are all read. |
| `tests/test_cli_compile.py::test_discover_tests_finds_c_and_asm_sorted_by_name` | C and assembly tests are found and sorted by name. |
| `tests/test_cli_compile.py::test_discover_tests_empty_when_no_folders` | No test folders yields no tests. |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | A C test, a C memory test and an assembly test compile and land in the manifest. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | The same tests compile for simulation. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_uses_the_verilog_format_when_configured` | `sim.hex_format: verilog` writes the `objcopy` layout. |
| `tests/test_compiler_hex.py::test_elf_to_verilog_hex_keeps_the_real_word_address` | An image linked at `0x800` starts at `@00000200` with no zero padding. |
| `tests/test_compiler_libc.py::test_libc_flags_defaults_to_no_libc` | Without `toolchain.libc`, tests link with `-nostdlib`. |
| `tests/test_compiler_libc.py::test_libc_flags_picolibc_keeps_sections_the_link_script_does_not_reach` | `picolibc` selects the specs and turns garbage collection of sections off. |
| `tests/test_compiler_libc.py::test_libc_flags_rejects_an_unknown_library` | An unknown value raises an error naming the key. |
| `tests/test_compiler_libc.py::test_picolibc_provides_libc_functions` | A test calling `strlen` links with `picolibc` (skipped without a GCC configured with picolibc). |
| `tests/test_compiler_libc.py::test_no_libc_leaves_libc_functions_undefined` | The same test fails to link with `none` (skipped without a GCC configured with picolibc). |


## Usage

Not its own CLI subcommand: it's what `compile` (see the top-level [README](../../README.md#usage)) runs once per discovered test, before handing the result to [`bin_to_image`](bin_to_image.md) (for `.mif`/`.hex`), [`c_to_asm`](c_to_asm.md) (for `.S` inspection), or [`golden_generator`](golden_generator.md) (for a `memory`-kind C test's auto-generated golden).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
