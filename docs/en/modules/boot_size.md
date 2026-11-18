# `boot_size`

Assembles the BOOT of a platform with the toolchain and measures its size against the BOOT_MEMORY, before any hardware. The generated linker script already has an `ASSERT` that fails a BOOT that is too big, but it only fires when someone links the BOOT. The measure here runs in CI and on the machine of the developer, and says how much each file weighs.

## 1. Inputs

Everything comes from the `platform.yaml`, with no `--config`.

| Datum | Source |
| :--- | :--- |
| Linker script | `generate.boot_ld` |
| Source of the BOOT | `boot_memory.S`, in the same folder as the linker script |
| Limit | Size of the first region, the BOOT_MEMORY |
| `-march` and `-mabi` | The base and the width of the `core` block (`rv32i`, `rv32e`, `rv64i` or `rv64e`), the base only, without the extensions |

The `boot_memory.S` includes the generated headers (`memory_map.h`, `boot_config.h`) and the boot fragment of each extension of the core, so the headers must have been generated with `generate-memory-map`.

## 2. How it measures

1. Copies the generated linker script without the `ASSERT` that compares the end of the image with the memory, and with the memory made wider, so a BOOT that is too big is measured and not refused. The `ASSERT` of the reset section stays.
2. Assembles and links the `boot_memory.S` with `-g`, so each instruction keeps the file and the line it came from.
3. Reads the end of the last code section with `objdump -h`. The size is that address minus the base of the BOOT_MEMORY, so the gap between `_reset` and the wait point (`boot.wait_restart`) counts.
4. Adds 4 bytes per instruction of each file, read from `objdump -d -l`, which tells `boot_core.S` apart from each `boot.inc` fragment.

## 3. Result

| Situation | Output | Status |
| :--- | :--- | :--- |
| The BOOT fits | `boot size OK`, the size, the limit and the bytes of each file | 0 |
| The BOOT overflows | `V-B3`, the size, the limit, the excess and the bytes of each file, heaviest first | 1 |
| No `generate.boot_ld`, no `boot_memory.S` or a toolchain that fails | The message of the problem | 2 |

## 4. Usage

```bash
uv run riscv-tools --root <project> check-boot-size --platform src/simulation/modular/platform.yaml
```

| Option | Effect |
| :--- | :--- |
| `--gcc` | The compiler of the toolchain, `riscv32-unknown-elf-gcc` by default |
| `--objdump` | The `objdump` of the toolchain, `riscv32-unknown-elf-objdump` by default |
| `--build-dir` | Where to write the measure build, a temporary folder by default |

It needs the toolchain on the `PATH`, which the `ci-elf` and `dev_tools` images of [Infra](https://github.com/insper-riscv/Infra) carry.

## 5. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_boot_size.py` | The measure linker script, the BOOT that fits (size and gap of the wait point), the sum of bytes per file, the BOOT that overflows with `V-B3`, the base E assembled as `rv32e`, the platform without `generate.boot_ld` and statuses 1 and 2 of the subcommand. |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
