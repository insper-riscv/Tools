# `ram_dump`

Saves a RAM instance's entire content to a `.mif` over JTAG. Used for `RV32_TEST_KIND: memory` tests, where the PASS/FAIL mailbox alone isn't enough to prove a test did the right thing (it wrote the right values to memory, not just that it reached its own pass signal): see [`mem_validator`](mem_validator.md), which compares the resulting dump against a golden JSON.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_mem_instance` | Instance index Quartus' In-System Memory Content Editor assigns to the RAM debug tap. `1` is the common case. |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml dump-ram <output.mif>
```

Also called internally by [`orchestrator`](orchestrator.md) after each `memory`-kind test, before handing the dump to [`mem_validator`](mem_validator.md).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
