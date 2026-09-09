# `certify`

Builds and runs the ACT4 (RISC-V Architectural Certification Tests) suite under cocotb/GHDL, validating against the official `riscv-arch-test` suite rather than a project's own hand-picked tests. Never touches real hardware: ACT4 tests have no golden JSON of their own and signal completion via HTIF `tohost`, not a project's PASS/FAIL mailbox convention.

Two stages, owned by different tools:

1. `build_elfs` shells out to ACT4's own `make` (in the vendored `vendor/riscv-arch-test`) to compile self-checking ELFs for a project's own ACT4 target. ACT4 owns test generation/compilation entirely; the consuming project only supplies DUT-specific config (target config YAML, UDB YAML, macros header, linker script).
2. `run_suite` converts each built ELF the same way [`compiler`](compiler.md) converts a project's own tests (`objcopy` to raw `.bin`, then [`bin_to_image`](bin_to_image.md) to `.hex`), then drives it through the same cocotb/GHDL toplevel [`sim_runner`](sim_runner.md) uses for the regular suite, reusing `sim.vhdl_sources`/`sim.toplevel`/`sim.ghdl_std` from `config.yaml` directly. Only `test_module` differs, since ACT4 tests signal completion via HTIF rather than the project's own mailbox convention.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `act.vendor_dir` | Path to the vendored ACT4 framework itself (default `vendor/riscv-arch-test`). |
| `act.target_config` | The project's own ACT4 target config file. No default. |
| `act.extensions` | Comma-separated extension list forwarded to ACT4's own `make ... EXTENSIONS=` (default `"I,M"`). |
| `act.jobs` | `make`'s own parallelism (default `0`, ACT4's own auto-detect). |
| `act.sim_parameters` | Merged on top of `sim.parameters`; only needed to override something ACT4's own, typically larger images need sized differently than the project's real-hardware budget (e.g. `rom_addr_width`/`ram_addr_width`). Empty by default. |

## Usage

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml certify
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
