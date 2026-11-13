# `memory_map`

Checks that every hand-written copy of a platform's memory map agrees. The map (region bases and sizes, the words the boot memory reserves at the top of RAM, the boot entry points, the peripheral windows) is needed in many files: linker flags, boot memory, C runtime, VHDL, Quartus IPs, the project's `config.yaml`. Each copy is only noticed when it disagrees on the board. One YAML file, the platform, is the source of truth; this module reads each copy and reports every disagreement.

## 1. Configuration

No `config.yaml` section: the platform file is self-describing and is passed with `--platform`.

```yaml
regions:                      # the map itself
  - {name: BOOT_MEMORY, base: 0x0,    size: 2K,   kind: rom, exec: true}
  - {name: FLASH,    base: 0x800,  size: 30K,  kind: rom, exec: true}
  - {name: RAM,      base: 0x8000, size: 160K, kind: ram}
reserved:                     # words at the top of RAM (inside a ram region)
  stdout:  {base: 0x2FBE0, size: 1K+8}
  tohost:  {base: 0x2FFF0, size: 16}
boot: {entry: 0x800, wait_restart: 0x100}
peripherals:                  # absolute base and size in bytes of registers
  - {name: GPIO, base: 0xA0000000, size: 64}
checks:                       # where each copy lives
  - name: config ram base
    file: tools/riscv_build/config.yaml      # relative to --root
    yaml: memory.ram_base                     # dotted path, or:
    expect: RAM.base
  - name: specs ram size
    file: rv32im-fpga.specs
    pattern: '--defsym=__ram_size=(\S+)'      # one capture group
    expect: RAM.size - (RAM.end - stdout.base)
```

- **Symbols** in `expect`: `<REGION>.base|size|end|words`, `<reserved>.base|size|end`, `boot.entry|wait_restart`, `<PERIPHERAL>.base|size|window|index`.
- **Numbers** accept hexadecimal, decimal, VHDL-based (`16#800#`), suffixes (`30K`, `0x800u`) and `+ - * /` (exact division), plus `log2()` (exact) and `clog2()` (rounded up, for address widths).
- A check whose pattern matches nothing **fails** ("the copy moved"); `optional: true` skips a file that is absent. A pattern with several matches must agree at every match.
- Before the copies are read the map itself is validated: regions and reserved words do not overlap, reserved words sit inside a RAM region, `boot.entry` is in an executable region, `boot.wait_restart` is in the first region, the window of each peripheral is aligned, fits the space and overlaps neither another window nor a region, and the BOOT_MEMORY, the FLASH and the RAM are in order (see section 9).

## 2. Generating the files of the map

The same YAML can say, in the `generate` section, which files come out of it, so no copy of the map has to be written by hand.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `specs` | GCC specs file | The linker flags: `__flash`, `__flash_size`, `__ram`, `__ram_size` and `rv32_wait_restart`. The RAM of the linker ends where the reserved word `ram_limit` begins |
| `boot_ld` | Boot memory linker script | The `boot_memory` memory in the first region and the `RESET_RESERVED` from `boot.wait_restart` |
| `runtime` | Runtime header (`.h`, also included by `.S`) | `RV32_RAM_END` (end of the `ram` region), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` and `RV32_STDOUT_BASE`, from the `reserved` ranges the map has, `RV32_BOOT_ENTRY` (where the boot memory jumps) and `RV32_<NAME>_BASE` for each peripheral; the runtime in C and assembly (`_exit.c`, `stdio.c`, `boot_memory.S`, `spike_exit.S`) uses these names instead of hand-written addresses |
| `config_pkg` | VHDL package of the constants of the platform | The `config_pkg` of section 10, next to the map package |
| `vhdl` | VHDL package | The constants `BOOT_MEMORY_BITS`, `BOOT_MEMORY_SIZE_BYTES`, `FLASH_BASE_KIB`, `FLASH_END_KIB`, `FLASH_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES` and `RAM_LAST_PAGE`, the `FLASH_ON_BUS` and `RAM_ON_BUS` flags (from `generate.vhdl` or from the `memory` section), the cache constants of the `memory` section, `PERIPH_COUNT`, `STRICT_PERIPH`, the `PERIPH_BASES` and `PERIPH_MASKS` tables and, for each peripheral, `<NAME>_BASE` and `<NAME>_INDEX` |

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout}
  boot_ld: {path: runtime/boot_memory.ld}
  runtime: {path: runtime/memory_map.h, ram: RAM}
  vhdl:
    path: rtl/map_pkg.vhd
    package: map_pkg
    rom: FLASH
    ram: RAM
```

`FLASH_STORAGE_BYTES` and `RAM_STORAGE_BYTES` are the smallest power of two that covers the end of the FLASH and the size of the RAM, and `RAM_LAST_PAGE` is bits 31:12 of the last 4 KiB page of the RAM.

The limits of the VHDL package are the generics of the `core`, in KiB, so an address that is not a multiple of 1 KiB is an error. The map is validated before generating, and an inconsistent map generates nothing.

```bash
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <project> generate-memory-map --platform src/platform/platform.yaml --check
```

With `--check` nothing is written, and the command exits with status 1 when a file is missing or differs from what the map would generate. It needs no `--config`.

## 3. The FLASH banks

The `flash` section of the `platform.yaml` splits the FLASH into banks, each holding an image in the format of [`flash_image`](flash_image.md), for the program update in the field.

```yaml
flash:
  region: FLASH
  banks:
    - {name: A, base: 0x1000,  size: 124K}
    - {name: B, base: 0x20000, size: 128K}
generate:
  bank_specs:
    - {path: runtime/bank-b.specs, rom: BANK_B_PAYLOAD, ram: RAM, ram_limit: stdout}
  banks_h: {path: runtime/flash_banks.h}
```

Each bank starts with a 256-byte header page, so its program is linked from `base + 256`. For the bank `A` the map gains the symbols `BANK_A.base|size|end|words` and `BANK_A_PAYLOAD.base|size|end|words` (the part after the header), which serve as `expect` in the checks and as `rom` in the specs sections.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `bank_specs` | List of GCC specs files, one per entry | Like `specs`, with `__flash` and `__flash_size` of the region chosen in `rom`, usually `BANK_<name>_PAYLOAD` |
| `banks_h` | Header (`.h`, also included by `.S`) | `RV32_IMAGE_MAGIC`, `RV32_IMAGE_HEADER_SIZE` and, for each bank, `RV32_BANK_<NAME>_BASE`, `_SIZE` and `_ENTRY` (where the program starts) |

The map refuses banks that are not aligned to the 4 KiB sector, that leave no room for a program after the header, that leave the region named in `flash.region`, that overlap or that repeat a name.

## 4. The core of the platform

The `platform.yaml` has no profile name. It describes the core in the `core` block, and the Tools infer from it the profile of the specification of the Core, which the platform locates in `profiles:`, a path relative to the `platform.yaml` (the `profiles/matrix.yaml` of the Core).

```yaml
core:
  type: 32          # 32 or 64 (RV32 or RV64)
  base: I           # I or E (32 or 16 registers)
  extensions:       # or `extensions: []`
    - M
    - Zicsr
    - Zicclsm
    - Zicntr
    - Zihpm
    - Zifencei
    - Zimop
    - Zicond
    - Zihintntl
    - Zihintpause
    - Interrupts
    - Sscofpmf
    - AccessFaults
profiles: ../../../Core/profiles/matrix.yaml
```

The keys are `type`, `base` and `extensions`, in lower case, and the names of the extensions are not case sensitive. The module `riscv_tools.memory_map.core_profile` does the inference.

| Rule | Effect |
| :--- | :--- |
| Extensions of the matrix (`M`, `Zmmul`, `Zicsr`, `Zicntr`, `Zihpm`, `Zifencei`, `Zicclsm`, `Zimop`, `Zicond`) | Pick the profile `rv<type><base>` with the extensions in the canonical order of the name, such as `rv32im_zicclsm_zicntr_zihpm_zifencei` |
| Extensions the matrix does not list (`Zihintntl`, `Zihintpause`, `Interrupts`, `Sscofpmf`, `AccessFaults`; also `Zimop` and `Zicond` if the matrix lacks them) | They are the extras, turned on over the profile |
| Normalization | `M` implies `Zmmul`, and `Zicntr` and `Zihpm` imply `Zicsr`. Listing `Zicsr` beside `Zicntr` or `Zihpm` is accepted, and the inferred name does not cite it |
| Error | An unknown or repeated extension; a combination the matrix refuses (`M` with `Zmmul`); `type: 64` without an `rv64` base in the matrix; `isa` in place of `base` ("the key is called base"); an unknown or missing key |
| Migration | `profile:` and `extras:` are refused, with the message of the block that replaces them: `profile: rv32em_zicntr` becomes `type` 32, `base` E and `extensions` M, Zicntr |

The profile gives:

| Output | Content |
| :--- | :--- |
| VHDL package | `IS_E` (true on the RV32E) and one boolean `HAS_<EXTENSION>` per extension of the core (`HAS_M`, `HAS_ZMMUL`, `HAS_ZICSR`, `HAS_ZICNTR`, `HAS_ZIHPM`, `HAS_ZIMOP`, `HAS_ZICOND`, `HAS_ZIHINTNTL`, `HAS_ZIHINTPAUSE`, `HAS_ZIFENCEI`, `HAS_ZICCLSM`, `HAS_INTERRUPTS`, `HAS_SSCOFPMF`, `HAS_ACCESS_FAULTS`) |
| `config.yaml` | `isa.base`, which picks `-march` and `-mabi` of the programs and of the boot memory (`rv32e` with `ilp32e`, the others with `ilp32`), and the `sim.config_pkg`, the text of the `config_pkg` of the profile that the runner compiles in place of the `config_pkg.vhd` of the sources (the base and the extensions of the core are constants of that package, not generics of the top) |

`--profile NAME`, a global option of `riscv-tools`, replaces only the profile part of the matrix, without editing the platform, to run the same platform over many profiles in a test matrix. The extensions the matrix does not list stay on. It applies to `generate-memory-map` (writes the package of that profile), to `platform sync` and to every command that reads the configuration. A name that the specification does not list is rejected before anything runs.

`Sscofpmf` needs `Zihpm` and `Interrupts`, and generation fails without them. Every switch that neither the profile nor the extras turn on comes out `false` in the package. A platform without `profiles:` keeps only the profile name, in the order of the matrix of the Core.

```bash
uv run riscv-tools --root <project> --profile rv32em_zicsr generate-memory-map --platform src/platform/platform.yaml
```

## 5. The interrupts of the platform

A platform with the machine interrupts turns on the `Interrupts` extension of `core` (the core enables them only with `Zicsr`), lists the `CLINT` and, for the external lines, the `EXT_IRQ` among the `peripherals`, and describes the clock in the `interrupts` section.

```yaml
core: {type: 32, base: I, extensions: [Zicsr, Interrupts]}
peripherals:
  - {name: CLINT,   base: 0xE0000000, size: 64K}
  - {name: EXT_IRQ, base: 0xF0000000, size: 16}
interrupts:
  clock_hz: 50000000   # clock of the domain of the core and the CLINT
  mtime_hz: 1000000    # rate at which the mtime of the CLINT counts
```

The `mtime` of the CLINT is a counter of its own, set by `mtime_hz`, and it is independent of the CSR `time` of Zicntr, which the core serves. With `clocks.core` in the platform `clock_hz` is left out and is the core clock rounded to a whole number of cycles per increment; when written, it must be that value. `clock_hz` must be a multiple of `mtime_hz`, the profile must turn on `has_interrupts`, and the `peripherals` list must have the `CLINT`; the absence of any of them is an error before generating and in `check-memory-map`.

| Output | Constants |
| :--- | :--- |
| VHDL package (`vhdl`) | `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES` (clock cycles per increment of `mtime`, the `tick_cycles` generic of the CLINT), besides `CLINT_BASE`, `CLINT_INDEX`, `EXT_IRQ_BASE` and `EXT_IRQ_INDEX` |
| Runtime header (`runtime`) | `RV32_CLINT_BASE`, `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` and `RV32_MTIME_HZ`, which `FreeRTOSConfig.h` uses in `configMTIMECMP_BASE_ADDRESS`, `configMTIME_BASE_ADDRESS` and `configCPU_CLOCK_HZ` |

The offsets of the registers inside the 64 KiB window of the CLINT follow the SiFive layout that the FreeRTOS port expects.

### 5.1. PLIC and interrupt sources

A platform with a PLIC lists it in `peripherals` with a `size` (the window it decodes, a power of two of at least `0x200008` bytes) and describes it in `interrupts`.

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, size: 4M}
interrupts:
  plic: {priority_bits: 3}
  sources:                 # ids of the lines wired to the PLIC
    - {name: UART, id: 1}
    - {name: TIMER, id: 5}
```

| Output | Constants |
| :--- | :--- |
| VHDL package (`vhdl`) | `PLIC_N_SOURCES` (the largest id), `PLIC_PRIORITY_BITS`, `PLIC_ADDR_WIDTH` (the window in words, as a power of two) and `IRQ_<NAME>` per source |
| Runtime header (`runtime`) | `RV32_PLIC_PRIORITY`, `RV32_PLIC_PENDING`, `RV32_PLIC_ENABLE`, `RV32_PLIC_THRESHOLD`, `RV32_PLIC_CLAIM` and `RV32_IRQ_<NAME>` per source |

Repeated ids, ids outside 1 to 1023, `priority_bits` outside 1 to 32 and a window with no `size` or an invalid one are errors before generating.

$$ \text{msip} = base, \quad \text{mtimecmp} = base + \texttt{0x4000}, \quad \text{mtime} = base + \texttt{0xBFF8} $$

## 6. The clocks of the platform

The `clocks` section of the `platform.yaml` is the single source of the frequencies: the PLL, the `.sdc` and the VHDL package come from it (see [pll_generator](pll_generator.md)). The memory map reads the SDRAM controller clock and the core clock from it.

```yaml
clocks:
  core:  {mhz: 76.923077, phase_ps: 7500}  # core clock
  mem:   {mhz: 100}                        # SDRAM controller clock
```

| Output | Content |
| :--- | :--- |
| VHDL package (`vhdl`) | `SDRAM_CLOCK_HZ` and `SDRAM_TCK_PS` from `clocks.mem`, the period in picoseconds with which the controller and the chip model convert the chip timings into cycles |
| `checks` symbols | `CLOCKS.mem_mhz`, `CLOCKS.mem_tck_ps`, `CLOCKS.core_mhz` (rounded) and `CLOCKS.core_phase_ps` |

Every declared clock needs a positive `mhz`, and `clocks.mem` must have a whole period in picoseconds; a missing or bad value is an error before generating and in `check-memory-map`. The phase of the `DRAM_CLK` pin belongs to the board (`memories.sdram.clk_phase_ps` of the `board.yaml`). The `interrupts` section names `INTERRUPTS.tick_cycles`, the clock cycles per `mtime` tick, for the checks.

## 7. The memories and caches of the platform

The `memory` section of the `platform.yaml` picks four independent things per platform, and 9 of the 16 combinations are valid. No field has a default, so forgetting one is an error and the platform never builds a combination other than the one its author wrote. A platform without the section keeps generating the package it generated before.

```yaml
memory:
  rom:    {external: true}
  ram:    {external: true}
  icache: {enabled: true, size_bits: 4096}
  dcache: {enabled: true, size_bits: 4096}
```

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `rom.external` | boolean | The FLASH sits outside the chip |
| `ram.external` | boolean | The RAM sits outside the chip |
| `icache.enabled` | boolean | An instruction cache exists |
| `icache.size_bits` | power of two, at least 256 | Size of the instruction cache in bits; required only with `enabled: true` |
| `dcache.enabled` | boolean | A data cache exists |
| `dcache.size_bits` | power of two, at least 256 | Size of the data cache in bits; required only with `enabled: true` |

The `rom_external` and `ram_external` fields of `generate.vhdl` are derived from the `memory` section, and having both together is an error.

### 7.1. Generated constants

The VHDL package gains the constants below. `FLASH_ON_BUS` and `RAM_ON_BUS` say that the memory is reached through the bus, inside or outside the chip, and not through the direct port of the core. A cache only exists over a memory on the bus.

| Constant | Type | Value |
| :--- | :--- | :--- |
| `FLASH_ON_BUS` | boolean | `memory.rom.external` |
| `RAM_ON_BUS` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, or 256 without the cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, or 256 without the cache |
| `I_CACHE_WINDOW_BITS`, `D_CACHE_WINDOW_BITS` | natural | Smallest width from 26 to 29 such that the FLASH and the RAM each fit one aligned window of $2^{\text{width}}$ bytes (26 is 64 MiB, 27 is 128 MiB), derived from the regions; both have the same value |

In the `config.yaml` the values arrive as `sim.parameters` named `ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` and `DCACHE_SIZE_BITS`, and `CACHE_WINDOW_BITS` only when it is above 26, and the simulation top must declare the matching generics. Without `config.addr_widths` in the platform, the address widths come from the choice, and the `boot_memory` and each internal memory come out, since an external memory is a chip that the top sizes by itself. With `config.addr_widths` listed, the list wins.

### 7.2. Validation

| Rule | Condition | Result |
| :--- | :--- | :--- |
| V1 | The four booleans exist and there is no unknown key | Error |
| V2 | `size_bits` is a power of two and at least 256 | Error |
| V3 | With any cache, the FLASH and the RAM each fit one aligned window of up to 512 MiB (the tag of the caches keeps the bits below the window) | Error |
| V4 | With the FLASH on the bus, its size fits the 1024 KiB window of the router | Error |
| V5 | An `exec` region in the RAM needs the RAM and the FLASH on the bus | Error |
| V7 | An `exec` region in the RAM behind the instruction cache needs Zifencei in the profile | Error |
| V9 | A platform with peripherals | Note |
| V10 | With any cache, `reserved.fromhost` exists and sits in the last 4 KiB page of the RAM, the one the cache skips | Error |
| V-C1 | `icache.enabled` with `rom.external: false`: the instruction cache needs `FLASH_ON_BUS` | Error |
| V-C2 | `dcache.enabled` with `ram.external: false`: the data cache needs `RAM_ON_BUS` | Error |

Of the 16 combinations of `rom.external`, `ram.external`, `icache.enabled` and `dcache.enabled`, 9 are valid and 7 are refused by V-C1 and V-C2. The FLASH on the bus without an instruction cache is valid. The note comes out as `NOTE` on the standard error of `generate-memory-map`, and the errors stop the generation.

### 7.3. The `--memory` option

`--memory`, a global option of `riscv-tools`, replaces fields of the `memory` section without editing the platform, to run the same platform over the combinations. The value is a comma list of `key=value` pairs.

| Key | Values |
| :--- | :--- |
| `rom`, `ram` | `int` or `ext` |
| `icache`, `dcache` | `on`, `off` or a size in bits, which turns the cache on |

A key that is not named keeps the choice of the platform, and a platform without the `memory` section needs the four keys. `on` without a size uses the `size_bits` of the platform, or 4096 if it has none. A malformed value is rejected before anything runs.

```bash
uv run riscv-tools --root <project> --memory rom=ext,ram=int,icache=on,dcache=off generate-memory-map --platform src/platform/platform.yaml
```

## 8. Reading the configuration from the map

A project `config.yaml` declares `memory_map: <path of the platform.yaml>`, and the configuration loader replaces the keys the map fixes with the map's own: `isa.base`, `memory.boot_memory_base`, `boot_memory_words`, `rom_base`, `rom_words`, `ram_base`, `ram_words`, `tohost_addr`, `fromhost_addr` `sim.env.TOHOST_ADDR`, `sim.env.STDOUT_ADDR` (the testbench reads the address from the environment) and, for the memories the `config.addr_widths` section of the map lists, `sim.parameters.<memory>_addr_width`. What the map fixes wins over what the file or its `extends` say, so no address or size is written twice.

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_memory, rom, ram]
```

`platform sync` writes the values already replaced, so Tests and Certification do not need the `platform.yaml`.

## 9. The width of the physical address

### 9.1. The `address_bits` field

The top-level `address_bits` field of the `platform.yaml` is an integer from 16 to `XLEN` (the `type` of the `core` block: 32 or 64) with the width of the physical address. When absent it is 32, and no platform written for 32 bits needs to change. A `type: 64` turns on `IS_64` of the `config_pkg` and accepts 16 to 64 bits, including fewer than 64.

```yaml
address_bits: 24      # optional, 32 by default
core: {type: 32, base: I, extensions: [M]}
peripherals:          # absolute base and size in bytes of registers
  - {name: UART, base: 0xC00000, size: 16}
```

### 9.2. The window of each peripheral

The core only knows the BOOT_MEMORY, the FLASH and the RAM, and every address outside them leaves through the external port. The interconnect decodes the peripherals from a table with one window per peripheral. The window is derived from the `size`.

$$ \text{window} = \max\left(16,\ 2^{\lceil \log_2 \text{size} \rceil}\right), \quad \text{peripheral } i \text{ answers when } (\text{address} \wedge \text{mask}_i) = \text{base}_i $$

The mask of a peripheral has the address bits above its window, so a 64 KiB peripheral with 32 address bits has the mask `0xFFFF0000`. There is no fixed peripheral window, no cap on the count and no slot identifier, and the position of a peripheral in the `peripherals` list is its `<NAME>_INDEX` in the tables.

### 9.3. Validations

Each validation is a `platform` problem before generation and in `check-memory-map`, with the field name and the cause in the message.

| Rule | Rejection condition |
| :--- | :--- |
| V-A1 | `address_bits` is not an integer or is outside 16 to 64 |
| V-A2 | `address_bits` greater than `XLEN` (32 with `type: 32`, 64 with `type: 64`), message "ADDR_BITS maior que XLEN" |
| V-A3 | A region (`base + size`) goes past $2^{\text{address\_bits}}$ bytes |
| V-A4 | The window of a peripheral goes past $2^{\text{address\_bits}}$ bytes |
| V-A5 | `address_bits` below `xlen` without `has_access_faults` in the profile (an access above the window must raise an access fault) |
| V-A6 | `boot.entry` or `boot.wait_restart` outside $2^{\text{address\_bits}}$ |
| V-M1 | The BOOT_MEMORY (the first region) does not start at address 0 |
| V-M2 | The BOOT_MEMORY ends after the start of the FLASH |
| V-M3 | The FLASH does not have a positive size |
| V-M4 | The FLASH ends after the start of the RAM |
| V-M5 | The RAM does not have a positive size or goes past $2^{\text{address\_bits}}$ bytes |

V-A5 is only checked when the profile is resolved, which `generate-memory-map` and `check-memory-map` do whenever `address_bits` is below `xlen`. The V-M rules hold when the platform names the FLASH and the RAM in `generate.vhdl` or in `config`.

### 9.4. Peripherals by base and size

Each `peripherals` entry gives the absolute address `base` and the `size`, the bytes of registers of the peripheral. The `base` must be a multiple of the window.

```yaml
address_bits: 32
peripherals:
  - {name: DISPLAY,  base: 0x80001000, size: 4}
  - {name: SWITCHES, base: 0x80003000, size: 64}
  - {name: CLINT,    base: 0xE0000000, size: 64K}
```

| Field | Meaning |
| :--- | :--- |
| `base` | Absolute address of the start of the window, aligned to its size |
| `size` | Bytes of registers. What is left of the window after them is the former padding |
| `id`, `offset`, `padding` | Refused with the migration message: the entry gives the `base` that the `id` used to give (`id: 5` becomes `base: 0xD0000000`) and the `size` |

| Rule | Rejection condition |
| :--- | :--- |
| V-P1 | The entry lacks `base` or `size`, the `size` is not positive, or it has `id`, `offset` or `padding` |
| V-P2 | The `base` is not a multiple of the window |
| V-P4 | Two peripheral windows overlap |
| V-P5 | The window of a peripheral overlaps a region |
| V-P6 | The top-level `periph_window` field, or `ext_base` or `periph_base` of `generate.vhdl`, which the core no longer knows |
| V-S1 | The `strict_periph` key, when given, is not a boolean |

The `strict_periph` key of the platform, true when absent, is a policy of the interconnect: when on, an access to what is left of the window after the `size` ends with an error, and with `strict_periph: false` that access reads zero and ignores the write. It comes out as `STRICT_PERIPH` in the map package, not in the `config_pkg`.

The symbols of a peripheral in the `checks` are `<NAME>.base`, `<NAME>.size`, `<NAME>.window` and `<NAME>.index`. The map package gains, for each peripheral, `<NAME>_BASE` (of type `addr_t`) and `<NAME>_INDEX`, and the tables below.

| Constant | Type | Value |
| :--- | :--- | :--- |
| `PERIPH_COUNT` | natural | Number of `peripherals` entries |
| `STRICT_PERIPH` | boolean | The `strict_periph` key |
| `periph_addr_array_t` | type | `array (natural range <>) of addr_t` |
| `PERIPH_BASES` | `periph_addr_array_t(0 to PERIPH_COUNT - 1)` | The `base` of each peripheral, indexed by `<NAME>_INDEX` |
| `PERIPH_MASKS` | `periph_addr_array_t(0 to PERIPH_COUNT - 1)` | The window mask of each peripheral |


## 10. The `config_pkg`

### 10.1. Contents

The `config_pkg` is the VHDL package of constants of a platform, written from the `platform.yaml`. It has the contract of the default package of the Common-Components (`src/config_pkg.vhd`), with the same unit name, constants, types and functions, and only the values change, so the generated version takes its place in the list of sources. With the default values (RV32I with Zicclsm, 32 address bits, no peripherals) the text is identical to the Common-Components one, except for the generation header and the cache windows. It is a package of constants, not a generic one, because Quartus Lite refuses the generic package.

| Group | Constants |
| :--- | :--- |
| Base and widths | `IS_64`, `IS_E`, `ADDR_BITS`, `XLEN`, `REG_BITS`, `NUM_REGS` and the subtypes `word_t`, `reg_t`, `addr_t` and `map_addr_t` |
| Memory system | `HAS_ICACHE`, `HAS_DCACHE`, `FLASH_ON_BUS` and `RAM_ON_BUS` |
| Extensions | One `HAS_<EXTENSION>` per profile key (`HAS_ZICCLSM` to `HAS_ZIHINTPAUSE`) |
| Memory | `BOOT_MEMORY_BITS`, `BOOT_MEMORY_BASE` and `BOOT_MEMORY_END` (from 0 to $2^{\text{BOOT\_MEMORY\_BITS}}$), `FLASH_BASE`, `FLASH_END`, `RAM_BASE` and `RAM_END` of type `map_addr_t`, and `I_CACHE_WINDOW_BITS` and `D_CACHE_WINDOW_BITS` |
| Peripherals of the core | `HAS_GPIO`, `HAS_CLINT`, `HAS_PLIC` and `HAS_TIMER`, true when the name is in `peripherals` |
| Composite | `HAS_MULTIPLICATION` (`HAS_M or HAS_ZMMUL`), `HAS_ANY_COUNTER` (`HAS_ZICNTR or HAS_ZIHPM`) and `HAS_SSCOF` (`HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS`) |
| Functions | `isa_string`, the ISA text (`rv32im_zicsr_zicntr`), and `check_isa`, which fails at elaboration when a dependency between constants does not hold |

`map_addr_t` is `unsigned(ADDR_BITS downto 0)`, one bit wider to represent the exclusive end $2^{\text{ADDR\_BITS}}$. Each address comes out as `resize(unsigned'(x"..."), ADDR_BITS + 1)`, with the hexadecimal digits that `ADDR_BITS` asks for (eight with 32 bits), so the width holds below and above 32 bits too. `FLASH_ON_BUS` and `RAM_ON_BUS` say that the memory is reached through the bus, and they are `memory.rom.external` and `memory.ram.external` of the platform. The two cache windows have the width of the tag window of section 7.1. The package has no constants for the peripherals of the SoC (UART, display, switches, keys, FLASH controller), nor `EXT_BASE`, `PERIPH_BASE` and `STRICT_PERIPH`, which stay in the map package.

`check_isa` checks that the counters, the interrupts and the access faults have `Zicsr`, that `Sscofpmf` has `Zihpm` and interrupts, that `ADDR_BITS` is from 16 to `XLEN` (the core has no MMU, so the effective address never passes `XLEN` bits), that the instruction cache requires `FLASH_ON_BUS` and the data cache requires `RAM_ON_BUS`, and the order of the BOOT_MEMORY, the FLASH and the RAM inside $2^{\text{ADDR\_BITS}}$. The entities call it once, in an `if check_isa generate`.

### 10.2. Generating it with the map

The key `generate.config_pkg` asks for the file, and `generate-memory-map` writes it (and `--check` compares it) with the others.

```yaml
generate:
  vhdl: {path: rtl/map_pkg.vhd, package: map_pkg, rom: FLASH, ram: RAM}
  config_pkg: {path: rtl/config_pkg.vhd}
```

A platform without the key does not generate the package, and its files do not change.

### 10.3. Split with the map package

The `config_pkg` sits next to the map package. The constants that both carry must agree.

| Constant of the `*_map_pkg` | Constant of the `config_pkg` |
| :--- | :--- |
| `IS_E` | `IS_E` |
| `HAS_<EXTENSION>`, `HAS_ICACHE`, `HAS_DCACHE`, `FLASH_ON_BUS`, `RAM_ON_BUS`, `BOOT_MEMORY_BITS`, `I_CACHE_WINDOW_BITS`, `D_CACHE_WINDOW_BITS` | The same |
| `FLASH_BASE_KIB`, `FLASH_END_KIB`, `RAM_BASE_KIB`, `RAM_END_KIB` | `FLASH_BASE`, `FLASH_END`, `RAM_BASE`, `RAM_END`, in bytes |

Only the map package has `BOOT_MEMORY_SIZE_BYTES`, the `*_STORAGE_BYTES`, `RAM_LAST_PAGE`, the cache sizes, `PERIPH_COUNT`, `STRICT_PERIPH`, the `PERIPH_BASES` and `PERIPH_MASKS` tables, `<NAME>_BASE` and `<NAME>_INDEX` of each peripheral and the constants of the CLINT, the PLIC and the SDRAM clock. Only the `config_pkg` has the base and the widths, the types, the composites, the `HAS_` constants of the peripherals of the core and the functions. The map package uses `addr_t` and `ADDR_BITS` of the `config_pkg`, so the `config_pkg` comes first in the compilation order. A map package does not write a KiB value that does not fit a `natural`, nor the last page of the RAM above 32 bits.

When the platform asks for both files, `check-memory-map` reads both from disk and fails with `config-pkg` for a missing file or for a constant with different values in the two.

### 10.4. Variants for the formal proof

`generate-config-pkg` writes the package of a platform or of a variant of it, with no need for `--config`.

```bash
uv run riscv-tools --root <project> generate-config-pkg --platform src/platform/platform.yaml
uv run riscv-tools --root <project> generate-config-pkg --platform src/platform/platform.yaml \
    --set IS_64=true --set ADDR_BITS=40 --output formal/config_rv64.vhd
```

| Option | Effect |
| :--- | :--- |
| `--platform` | The `platform.yaml` the package comes from |
| `--set NAME=VALUE` | Replaces `IS_64`, `IS_E` or a `HAS_*` (`true` or `false`) or `ADDR_BITS` (integer). Repeatable |
| `--output` | File to write. Without it the package goes to the standard output |

The variant is validated as a platform of its own, with V-A1 to V-A6 for its `ADDR_BITS` and `IS_64`, and the peripherals of the upper half of the space move to the upper half of the new width, in the same 1/16 slot of the space and at the same offset inside it. A name that is not a constant of the package is an error, and so is a variant with `HAS_ICACHE` or `HAS_DCACHE` over a memory that is not on the bus. The header of the file lists the variant.

### 10.5. List of sources

`sources` keeps a single `config_pkg.vhd` in the list. When the file of the Common-Components and the one generated by the platform both appear, the generated one stays, at the position of the default, so every unit that uses it comes after it (see [sources](sources.md)).

### 10.6. Platforms that must declare more

Some platforms need one more declaration so that the generated `config_pkg` reflects their choice.

| Case | What to declare |
| :--- | :--- |
| Interrupts without `Zicsr` in the default profile (`check_isa` fails at elaboration) | Generate the variant with `--set HAS_ZICSR=true`, or turn `Zicsr` on in the profile |
| Address width below 26 bits with caches | The cache windows never go past `address_bits`, so the tag window is the whole space |

## 11. Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_memory_map.py::test_evaluate_number_notations` | Hex, VHDL-based, `K`, `u` suffix and arithmetic. |
| `tests/test_memory_map.py::test_evaluate_symbols_and_log2` | Symbols in expressions, `log2`/`clog2`, and `log2` rejecting non powers of two. |
| `tests/test_memory_map.py::test_evaluate_rejects_unknown_symbol_inexact_division_and_code` | Unknown symbols, inexact division and arbitrary code are rejected. |
| `tests/test_memory_map.py::test_symbols_flattens_regions_reserved_boot_and_peripherals` | The symbol table. |
| `tests/test_memory_map.py::test_the_reference_platform_is_consistent` | A consistent map has no problems. |
| `tests/test_memory_map.py::test_validate_platform_reports_an_inconsistent_map` | Overlaps, reserved outside RAM, bad boot entries and peripheral ids. |
| `tests/test_memory_map.py::test_check_passes_when_every_copy_agrees` | Five copies in five formats agree. |
| `tests/test_memory_map.py::test_check_fails_when_one_copy_diverges` | Changing any one copy fails exactly its check. |
| `tests/test_memory_map.py::test_check_reports_every_divergent_match_of_one_pattern` | Each divergent match is reported. |
| `tests/test_memory_map.py::test_check_fails_when_a_copy_no_longer_matches_the_pattern` | A reformatted copy is noticed. |
| `tests/test_memory_map.py::test_check_fails_on_a_missing_file_unless_optional` | Missing file fails unless `optional`. |
| `tests/test_memory_map.py::test_check_stops_at_an_inconsistent_map` | No copy is read when the map itself is inconsistent. |
| `tests/test_memory_map.py::test_load_platform_rejects_a_non_mapping` | A non-mapping file is rejected. |
| `tests/test_memory_map.py::test_cmd_check_memory_map_exit_status` | The command prints OK, or exits 1 listing the mismatches. |
| `tests/test_interrupts.py` | The package has `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES`, the header has the registers of the CLINT and the rate of `mtime`, and an inconsistent section (rate, missing CLINT, profile without the interrupts) is rejected. |
| `tests/test_memory_choice.py` | The `memory` section and the `--memory` option generate the 9 valid combinations as 9 different packages and refuse the 7 invalid ones, the constants and the simulation parameters come from the choice, and rules V1 to V5, V7 and V10 fail with a clear message. |
| `tests/test_config_from_platform.py` | The `memory` keys, the `tohost` and `stdout` environment and the address widths come from the map, and the map wins over the file and its `extends`. |
| `tests/test_core_profile.py` | The `core` block and the inferred profile (matrix order, `Zicsr` beside `Zicntr`, extras), `--profile` keeping the extras, each error (unknown or repeated extension, refused combination, `type: 64` without an `rv64` base, `isa` in place of `base`), the refusal of `profile:` and `extras:` with the migration, and the name without a matrix. |
| `tests/test_peripheral_offsets.py` | The window derived from `size`, the `base`, `size`, `window` and `index` symbols, one rejection for each V-P1 to V-P5, the refusal of `id`, `offset` and `padding` with the migration message, the `PERIPH_BASES` and `PERIPH_MASKS` tables, V-S1 and `STRICT_PERIPH` in the map package. |
| `tests/test_address_bits.py` | The `address_bits` field, one rejection for each V-A1 to V-A6, the refusal of `periph_window` (V-P6), `resolve` with the `rv64` profiles, `--profile` and the new keys of `config.yaml`. |
| `tests/test_config_pkg.py` | The `config_pkg` for 32, 24 and 40 bits, the E base, the variants and what they refuse, the `HAS_` constants of the peripherals of the core, `FLASH_ON_BUS` and `RAM_ON_BUS`, the cache rule (V-C1 and V-C2), the order of the map of the core (V-M), writing with the map and `--check`, the coherence between the two packages, the command and the proof that the map package and the `config_pkg` of the DE0-CV do not change. |
| `tests/test_generate_memory_map.py` | The specs, the linker script and the VHDL package come out of the map; `--check` catches a missing or edited file; an address off a KiB, a peripheral window over a region and a removed key are rejected; the command writes and checks. |

## 12. Usage

```bash
uv run riscv-tools --root <project> check-memory-map --platform platforms/internal-mem.yaml
```

No `--config` needed. Exit status 1 and one `MISMATCH` line per disagreement when a copy diverges; meant for CI.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
