# Configuration

Every `riscv-tools` command takes `--config <path>`, pointing at the
**consuming project's own** `config.yaml` — this package never ships a
specific project's values, only defaults (see `riscv_tools/settings.py`
for the merge logic, if you're curious how it works, but you shouldn't
need to read it to use this).

## How it's assembled

Each module owns a small set of defaults in its own `__config__.py`
(e.g. `riscv_tools/mailbox/__config__.py`). `riscv-tools` merges all of
those together, then layers your project's `config.yaml` on top —
**your config.yaml always wins**. A key with no sane cross-project
default (a memory address, a path inside your repo) is `None` in the
built-in defaults, meaning your `config.yaml` **must** set it — every
such key is marked "**required**" below.

## Reference

Your `config.yaml` is a nested YAML file with these top-level
sections. Any key you omit falls back to the built-in default shown.

### `toolchain:`

| Key | Default | Used by |
|---|---|---|
| `gcc` | `riscv32-unknown-elf-gcc` | `compiler`, `c_to_asm` |
| `objcopy` | `riscv32-unknown-elf-objcopy` | `compiler` |
| `nm` | `riscv32-unknown-elf-nm` | `golden_generator` (`generate-golden`) |

### `isa:`

| Key | Default | Used by |
|---|---|---|
| `base` | `i` | `compiler`, `c_to_asm` — the base ISA letter, always implied even when a test has no `RV32_EXT` header |
| `canonical_order` | `MAFDQLCBJTPVNH` | `compiler`, `c_to_asm` — the letter order a test's `RV32_EXT` extensions get sorted into (see [creating-a-c-test.md](creating-a-c-test.md#header-comments)) |
| `default_ext` | `""` | **not currently read by any code path** — declared here for documentation purposes only; a test with no `RV32_EXT` header always resolves to plain `base`, regardless of what this is set to |

### `paths:` — all **required**, no generic default (paths inside YOUR repo)

| Key | Meaning |
|---|---|
| `include_dir` | Passed as `-I` to gcc — where your `rv32_test.h` lives |
| `crt0` | Path to your project's `crt0.S`, compiled+linked into every test |
| `linker_script` | Path to your project's linker script |
| `build_dir` | Where compiled artifacts (`.elf`/`.bin`/`.mif`/`.hex`/`manifest.json`) are written |
| `tests_real_dir` | Directory `compile --emit mif` / `--emit asm` scans for `.c`/`.S` |
| `tests_sim_dir` | Directory `compile --emit hex` scans for `.c`/`.S` |
| `golden_dir` | Directory holding golden `.json` files for `RV32_TEST_KIND: memory` tests |

### `quartus:`

| Key | Default | Used by |
|---|---|---|
| `jtag_device` | **required** | `jtag` — the FPGA's own JTAG IDCODE string. The cable name (`USB-Blaster [...]`) is auto-detected live instead, since it drifts across reboots |
| `project_dir` | **required** | `quartus_program` — path to the Quartus project directory |
| `project_name` | **required** | `quartus_program` — passed to `quartus_sh --flow compile` |
| `sof_file` | **required** | `quartus_program` — path (relative to `project_dir`) to the compiled `.sof`, passed to `quartus_pgm` |
| `rom_mif_target` | **required** | `quartus_program` — path (relative to `project_dir`) the ROM megafunction reads its `init_file` from at compile time |
| `stale_cache_dirs` | `[db, incremental_db, output_files, simulation]` | `quartus_program` — directories (relative to `project_dir`) deleted before every compile, since a ROM `init_file` isn't a tracked project source |
| `rom_mem_instance` | `0` | `rom_writer` — In-System Memory Content Editor instance index of the ROM |
| `ram_mem_instance` | `1` | `ram_zero`, `ram_dump`, `mailbox` — same, for RAM |
| `poll_interval_seconds` | `0.5` | `mailbox` / `orchestrator` — how often to poll the mailbox while waiting on a test |
| `program_wait_seconds` | `15` | `orchestrator` — how long to wait after a full reconfigure (fallback path only) before reading the mailbox |
| `default_timeout_s` | `15` | `compiler` / `orchestrator` — default per-test timeout if a test has no `RV32_TIMEOUT_S` header |

### `memory:` — all **required**, no generic default (depends on your RAM/ROM depth)

| Key | Meaning |
|---|---|
| `ram_base` | RAM's base byte address |
| `mailbox_addr` | Byte address of the PASS/FAIL mailbox word |
| `go_flag_addr` | Byte address of the restart "go" flag word |
| `ram_words` | RAM depth in words — used to zero the whole RAM and to validate a program's `.mif` |
| `rom_words` | ROM depth in words — used to validate/format a program's `.mif` |

### `emulator:`

| Key | Default | Used by |
|---|---|---|
| `spike_bin` | `spike` | `golden_generator` — name/path of the built `spike` binary. No sane default across workstations if it's not on `PATH`; point this at `vendor/riscv-isa-sim/build/spike` if you haven't installed it elsewhere |
| `tohost_symbol` | `tohost` | `golden_generator` — the HTIF symbol Spike watches for a nonzero write. Standard convention; rarely needs overriding |

### `sim:` — needs the `sim` extra (`uv sync --extra sim`)

| Key | Default | Used by |
|---|---|---|
| `toplevel` | **required** | `sim_runner` — top-level VHDL entity name GHDL elaborates and cocotb attaches to |
| `vhdl_sources` | **required** | `sim_runner` — list of VHDL source paths (relative to your project root), in dependency order |
| `test_module` | **required** | `sim_runner` — your project's own cocotb test module (e.g. `sim.test_c_program`) — it knows the DUT's actual signal hierarchy and polls the PASS/FAIL mailbox, the same convention `mailbox` uses for real hardware, just reading simulated signals directly instead of JTAG |
| `ghdl_std` | `08` | `sim_runner` — GHDL `--std=` value. VHDL-2008 (IEEE Std 1076-2008) by default, matching Quartus' own ceiling — Quartus (even the latest, 25.1std) only accepts `VHDL93`/`VHDL_2008` for `VHDL_INPUT_VERSION`, `VHDL_2019` is rejected outright, so this keeps simulation and synthesis on the same dialect |

### `freq_sweep:` — only needed for `riscv-tools freq-sweep`

Describes the *shape* of your PLL source's parameter strings — none of
these have a sane cross-project default, since PLL megafunction
instance names/parameter conventions are project-specific. See
[finding-fmax.md](finding-fmax.md) for what this is for and how to run
a sweep.

| Key | Default | Used by |
|---|---|---|
| `pll_file` | **required** | `freq_sweep`/`orchestrator` — path (relative to your project root) to the Verilog/VHDL PLL source rewritten before each candidate frequency's compile |
| `phase_count` | `1` | `freq_sweep` — how many equally phase-spaced clock outputs the PLL instance has (e.g. `3` for a 0/120/240-degree three-way PLL). `1` (a plain single-phase PLL) covers most projects |
| `freq_param_template` | `output_clock_frequency{idx}` | `freq_sweep` — `{idx}`-templated (0-indexed) parameter name searched for and rewritten. Matches Quartus' `altpll` megafunction; override for a different megafunction/instance naming |
| `phase_param_template` | `phase_shift{idx}` | `freq_sweep` — same idea, for the phase-offset parameter |
| `freq_unit` | `MHz` | `freq_sweep` — literal unit suffix written after the frequency value, e.g. `.output_clock_frequency0("10.000000 MHz")`. Only controls the string suffix — the period/phase-offset math itself always assumes MHz-in/ps-out, matching Quartus' `altpll` convention |
| `phase_unit` | `ps` | `freq_sweep` — same idea, for the phase value |

`riscv-tools freq-sweep <mif> --golden <golden.json>` reuses
`quartus.*`/`memory.ram_base` from the `quartus:`/`memory:` sections
above (same fields `full_reconfigure`/`run_one` use) for the actual
compile+program+dump+compare at each candidate frequency — see
`orchestrator.run_freq_sweep_linear`/`run_freq_sweep_binary`.

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
  tests_real_dir: tests/c/real
  tests_sim_dir: tests/c/sim
  golden_dir: tests/c/real/golden

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

Everything else (`isa.*`, `quartus.rom_mem_instance`/`ram_mem_instance`/
`poll_interval_seconds`/`program_wait_seconds`/`default_timeout_s`,
`emulator.*`) is optional — override only what doesn't match your setup.

`sim:` isn't in this minimal example at all — the real-hardware and
golden-generation paths never touch it, so it's only needed once you
actually use `sim_runner`/`riscv-tools sim`, at which point
`toplevel`/`vhdl_sources`/`test_module` become required (see the
Configuration reference above).
