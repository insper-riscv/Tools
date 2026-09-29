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
| `isa.base` | Base ISA letter, always `i`, never written in a test's own header. |
| `isa.default_ext` | Extension string used when a test has no `RV32_EXT` header at all. Empty by default (plain `rv32i`). |
| `isa.canonical_order` | Fixed letter order extension letters get sorted into before being appended to the base ISA string, so `RV32_EXT: A,M` and `RV32_EXT: M,A` both normalize to the same `-march=` value. |
| `paths.include_dir`, `paths.crt0`, `paths.linker_script`, `paths.build_dir`, `paths.c_dir`, `paths.asm_dir` | All project-specific paths inside the consuming repo; no default, every project must set these. |

## Usage

Not its own CLI subcommand: it's what `compile` (see the top-level [README](../../README.md#usage)) runs once per discovered test, before handing the result to [`bin_to_image`](bin_to_image.md) (for `.mif`/`.hex`), [`c_to_asm`](c_to_asm.md) (for `.S` inspection), or [`golden_generator`](golden_generator.md) (for a `memory`-kind C test's auto-generated golden).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
