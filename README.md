# riscv-tools

Build/JTAG tooling for bare-metal RV32IM test programs: compile,
write ROM/RAM over JTAG, program the base bitstream, and orchestrate
a real-hardware test run — factored into one module per responsibility,
each with its own `__config__.py` of defaults. A consuming project
(e.g. `RISC-V-Workstation-Tests`) supplies its own `config.yaml`,
which overrides these defaults (see `riscv_tools/settings.py`).

## Modules

| Module              | Responsibility                                              |
|----------------------|--------------------------------------------------------------|
| `compiler`           | .c/.S -> .elf/.bin -> .mif/.hex, header parsing (`RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`) |
| `jtag`               | Live JTAG cable detection, generic `.tcl` runner            |
| `mem_edit`           | Generic In-System Memory Content Editor primitives (read/write word, write-full, dump) |
| `rom_writer`         | JTAG-write a ROM image without reprogramming                |
| `ram_zero`           | JTAG-zero the whole RAM without reprogramming                |
| `ram_dump`           | JTAG-dump the whole RAM to a `.mif`                          |
| `mailbox`            | PASS/FAIL mailbox read + restart "go flag" pulse             |
| `quartus_program`    | Full recompile + `quartus_pgm` (the slow "base" path)        |
| `golden`             | Compare a RAM dump against a golden JSON                     |
| `orchestrator`       | Composes the above into a full test-suite run                |

## Usage

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml run
```

See `riscv-tools --help` for the full subcommand list (`write-rom`,
`zero-ram`, `dump-ram`, `program`, `mailbox read|pulse`, `run`).

## Development

```bash
uv sync --group dev
uv run pytest
```
