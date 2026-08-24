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
| `c_to_asm`           | .c -> human-readable RISC-V assembly (`gcc -S`), for inspecting codegen |
| `jtag`               | Live JTAG cable detection, generic `.tcl` runner            |
| `mem_edit`           | Generic In-System Memory Content Editor primitives (read/write word, write-full, dump) |
| `rom_writer`         | JTAG-write a ROM image without reprogramming                |
| `ram_zero`           | JTAG-zero the whole RAM without reprogramming                |
| `ram_dump`           | JTAG-dump the whole RAM to a `.mif`                          |
| `mailbox`            | PASS/FAIL mailbox read + restart "go flag" pulse             |
| `quartus_program`    | Full recompile + `quartus_pgm` (the slow "base" path)        |
| `mem_validator`      | Compare a RAM dump against a golden JSON, or generate one via Spike |
| `orchestrator`       | Composes the above into a full test-suite run                |

## Vendored references (git submodules)

| Path                     | Points at                                              | Why                                                          |
|---------------------------|--------------------------------------------------------|----------------------------------------------------------------|
| `vendor/riscv-gnu-toolchain` | [riscv-collab/riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) | The GCC cross-toolchain `compiler` builds test programs with |
| `vendor/riscv-isa-sim`    | [riscv-software-src/riscv-isa-sim](https://github.com/riscv-software-src/riscv-isa-sim) (Spike, RISC-V International's reference simulator) | Golden-reference source for `mem_validator generate-golden` (see below) |

Clone with `git clone --recurse-submodules`, or after a plain clone:
`git submodule update --init --recursive`.

### `mem_validator generate-golden`

Runs a compiled ELF under Spike, using its interactive debug console
(`-d`) to stop the instant the program writes its HTIF "done" signal
to `tohost_symbol` (default `tohost` — the standard Spike/riscv-tests
convention; see the consuming project's link.ld/crt0.S, which defines
`tohost`/`fromhost` and translates RV32_PASS/RV32_FAIL's mailbox value
into it), then snapshots the given byte range of RAM into a golden
JSON in the same format `compare` expects.

Requires `vendor/riscv-isa-sim` to be built first:
```bash
sudo apt-get install -y device-tree-compiler libboost-all-dev
cd vendor/riscv-isa-sim
mkdir -p build && cd build
../configure
make -j"$(nproc)"
```
The `spike` binary ends up at `vendor/riscv-isa-sim/build/spike` — either
put it on `PATH`, or set `emulator.spike_bin` in your project's
config.yaml to that path. `device-tree-compiler` (`dtc`) is required by
Spike's `./configure`; without it configure fails with `device-tree-compiler
not found`. Boost is used for a couple of optional features (`configure`
still succeeds without it, with an ASIO/Regex warning), but installing it
avoids a slower fallback path in `make`.

`tests/test_generate_golden.py` (this package's own pytest suite) builds
and runs two tiny fixture programs (one C, one asm — see
`tests/fixtures/htif_min/`) through this exact path, and is skipped
automatically if `spike` and the toolchain aren't both available.

## How to create a RISC-V test

- [Creating a test in C](docs/creating-a-c-test.md)
- [Creating a test in ASM](docs/creating-an-asm-test.md)

## Usage

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json
```

See `riscv-tools --help` for the full subcommand list (`write-rom`,
`zero-ram`, `dump-ram`, `program`, `mailbox read|pulse`, `generate-golden`, `run`).

## Development

```bash
uv sync --group dev
uv run pytest
```
