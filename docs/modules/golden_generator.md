# `golden_generator`

Generates a golden JSON dynamically by running a compiled test's ELF under Spike (RISC-V International's reference simulator, `vendor/riscv-isa-sim`) instead of a human working out expected memory values by hand. Also manages building Spike itself the first time it's needed. Full mechanism and setup: [docs/generating-a-golden.md](../generating-a-golden.md).

## Configuration

| Key | Meaning |
| :--- | :--- |
| `toolchain.nm` | `nm` binary used to resolve a symbol's address in the compiled ELF (default `riscv32-unknown-elf-nm`). |
| `emulator.spike_bin` | Name or path of the built `spike` binary (default `spike`). If this doesn't already resolve to something runnable, `vendor/riscv-isa-sim` gets built. |
| `emulator.tohost_symbol` | HTIF symbol a test writes a nonzero value to on completion, which Spike watches to know when to snapshot memory (default `tohost`, the standard Spike/riscv-tests convention). |
| `emulator.entry_symbol` | Symbol Spike starts execution at (default `_start`), overridable for a project whose real entry point is something else, e.g. a shared bootloader's own reset vector. |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json
```

Also called internally by `compile` for every `memory`-kind C test that doesn't already have a checked-in `golden.json`, and by [`orchestrator`](orchestrator.md) when re-running a suite that needs one regenerated.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
