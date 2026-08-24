# RISC-V Tools

Build/JTAG tooling for bare-metal RV32IM test programs: compile,
write ROM/RAM over JTAG, program the base bitstream, and orchestrate
a real-hardware test run, organized as one module per responsibility,
each with its own `__config__.py` of defaults. A consuming project
supplies its own `config.yaml`, which overrides these defaults: See
[docs/configuration.md](docs/configuration.md) for the full reference.

## Modules

| Module              | Responsibility                                              |
|----------------------|--------------------------------------------------------------|
| `compiler`           | .c/.S -> .elf/.bin, header parsing (`RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`) |
| `bin_to_image`       | .bin -> .mif/.hex (memory-image formats, no compiler involved)    |
| `c_to_asm`           | .c -> human-readable RISC-V assembly (`gcc -S`), for inspecting codegen |
| `jtag`               | Live JTAG cable detection, generic `.tcl` runner            |
| `mem_edit`           | Generic In-System Memory Content Editor primitives (read/write word, write-full, dump) |
| `rom_writer`         | JTAG-write a ROM image without reprogramming                |
| `ram_zero`           | JTAG-zero the whole RAM without reprogramming                |
| `ram_dump`           | JTAG-dump the whole RAM to a `.mif`                          |
| `mailbox`            | PASS/FAIL mailbox read + restart "go flag" pulse             |
| `quartus_program`    | Full recompile + `quartus_pgm` (the slow "base" path)        |
| `mem_validator`      | Compare a RAM dump against a golden JSON                     |
| `golden_generator`   | Generate a golden JSON dynamically by running an ELF under Spike |
| `orchestrator`       | Composes the above into a full real-hardware test-suite run, or a clock frequency sweep to find Fmax |
| `sim_runner`         | Drives cocotb/GHDL simulation — the sim-side counterpart to `orchestrator` (needs the `sim` extra) |
| `vhdl_sort`          | Topologically sort VHDL sources by entity/package dependency, for GHDL `-a` |
| `freq_sweep`         | Rewrite a PLL source's clock frequency/phase offsets — the mechanism `orchestrator`'s frequency sweep edits with |

## Vendored references (git submodules)

| Path                     | Points at                                              | Why                                                          |
|---------------------------|--------------------------------------------------------|----------------------------------------------------------------|
| `vendor/riscv-gnu-toolchain` | [riscv-collab/riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) | The GCC cross-toolchain `compiler` builds test programs with |
| `vendor/riscv-isa-sim`    | [riscv-software-src/riscv-isa-sim](https://github.com/riscv-software-src/riscv-isa-sim) (Spike, RISC-V International's reference simulator) | Golden-reference source for `golden_generator` ([docs](docs/generating-a-golden.md)) |

Clone with `git clone --recurse-submodules`, or after a plain clone:
`git submodule update --init --recursive`.

## Docs

- [Configuration reference](docs/configuration.md)
- [Creating a test in C](docs/creating-a-c-test.md)
- [Creating a test in ASM](docs/creating-an-asm-test.md)
- [Generating a golden JSON via Spike](docs/generating-a-golden.md)
- [Finding Fmax (clock frequency sweep)](docs/finding-fmax.md)
- [Creating a GitHub Actions workflow per task](docs/github-actions.md)

## Usage

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json

# Simulation (needs the "sim" extra: cocotb + cocotb-tools, and GHDL on PATH)
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

See `riscv-tools --help` for the full subcommand list (`write-rom`,
`zero-ram`, `dump-ram`, `program`, `mailbox read|pulse`, `generate-header`,
`generate-golden`, `run`, `sim`, `vhdl-sort`, `freq-sweep`).

```bash
# vhdl-sort needs no --config — pure file-content analysis, e.g. wired
# into a Makefile's own VHDL-syntax-check target:
uv run riscv-tools vhdl-sort src/**/*.vhd

# freq-sweep: find Fmax by editing the PLL and doing a full
# recompile+reprogram+RAM-compare at each candidate frequency — see
# docs/finding-fmax.md.
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --start 1 --stop 30 --step 2
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --binary --low 1 --high 50
```

## Development

```bash
uv sync --group dev
uv run pytest
```
