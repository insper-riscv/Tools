# RISC-V Tools

🌐 [Português](README.md) · [English](README.en.md)

Config-driven build and test tooling for bare-metal RISC-V or virtual
hardware simulation: the same compiled test runs either against real
hardware over JTAG or against cocotb/GHDL simulation; results
can be verified against Spike-generated or checked-in golden references.
Organized as one module per responsibility, each with its own
`__config__.py` of defaults; a consuming project supplies its own
`config.yaml`, which overrides these defaults. See
[docs/configuration.md](docs/en/configuration.md) for the full reference.

## Modules

| Module              | Responsibility                                              | Doc |
|----------------------|--------------------------------------------------------------|-----|
| `compiler`           | .c/.S -> .elf/.bin, header parsing (`RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`) | [docs/modules/compiler.md](docs/en/modules/compiler.md) |
| `bin_to_image`       | .bin -> .mif/.hex (memory-image formats, no compiler involved)    | [docs/modules/bin_to_image.md](docs/en/modules/bin_to_image.md) |
| `c_to_asm`           | .c -> human-readable RISC-V assembly (`gcc -S`), for inspecting codegen | [docs/modules/c_to_asm.md](docs/en/modules/c_to_asm.md) |
| `boot_rom`           | Builds the fixed, shared bootloader, once, reused across every test | [docs/modules/boot_rom.md](docs/en/modules/boot_rom.md) |
| `jtag`               | Live JTAG cable detection, generic `.tcl` runner            | [docs/modules/jtag.md](docs/en/modules/jtag.md) |
| `mem_edit`           | Generic In-System Memory Content Editor primitives (read/write word, write-full, dump) | [docs/modules/mem_edit.md](docs/en/modules/mem_edit.md) |
| `rom_writer`         | JTAG-write a ROM image without reprogramming                | [docs/modules/rom_writer.md](docs/en/modules/rom_writer.md) |
| `ram_zero`           | JTAG-zero the whole RAM without reprogramming                | [docs/modules/ram_zero.md](docs/en/modules/ram_zero.md) |
| `ram_dump`           | JTAG-dump the whole RAM to a `.mif`                          | [docs/modules/ram_dump.md](docs/en/modules/ram_dump.md) |
| `mailbox`            | PASS/FAIL mailbox read + restart "go flag" pulse             | [docs/modules/mailbox.md](docs/en/modules/mailbox.md) |
| `quartus_program`    | Full recompile + `quartus_pgm` (the slow "base" path)        | [docs/modules/quartus_program.md](docs/en/modules/quartus_program.md) |
| `mem_validator`      | Compare a RAM dump against a golden JSON                     | [docs/modules/mem_validator.md](docs/en/modules/mem_validator.md) |
| `golden_generator`   | Generate a golden JSON dynamically by running an ELF under Spike | [docs/modules/golden_generator.md](docs/en/modules/golden_generator.md) |
| `spike_exec`         | Prepares and launches Spike runs: preflight, ELF symbols, command line (shared by `golden_generator` and `spike_run`) | [docs/modules/spike_exec.md](docs/en/modules/spike_exec.md) |
| `spike_run`          | Runs each compiled test to completion under Spike and reports PASS/FAIL from its HTIF verdict, with no hardware | [docs/modules/spike_run.md](docs/en/modules/spike_run.md) |
| `orchestrator`       | Composes the above into a full real-hardware test-suite run, or a clock frequency sweep to find Fmax | [docs/modules/orchestrator.md](docs/en/modules/orchestrator.md) |
| `sim_runner`         | Drives cocotb/GHDL simulation: the sim-side counterpart to `orchestrator` (needs the `sim` extra) | [docs/modules/sim_runner.md](docs/en/modules/sim_runner.md) |
| `certify`            | Builds and runs the ACT4 architectural certification suite under cocotb/GHDL | [docs/modules/certify.md](docs/en/modules/certify.md) |
| `vhdl_sort`          | Topologically sort VHDL sources by entity/package dependency, for GHDL `-a` | [docs/modules/vhdl_sort.md](docs/en/modules/vhdl_sort.md) |
| `freq_sweep`         | Rewrite a PLL source's clock frequency/phase offsets: the mechanism `orchestrator`'s frequency sweep edits with | [docs/modules/freq_sweep.md](docs/en/modules/freq_sweep.md) |
| `run_log`            | Rotates and tees a run's full console output into a persistent per-kind log history | [docs/modules/run_log.md](docs/en/modules/run_log.md) |

## Rule: one module, one responsibility

Every module in the table above owns exactly one job. When adding or
changing code:

- New functionality that doesn't fit an existing module's
  responsibility gets its **own new module**; don't bolt it onto the
  nearest unrelated one just because it's convenient to import from
  there.
- Logic needed by **two or more** modules gets factored into its own
  module (or a small private helper shared via an explicit import),
  not copy-pasted into each caller. Duplication between modules is how
  a fix applied to one copy silently leaves the other one broken, with
  nothing at either call site hinting that a second copy even exists.
- If you're unsure whether something is a new responsibility or fits
  an existing one, prefer the smaller, more specific module: merging
  two modules later is easy; un-tangling a module that grew several
  unrelated jobs is not.

## Toolchain dependencies

The RISC-V binaries (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) come
from one GCC toolchain and are resolved through `PATH`; Spike is needed
only to generate goldens.

| Command | GCC | objcopy | nm | Spike |
|---|---|---|---|---|
| `compile --emit asm` | yes | no | no | no |
| `compile --emit mif` / `--emit hex` | yes | yes | only for `memory` tests written in C | only for `memory` tests written in C |
| `generate-golden` | no | no | yes | yes |
| `spike-run` | no | yes | yes | yes |
| `program`, `sim` | yes (boot ROM) | yes (boot ROM) | no | no |
| `certify` | yes (through ACT4's own build) | yes | no | no |

## Installing the toolchain

The RISC-V GCC toolchain and Spike come from the workstation install in
[insper-riscv/Infra](https://github.com/insper-riscv/Infra)
(`GCC_SETUP.md` and `SPIKE_SETUP.md`): both live in a shared cache
(`/opt/riscv-foundation`) and are put on `PATH` by wrappers in
`/usr/local/bin`. This package builds nothing itself.

Spike has to keep its debug module away from address 0, which the Infra
build does. A stock Spike aborts at startup with `devices at [0, 1000) and
[0, 10000) overlap` for a target whose ROM starts at address 0; the golden
generator checks this before its first run and points at `SPIKE_SETUP.md`
when it fails.

## Docs

- [Configuration reference](docs/en/configuration.md)
- [Creating a test in C](docs/en/creating-a-c-test.md)
- [Creating a test in ASM](docs/en/creating-an-asm-test.md)
- [Generating a golden JSON via Spike](docs/en/generating-a-golden.md)
- [Finding Fmax (clock frequency sweep)](docs/en/finding-fmax.md)
- [Creating a GitHub Actions workflow per task](docs/en/github-actions.md)

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
`generate-golden`, `spike-run`, `run`, `sim`, `vhdl-sort`, `freq-sweep`).

```bash
# vhdl-sort needs no --config; pure file-content analysis, e.g. wired
# into a Makefile's own VHDL-syntax-check target:
uv run riscv-tools vhdl-sort src/**/*.vhd

# freq-sweep: find Fmax by editing the PLL and doing a full
# recompile+reprogram+RAM-compare at each candidate frequency. See
# docs/en/finding-fmax.md.
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --start 1 --stop 30 --step 2
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --binary --low 1 --high 50
```

## Development

```bash
uv sync --group dev --extra sim
uv run pytest
```

Tests that need GHDL, the RISC-V GCC or Spike skip when the tool is missing.
Each module's doc lists its prerequisites and the tests that cover it. The
tests check this package's own tooling; the processor is verified by the
consuming project's suites.

`tests/test_static_analysis.py` runs `ruff`, `pyright` and `deptry` over the whole
package, so it belongs to no single module.

### Running the tests in Docker

The `Dockerfile` starts from the toolchain image that
[insper-riscv/Infra](https://github.com/insper-riscv/Infra) publishes
(`ghcr.io/insper-riscv/infra-toolchain`, see its `TOOLCHAIN_IMAGE.md`): GHDL,
the RISC-V GCC with picolibc, a Spike patched as its `SPIKE_SETUP.md`
describes and `uv`, at the same paths the workstation install uses. It adds
this project's dependencies, so nothing is skipped and nothing is compiled:

```bash
docker build -t riscv-tools-tests .
docker run --rm -v "$PWD:/workspace" riscv-tools-tests
docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v
```

The base image is pinned to a `sha-` tag. To test against another
publication, pass its tag:

```bash
docker build --build-arg TOOLCHAIN_IMAGE=ghcr.io/insper-riscv/infra-toolchain:latest \
    -t riscv-tools-tests .
```

The `tests` workflow builds this image and runs the whole suite on every push
and pull request.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](LICENSE).
