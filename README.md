# riscv-tools

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
| `orchestrator`       | Composes the above into a full test-suite run                |

## Vendored references (git submodules)

| Path                     | Points at                                              | Why                                                          |
|---------------------------|--------------------------------------------------------|----------------------------------------------------------------|
| `vendor/riscv-gnu-toolchain` | [riscv-collab/riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) | The GCC cross-toolchain `compiler` builds test programs with |
| `vendor/riscv-isa-sim`    | [riscv-software-src/riscv-isa-sim](https://github.com/riscv-software-src/riscv-isa-sim) (Spike, RISC-V International's reference simulator) | Golden-reference source for `golden_generator` (see below) |

Clone with `git clone --recurse-submodules`, or after a plain clone:
`git submodule update --init --recursive`.

### `golden_generator`

Runs a compiled ELF under Spike, using its interactive debug console
(`-d`) to stop the instant the program writes its HTIF "done" signal
to `tohost_symbol` (default `tohost` — the standard Spike/riscv-tests
convention; see the consuming project's link.ld/crt0.S, which defines
`tohost`/`fromhost` and translates RV32_PASS/RV32_FAIL's mailbox value
into it), then snapshots the given byte range of RAM into a golden
JSON in the same format `mem_validator.compare` expects.

`golden_generator.setup()`/`update()` manage the `spike` binary itself
so nobody has to remember `./configure && make` by hand:

```python
from riscv_tools import golden_generator

golden_generator.setup()   # build vendor/riscv-isa-sim if nothing usable exists yet
golden_generator.update()  # rebuild it if the submodule pointer has moved since
```

- `setup(spike_bin="spike")` — if `spike_bin` already resolves to something
  runnable (on `PATH`, or an existing file — e.g. a system package), it's
  left alone and returned as-is. Otherwise it checks `device-tree-compiler`
  (`dtc`) is installed — the one dependency Spike's `./configure` hard-fails
  without (`sudo apt-get install device-tree-compiler`; Boost is also used
  but is optional, `configure` degrades gracefully without it) — and builds
  `vendor/riscv-isa-sim` if `build/spike` doesn't exist yet. Raises
  `FileNotFoundError` if the submodule itself was never checked out (run
  `git submodule update --init --recursive` first).
- `update()` — rebuilds only if `vendor/riscv-isa-sim`'s currently checked-out
  commit has moved since the last build (tracked via a marker file next to
  the binary), e.g. after pulling a newer submodule pin. Returns `False`
  without building anything if nothing's been built yet — call `setup()`
  first.

The `spike` binary ends up at `vendor/riscv-isa-sim/build/spike` — either
put it on `PATH`, or set `emulator.spike_bin` in your project's config.yaml
to that path (setup()/update() honor whatever `spike_bin` resolves).

#### `RISCV_ISA_SIM_DIR` — pointing at a cache directory instead

This repo's own `vendor/riscv-isa-sim` isn't the only place a
riscv-isa-sim checkout can live. Set the `RISCV_ISA_SIM_DIR`
environment variable to make `setup()`/`update()` operate on a
different directory entirely — e.g. in CI, point it at a persistent
cache (`actions/cache`) instead of this repo's own submodule path, so
a fresh checkout of `riscv-tools` doesn't have to re-clone and rebuild
Spike from scratch (and burn CI minutes/bandwidth) on every run:

```yaml
# GitHub Actions example
- uses: actions/cache@v4
  with:
    path: ${{ runner.temp }}/riscv-isa-sim
    key: riscv-isa-sim-${{ <pinned commit/version> }}
- run: uv run python -c "from riscv_tools import golden_generator; golden_generator.setup()"
  env:
    RISCV_ISA_SIM_DIR: ${{ runner.temp }}/riscv-isa-sim
```

On a cache miss (directory empty or not yet a checkout), `setup()`
clones riscv-isa-sim there itself, checking out the same commit this
repo's own `vendor/riscv-isa-sim` submodule is pinned to (so the
override still runs the exact Spike version this repo vendors, not
just whatever the remote's default branch happens to be at clone
time). This repo's own submodule is never auto-cloned into this way —
only an override directory is, since the submodule itself is meant to
be populated with `git submodule update --init`.

`tests/test_generate_golden.py` (this package's own pytest suite) builds
and runs two tiny fixture programs (one C, one asm — see
`tests/fixtures/htif_min/`) through this exact path, and is skipped
automatically if `spike` and the toolchain aren't both available.

## Docs

- [Configuration reference](docs/configuration.md)
- [Creating a test in C](docs/creating-a-c-test.md)
- [Creating a test in ASM](docs/creating-an-asm-test.md)
- [Generating a golden JSON via Spike](docs/generating-a-golden.md)

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
`zero-ram`, `dump-ram`, `program`, `mailbox read|pulse`, `generate-header`,
`generate-golden`, `run`).

## Development

```bash
uv sync --group dev
uv run pytest
```
