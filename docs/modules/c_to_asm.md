# `c_to_asm`

Compiles a single C source straight to human-readable RISC-V assembly (`gcc -S`), for inspecting or debugging codegen. A `.S` source is already assembly and is copied through unchanged rather than reprocessed.

## Configuration

Shares the same toolchain/ISA settings as [`compiler`](compiler.md) (`toolchain.gcc`, `isa.base`, `isa.canonical_order`), since it's the same compiler and the same `RV32_EXT` header convention, only a different output format.

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
```

Writes one `.s` file per discovered test, alongside the normal `.mif`/`.hex` build output, for reading rather than running.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
