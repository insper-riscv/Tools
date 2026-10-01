# Configuration

Every `riscv-tools` command takes `--config <path>`, pointing at the
**consuming project's own** `config.yaml`: this package never ships a
specific project's values, only defaults (see `riscv_tools/settings.py`
for the merge logic, if you're curious how it works, but you shouldn't
need to read it to use this).

## How it's assembled

Each module owns a small set of defaults in its own `__config__.py`
(e.g. `riscv_tools/mailbox/__config__.py`). `riscv-tools` merges all of
those together, then layers your project's `config.yaml` on top: your
config.yaml always wins. A key with no sane cross-project
default (a memory address, a path inside your repo) is `None` in the
built-in defaults, meaning your `config.yaml` **must** set it: every
such key is marked "**required**" below.

A config file can start from another one with `extends: <path>` (relative
to the file that names it). The file is merged over its base with the same
rules: a section present in both is merged key by key, and any other value
(including a list) replaces the base's. A variant then only lists what
differs, for example a simulation profile that changes `sim:` and keeps
everything else. A chain that loops back is an error.

## Reference

Your `config.yaml` is a nested YAML file with these top-level
sections. Any key you omit falls back to the built-in default shown.

### `toolchain:`

| Key | Default | Used by |
|---|---|---|
| `gcc` | `riscv32-unknown-elf-gcc` | `compiler`, `c_to_asm`, `boot_rom` |
| `objcopy` | `riscv32-unknown-elf-objcopy` | `compiler`, `boot_rom`, `certify`, `golden_generator` |
| `nm` | `riscv32-unknown-elf-nm` | `golden_generator` (`generate-golden`) |
| `libc` | `none` | `compiler`: the C library tests link against. `none` passes `-nostdlib`, so a project supplies what it needs (such as `malloc`) through `paths.syscalls`. `picolibc` passes `--specs=picolibc.specs` (and `-Wl,--no-gc-sections`, see [compiler.md](modules/compiler.md#c-library)) for a GCC configured with picolibc, such as the one Infra's `GCC_SETUP.md` builds |
| `specs` | unset | `compiler`: path (relative to your project root) of a GCC specs file that describes your platform. It includes `picolibc.specs` and adds the memory map (`--defsym=__flash=...`, `__ram=...`) and the crt0 to use, so tests link against the toolchain's own crt0 and `picolibc.ld` and need no `crt0.S` or linker script of yours. Tests are then compiled as hosted programs (`main` may return), and `libc` is ignored. See [compiler.md](modules/compiler.md#platform-specs-file) |

### `isa:`

| Key | Default | Used by |
|---|---|---|
| `base` | `i` | `compiler`, `c_to_asm`: the base ISA letter, always implied even when a test has no `RV32_EXT` header |
| `canonical_order` | `MAFDQLCBJTPVNH` | `compiler`, `c_to_asm`: the letter order a test's `RV32_EXT` extensions get sorted into (see [creating-a-c-test.md](creating-a-c-test.md#header-comments)) |
| `default_ext` | `""` | **not currently read by any code path**: declared here for documentation purposes only; a test with no `RV32_EXT` header always resolves to plain `base`, regardless of what this is set to |

### `paths:` (no generic default; paths inside YOUR repo)

All are **required** except `crt0`, `linker_script` and `sources`.

| Key | Meaning |
|---|---|
| `include_dir` | Passed as `-I` to gcc: where your `rv32_test.h` lives |
| `crt0` | Path to your project's `crt0.S`, compiled+linked into every test. Leave it unset with `toolchain.specs`, which selects the toolchain's crt0 |
| `linker_script` | Path to your project's linker script. Leave it unset with `toolchain.specs`: the GCC driver then adds the toolchain's `picolibc.ld` |
| `sources` | List of source files (relative to the project root) compiled into every test: the platform's own parts of the runtime, such as the `_exit` the toolchain's crt0 ends in. Empty by default |
| `build_dir` | Where compiled artifacts (`.elf`/`.bin`/`.mif`/`.hex`/`manifest.json`) are written |
| `c_dir` | Directory holding one `<name>/src.c` folder per C test (see [creating-a-c-test.md](creating-a-c-test.md)) |
| `asm_dir` | Directory holding one `<name>/src.S` folder per assembly test (see [creating-an-asm-test.md](creating-an-asm-test.md)) |

No `tests_real_dir`/`tests_sim_dir`/`golden_dir` split: every test under `c_dir`/`asm_dir` builds for both `compile --emit mif` (real) and `--emit hex` (sim), regardless of kind: a `RV32_TEST_KIND: memory` test's `results` are checked against golden.json the same way on both (see [creating-a-c-test.md](creating-a-c-test.md#unit-vs-memory-tests): `memory` is `unit`, expanded, mailbox PASS first, then the golden compare). A `memory` test's expected `{byte address: byte value}` map lives at `<name>/golden.json`, next to its `src.c`/`src.S`, not in a separate golden directory.

### `quartus:`

| Key | Default | Used by |
|---|---|---|
| `jtag_device` | **required** | `jtag`: the FPGA's own JTAG IDCODE string. The cable name (`USB-Blaster [...]`) is auto-detected live instead, since it drifts across reboots |
| `project_dir` | **required** | `quartus_program`: path to the Quartus project directory |
| `project_name` | **required** | `quartus_program`: passed to `quartus_sh --flow compile` |
| `sof_file` | **required** | `quartus_program`: path (relative to `project_dir`) to the compiled `.sof`, passed to `quartus_pgm` |
| `rom_mif_target` | **required** | `quartus_program`: path (relative to `project_dir`) the ROM megafunction reads its `init_file` from at compile time |
| `stale_cache_dirs` | `[db, incremental_db, output_files, simulation]` | `quartus_program`: directories (relative to `project_dir`) deleted before every compile, since a ROM `init_file` isn't a tracked project source |
| `rom_mem_instances` | `[0]` | `rom_writer`: In-System Memory Content Editor instance index/indices of the ROM (a list; a project with more than one physical ROM copy, e.g. one per read port if a true dual-port memory isn't available, lists every one, all kept in sync on every write) |
| `ram_mem_instance` | `1` | `ram_zero`, `ram_dump`, `mailbox`: same, for RAM |
| `poll_interval_seconds` | `0.5` | `mailbox` / `orchestrator`: how often to poll the mailbox while waiting on a test |
| `program_wait_seconds` | `15` | `orchestrator`: how long to wait after a full reconfigure (fallback path only) before reading the mailbox |
| `default_timeout_s` | `15` | `compiler` / `orchestrator`: default per-test timeout if a test has no `RV32_TIMEOUT_S` header |

### `memory:` (all **required**, no generic default; depends on your RAM/ROM depth)

| Key | Meaning |
|---|---|
| `ram_base` | RAM's base byte address |
| `mailbox_addr` | Byte address of the PASS/FAIL mailbox word |
| `go_flag_addr` | Byte address of the restart "go" flag word |
| `ram_words` | RAM depth in words: used to zero the whole RAM and to validate a program's `.mif` |
| `rom_base` | Byte address the program image is linked at (0 for a ROM that starts at address 0). The `.mif`/`.hex` of a test linked above 0 gets `rom_base / 4` leading zero words, because the memory is addressed raw, without subtracting a base |
| `rom_words` | ROM depth in words: used to validate/format a program's `.mif` |

### `emulator:`

| Key | Default | Used by |
|---|---|---|
| `spike_bin` | `spike` | `golden_generator`: name/path of the `spike` binary. It must keep its debug module away from address 0 (see [generating-a-golden.md](generating-a-golden.md#requirements)) |
| `timeout_s` | `60` | `golden_generator`: seconds to wait for a test to write `tohost` before failing the generation |
| `tohost_symbol` | `tohost` | `golden_generator`: the HTIF symbol Spike watches for a nonzero write. Standard convention; rarely needs overriding |
| `sources` | `[]` | `golden_generator`, `spike_run`: source files (relative to the project root) linked into the ELF Spike runs and not into the test's own image. For an image that ends in code living elsewhere on the hardware (a boot ROM routine at a fixed address): a stand-in for it, plus the `tohost` and `fromhost` symbols Spike needs. With it empty, Spike runs the test's own image |
| `gcc_flags` | `[]` | `golden_generator`, `spike_run`: extra gcc arguments for that ELF, for example a `-D` that makes the specs file leave the hardware's fixed address out |

### `sim:` (requires the `sim` extra, `uv sync --extra sim`)

| Key | Default | Used by |
|---|---|---|
| `toplevel` | **required** | `sim_runner`: top-level VHDL entity name GHDL elaborates and cocotb attaches to |
| `vhdl_sources` | **required** | `sim_runner`: list of VHDL source paths (relative to your project root), in dependency order |
| `test_module` | **required** | `sim_runner`: your project's own cocotb test module (e.g. `sim.test_c_program`), which knows the DUT's actual signal hierarchy and polls the PASS/FAIL mailbox, the same convention `mailbox` uses for real hardware, just reading simulated signals directly instead of JTAG |
| `ghdl_std` | `08` | `sim_runner`: GHDL `--std=` value. VHDL-2008 (IEEE Std 1076-2008) by default, matching Quartus' own ceiling: Quartus (even the latest, 25.1std) only accepts `VHDL93`/`VHDL_2008` for `VHDL_INPUT_VERSION`, `VHDL_2019` is rejected outright, so this keeps simulation and synthesis on the same dialect |
| `parameters` | `{}` | `sim_runner`: VHDL generics to set on `toplevel` at GHDL's run step, e.g. `{"ROM_FILE": "{hex_path}"}` for a project whose sim-only ROM model loads its program image via a VHDL generic rather than reading `sim_runner`'s own `ROM_HEX` env var. `"{hex_path}"` is substituted with each test's compiled `.hex` path; any other value is passed through as-is (e.g. a fixed memory-depth generic). Empty by default: most toplevels need no generic overrides |
| `hex_format` | `words` | `compile --emit hex`, `sim`, `certify`: layout of the `.hex` a simulation loads. `words` is one 32-bit word per line with leading zero words for a program linked above address 0. `verilog` is what `objcopy -O verilog` writes (see [compiler.md](modules/compiler.md#hex-output)), so the memory model that loads it must handle `@<word address>` lines and four words per line |
| `image` | `hex` | `sim`: which image a simulation loads. `hex` reads `<build_dir>/sim/manifest.json` (from `compile --emit hex`). `mif` reads `<build_dir>/real/manifest.json` (from `compile --emit mif`), the same images the hardware loads, and also builds the boot ROM's `.mif` |
| `ghdl_flags` | `[]` | `sim_runner`: extra GHDL arguments for the analyze, elaborate and run steps, e.g. `["-fsynopsys", "-fexplicit"]` for a vendor simulation library |
| `libraries` | `{}` | `sim_runner`: VHDL libraries analyzed once per `sim` run before `vhdl_sources`, as `{library: [files]}`, e.g. Quartus' `altera_mf` for a toplevel that instantiates its memory IP. Paths are relative to the project root, and `$VAR` or `${VAR}` is replaced from the environment (an unset variable is an error) |
| `run_files` | `{}` | `sim_runner`: files copied into each test's run directory before it runs, as `{file name: source}`, for a design that opens a file by a fixed name, e.g. an `altsyncram` `init_file`. The source takes the same templates as `parameters` |
| `env` | `{}` | `sim_runner`: extra environment variables for your cocotb test module, as `{name: template}`, with the same templates as `parameters` |
| `python_path` | `[]` | `sim_runner`: directories (relative to your project root) put on the module search path of the simulation, so `test_module` can live outside your project, for example in the platform repository a config `extends:` |

The templates of `parameters`, `run_files` and `env` are `{hex_path}` and `{mif_path}` (the test's image, for whichever `image` selects; the other is empty), and `{boot_rom_hex_path}` and `{boot_rom_mif_path}` (the boot ROM's, the same for every test).

### `freq_sweep:` (only needed for `riscv-tools freq-sweep`)

Describes the *shape* of your PLL source's parameter strings: none of
these have a sane cross-project default, since PLL megafunction
instance names/parameter conventions are project-specific. See
[finding-fmax.md](finding-fmax.md) for what this is for and how to run
a sweep.

| Key | Default | Used by |
|---|---|---|
| `pll_file` | **required** | `freq_sweep`/`orchestrator`: path (relative to your project root) to the Verilog/VHDL PLL source rewritten before each candidate frequency's compile |
| `phase_count` | `1` | `freq_sweep`: how many equally phase-spaced clock outputs the PLL instance has (e.g. `3` for a 0/120/240-degree three-way PLL). `1` (a plain single-phase PLL) covers most projects |
| `freq_param_template` | `output_clock_frequency{idx}` | `freq_sweep`: `{idx}`-templated (0-indexed) parameter name searched for and rewritten. Matches Quartus' `altpll` megafunction; override for a different megafunction/instance naming |
| `phase_param_template` | `phase_shift{idx}` | `freq_sweep`: same idea, for the phase-offset parameter |
| `freq_unit` | `MHz` | `freq_sweep`: literal unit suffix written after the frequency value, e.g. `.output_clock_frequency0("10.000000 MHz")`. Only controls the string suffix: the period/phase-offset math itself always assumes MHz-in/ps-out, matching Quartus' `altpll` convention |
| `phase_unit` | `ps` | `freq_sweep`: same idea, for the phase value |

`riscv-tools freq-sweep <mif> --golden <golden.json>` reuses
`quartus.*`/`memory.ram_base` from the `quartus:`/`memory:` sections
above (same fields `full_reconfigure`/`run_one` use) for the actual
compile+program+dump+compare at each candidate frequency. See
`orchestrator.run_freq_sweep_linear`/`run_freq_sweep_binary`.

### `run_log:`

Where `run`/`sim`/`certify` each keep their own persistent, gitignored
log history. See `run_log.start`.

| Key | Default | Used by |
|---|---|---|
| `logs_dir` | `logs` | `cli` (cmd_run/cmd_sim/cmd_certify): path (relative to your project root) holding one subdirectory per subcommand (`real`/`sim`/`certification`), each with a `latest.log` for the run in progress plus every prior run archived under its own start timestamp. Add `logs/` to your project's `.gitignore` |

## Example

A minimal `config.yaml` covering every required key:

```yaml
toolchain:
  gcc: riscv32-unknown-elf-gcc
  objcopy: riscv32-unknown-elf-objcopy

paths:
  include_dir: tools/riscv_build/include
  crt0: tools/riscv_build/crt0.S
  linker_script: tools/riscv_build/link.ld
  build_dir: build
  c_dir: c
  asm_dir: asm

memory:
  ram_base: 0x00000000
  ram_words: 4096
  rom_words: 8192
  mailbox_addr: 0x00003FFC
  go_flag_addr: 0x00003FF8

quartus:
  jtag_device: "@1: 5CE(BA4|FA4) (0x02B050DD)"
  project_dir: ../RV32IM/tests/FPGA/core/quartus
  project_name: core_fpga_test
  sof_file: output_files/core_fpga_test.sof
  rom_mif_target: init.mif
```

Everything else (`isa.*`, `quartus.rom_mem_instances`/`ram_mem_instance`/
`poll_interval_seconds`/`program_wait_seconds`/`default_timeout_s`,
`emulator.*`) is optional: override only what doesn't match your setup.

`sim:` isn't in this minimal example at all: the real-hardware and
golden-generation paths never touch it, so it's only needed once you
actually use `sim_runner`/`riscv-tools sim`, at which point
`toplevel`/`vhdl_sources`/`test_module` become required (see the
Configuration reference above).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
