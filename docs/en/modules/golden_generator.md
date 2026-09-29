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

## Prerequisites

- The RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `GCC_SETUP.md` (`gcc` builds the fixtures, `nm` and `objcopy` prepare the ELF).
- `spike` on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `SPIKE_SETUP.md` (the build keeps Spike's debug module away from address 0).

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_generate_golden.py::test_generate_golden_reads_back_expected_bytes` | A C test and an assembly test leave the expected bytes in the snapshot, little-endian. |
| `tests/test_generate_golden.py::test_generate_golden_json_round_trips_through_compare` | The golden JSON on disk holds the same bytes as the in-memory result. |
| `tests/test_generate_golden.py::test_symbol_range_resolves_address_and_size` | A sized symbol resolves to its address and size. |
| `tests/test_generate_golden.py::test_generate_golden_by_symbol_matches_explicit_start_end` | A range from a symbol equals the same range given by hand. |
| `tests/test_generate_golden.py::test_generate_golden_rounds_a_partial_word_range_up` | A 1-byte range yields the 4 bytes of its word. |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | `compile` generates the golden of a C memory test under Spike. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | The same for the simulation build. |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json
```

Also called internally by `compile` for every `memory`-kind C test that doesn't already have a checked-in `golden.json`, and by [`orchestrator`](orchestrator.md) when re-running a suite that needs one regenerated.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
