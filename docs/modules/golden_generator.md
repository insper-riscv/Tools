# `golden_generator`

Generates a golden JSON dynamically by running a compiled test's ELF under Spike (RISC-V International's reference simulator) until it signals completion through HTIF `tohost`, then reading the requested memory range from the signature file Spike writes, instead of a human working out expected memory values by hand. Full mechanism and requirements: [docs/generating-a-golden.md](../generating-a-golden.md).

## Configuration

| Key | Meaning |
| :--- | :--- |
| `toolchain.nm` | `nm` binary used to resolve a symbol's address in the compiled ELF (default `riscv32-unknown-elf-nm`). |
| `emulator.spike_bin` | Name or path of the `spike` binary (default `spike`). It must keep its debug module away from address 0 (see [docs/generating-a-golden.md](../generating-a-golden.md#requirements)); the first run checks this. |
| `emulator.timeout_s` | Seconds to wait for a test to write `tohost` before failing the generation (default `60`). |
| `toolchain.objcopy` | `objcopy` binary used to add the symbols Spike needs to a copy of the ELF (shared with [`compiler`](compiler.md)). |
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
