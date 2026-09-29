# `c_to_asm`

Compiles a single C source straight to human-readable RISC-V assembly (`gcc -S`), for inspecting or debugging codegen. A `.S` source is already assembly and is copied through unchanged rather than reprocessed.

## Configuration

Shares the same toolchain/ISA settings as [`compiler`](compiler.md) (`toolchain.gcc`, `isa.base`, `isa.canonical_order`), since it's the same compiler and the same `RV32_EXT` header convention, only a different output format.

## Prerequisites

- the RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `GCC_SETUP.md`.

## Tests

No automated test in this repository. `compile --emit asm` is not covered by a test here; a project can check the output by hand.


## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
```

Writes one `.s` file per discovered test, alongside the normal `.mif`/`.hex` build output, for reading rather than running.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
