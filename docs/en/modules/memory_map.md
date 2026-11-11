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
peripherals:                  # base = window | id << (address_bits - 4)
  - {name: GPIO, base: 0xA0000000, id: 2}
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

- **Symbols** in `expect`: `<REGION>.base|size|end|words`, `<reserved>.base|size|end`, `boot.entry|wait_restart`, `<PERIPHERAL>.base|id`.
- **Numbers** accept hexadecimal, decimal, VHDL-based (`16#800#`), suffixes (`30K`, `0x800u`) and `+ - * /` (exact division), plus `log2()` (exact) and `clog2()` (rounded up, for address widths).
- A check whose pattern matches nothing **fails** ("the copy moved"); `optional: true` skips a file that is absent. A pattern with several matches must agree at every match.
- Before the copies are read the map itself is validated: regions and reserved words do not overlap, reserved words sit inside a RAM region, `boot.entry` is in an executable region, `boot.wait_restart` is in the first region, each peripheral base matches its id, and every region ends at or below the peripheral window (the lower half of the space belongs to the BOOT_MEMORY, the ROM and the RAM, the upper half to the peripherals; `0x80000000` with 32 bits, see section 9).

## 2. Generating the files of the map

The same YAML can say, in the `generate` section, which files come out of it, so no copy of the map has to be written by hand.

| Key | Generated file | Content |
| :--- | :--- | :--- |
| `specs` | GCC specs file | The linker flags: `__flash`, `__flash_size`, `__ram`, `__ram_size` and `rv32_wait_restart`. The RAM of the linker ends where the reserved word `ram_limit` begins |
| `boot_ld` | Boot memory linker script | The `boot_memory` memory in the first region and the `RESET_RESERVED` from `boot.wait_restart` |
| `runtime` | Runtime header (`.h`, also included by `.S`) | `RV32_RAM_END` (end of the `ram` region), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` and `RV32_STDOUT_BASE`, from the `reserved` ranges the map has, `RV32_BOOT_ENTRY` (where the boot memory jumps) and `RV32_<NAME>_BASE` for each peripheral; the runtime in C and assembly (`_exit.c`, `stdio.c`, `boot_memory.S`, `spike_exit.S`) uses these names instead of hand-written addresses |
| `config_pkg` | VHDL package of the constants of the platform | The `config_pkg` of section 10, next to the map package |
| `vhdl` | VHDL package | The constants `BOOT_MEMORY_BITS`, `BOOT_MEMORY_SIZE_BYTES`, `ROM_BASE_KIB`, `ROM_END_KIB`, `ROM_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES`, `RAM_LAST_PAGE`, `EXT_BASE_KIB` and `PERIPH_BASE_KIB`, the `ROM_EXTERNAL` and `RAM_EXTERNAL` flags (from `generate.vhdl` or from the `memory` section), the cache constants of the `memory` section and, for each peripheral, `<NAME>_BASE` and `<NAME>_ID` |

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

`ext_base` and `periph_base` are optional and default to `0x80000000`, the peripheral window. `ROM_STORAGE_BYTES` and `RAM_STORAGE_BYTES` are the smallest power of two that covers the end of the ROM and the size of the RAM, and `RAM_LAST_PAGE` is bits 31:12 of the last 4 KiB page of the RAM.

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

## 4. The profile of the platform

The platform picks its profile in `profile:` (`rv32im`, `rv32em_zicsr`, ...) and says where the specification of the profiles is in `profiles:`, a path relative to the `platform.yaml` (the `profiles/matrix.yaml` of the Core). The name starts with `rv32i` (32 registers), `rv32e` (16), `rv64i` or `rv64e` and must be one of the profiles of the specification. It gives:

| Output | Content |
| :--- | :--- |
| VHDL package | `HAS_E` (true on the RV32E) and one boolean `HAS_<EXTENSION>` per extension of the core (`HAS_M`, `HAS_ZMMUL`, `HAS_ZICSR`, `HAS_ZICNTR`, `HAS_ZIHPM`, `HAS_ZIMOP`, `HAS_ZICOND`, `HAS_ZIHINTNTL`, `HAS_ZIHINTPAUSE`, `HAS_ZIFENCEI`, `HAS_ZICCLSM`, `HAS_INTERRUPTS`, `HAS_SSCOFPMF`, `HAS_ACCESS_FAULTS`) and `PERIPH_SLOTS`, the 8-bit mask of the 256 MiB windows of the peripheral bus that hold a peripheral (bit `n` is set for the `id` `n` of the `peripherals` list) |
| `config.yaml` | `isa.base`, which picks `-march` and `-mabi` of the programs and of the boot memory (`rv32e` with `ilp32e`, the others with `ilp32`), and the `sim.config_pkg`, the text of the `config_pkg` of the profile that the runner compiles in place of the `config_pkg.vhd` of the sources (the base and the extensions of the core are constants of that package, not generics of the top) |

`--profile NAME`, a global option of `riscv-tools`, replaces the `profile:` of the platform without editing it, to run the same platform over many profiles in a test matrix. It applies to `generate-memory-map` (writes the package of that profile), to `platform sync` and to every command that reads the configuration. A name that the specification does not list is rejected before anything runs.

`extras:` turns on what the profile does not turn on, by extension name (`extras: [Zihintntl, Zihintpause, Interrupts, Sscofpmf, AccessFaults]`; `Sscofpmf` needs Zihpm in the profile and `Interrupts` in the extras, and generation fails without them), and it also holds with `--profile`. The matrix of the Core lists Zimop and Zicond as profile extensions, so only the names the matrix does not list depend on `extras:`; the first two are still accepted there. Every switch that neither the profile nor the extras turn on comes out `false` in the package.

```bash
uv run riscv-tools --root <project> --profile rv32em_zicsr generate-memory-map --platform src/platform/platform.yaml
```

## 5. The interrupts of the platform

A platform with the machine interrupts turns on the `Interrupts` extra (the core enables them only with `Zicsr`), lists the `CLINT` and, for the external lines, the `EXT_IRQ` among the `peripherals`, and describes the clock in the `interrupts` section.

```yaml
extras: [Interrupts]
peripherals:
  - {name: CLINT,   base: 0xE0000000, id: 6}
  - {name: EXT_IRQ, base: 0xF0000000, id: 7}
interrupts:
  clock_hz: 50000000   # clock of the domain of the core and the CLINT
  mtime_hz: 1000000    # rate at which the mtime of the CLINT counts
```

The `mtime` of the CLINT is a counter of its own, set by `mtime_hz`, and it is independent of the CSR `time` of Zicntr, which the core serves. With `clocks.core` in the platform `clock_hz` is left out and is the core clock rounded to a whole number of cycles per increment; when written, it must be that value. `clock_hz` must be a multiple of `mtime_hz`, the profile must turn on `has_interrupts`, and the `peripherals` list must have the `CLINT`; the absence of any of them is an error before generating and in `check-memory-map`.

| Output | Constants |
| :--- | :--- |
| VHDL package (`vhdl`) | `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES` (clock cycles per increment of `mtime`, the `tick_cycles` generic of the CLINT), besides `CLINT_BASE`, `CLINT_ID`, `EXT_IRQ_BASE` and `EXT_IRQ_ID` |
| Runtime header (`runtime`) | `RV32_CLINT_BASE`, `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` and `RV32_MTIME_HZ`, which `FreeRTOSConfig.h` uses in `configMTIMECMP_BASE_ADDRESS`, `configMTIME_BASE_ADDRESS` and `configCPU_CLOCK_HZ` |

The offsets of the registers inside the 64 KiB window of the CLINT follow the SiFive layout that the FreeRTOS port expects.

### 5.1. PLIC and interrupt sources

A platform with a PLIC lists it in `peripherals` with a `size` (the window it decodes, a power of two of at least `0x200008` bytes) and describes it in `interrupts`.

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, id: 7, size: 4M}
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

The `memory` section of the `platform.yaml` picks four independent things per platform, and the 16 combinations come out of them. No field has a default, so forgetting one is an error and the platform never builds a combination other than the one its author wrote. A platform without the section keeps generating the package it generated before.

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

The VHDL package gains the constants below. `ROM_VIA_PORT` and `RAM_VIA_PORT` are the values of the `rom_external` and `ram_external` generics of the core, because a cache can only exist on the side of the core port protocol.

| Constant | Type | Value |
| :--- | :--- | :--- |
| `ROM_EXTERNAL` | boolean | `memory.rom.external` |
| `RAM_EXTERNAL` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, or 256 without the cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, or 256 without the cache |
| `CACHE_WINDOW_BITS` | natural | Smallest width from 26 to 29 such that the ROM and the RAM each fit one aligned window of $2^{\text{width}}$ bytes (26 is 64 MiB, 27 is 128 MiB), derived from the regions |
| `ROM_VIA_PORT` | boolean | `ROM_EXTERNAL or HAS_ICACHE` |
| `RAM_VIA_PORT` | boolean | `RAM_EXTERNAL or HAS_DCACHE` |

In the `config.yaml` the same values arrive as `sim.parameters` with the same names (`ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` and `DCACHE_SIZE_BITS`; `CACHE_WINDOW_BITS` only when above 26), and the simulation top must declare the matching generics. Without `config.addr_widths` in the platform, the address widths come from the choice, and the `boot_memory` and each internal memory are listed, since an external memory is a chip sized by the top itself. With `config.addr_widths` listed, the list wins.

### 7.2. Validation

| Rule | Condition | Result |
| :--- | :--- | :--- |
| V1 | The four booleans exist and there is no unknown key | Error |
| V2 | `size_bits` is a power of two and at least 256 | Error |
| V3 | With any cache, the ROM and the RAM each fit one aligned window of up to 512 MiB (the cache tag keeps the bits below the window) | Error |
| V4 | With the ROM through the core port, its size fits the 1024 KiB window of the router | Error |
| V5 | An `exec` region in the RAM needs an external RAM and the ROM through the port (external ROM or instruction cache) | Error |
| V7 | An `exec` region in the RAM behind the instruction cache needs Zifencei in the profile | Error |
| V8 | Instruction cache over an internal ROM or data cache over an internal RAM | Warning |
| V9 | Platform with peripherals | Note |
| V10 | With any cache, `reserved.fromhost` exists and sits in the last 4 KiB page of the RAM, the one the cache skips | Error |

An external ROM without an instruction cache is valid. The warning and the note are printed as `NOTE` on the standard error of `generate-memory-map`, and errors stop the generation.

### 7.3. The `--memory` option

`--memory`, a global option of `riscv-tools`, replaces fields of the `memory` section without editing the platform, to run the same platform over the 16 combinations. The value is a comma list of `key=value` pairs.

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

The top-level field `address_bits` of the `platform.yaml` is an integer from 16 to 64 with the width of the physical address. When absent it is 32, and no platform written for 32 bits needs to change. An `rv64...` profile turns on the `IS_64` of the `config_pkg`, and above 32 bits only an `rv64` profile is valid.

```yaml
address_bits: 24      # optional, 32 by default
profile: rv32im
peripherals:          # base = 2**(address_bits - 1) | id << (address_bits - 4)
  - {name: UART, base: 0xC00000, id: 4}
```

### 9.2. The peripheral window

The peripheral window is the upper half of the address space, and the id of the peripheral takes the three bits below the window bit.

$$ \text{window} = 2^{\text{address\_bits} - 1}, \quad \text{base} = \text{window} \mid (\text{id} \ll (\text{address\_bits} - 4)) $$

With 32 bits the values are `0x80000000` and `id << 28`, the same as before. The top-level field `periph_window` fixes another base for the window, and the `ext_base` and `periph_base` of `generate.vhdl` still apply only to the package of the map, with the window of the platform as default. `CACHE_WINDOW_BITS` is capped at `address_bits`.

### 9.3. Validations

Each validation is a `platform` problem before generating and in `check-memory-map`, with the name of the field and the cause in the message.

| Rule | Rejection condition |
| :--- | :--- |
| V-A1 | `address_bits` is not an integer or is outside 16 to 64 |
| V-A2 | `address_bits` above 32 with a profile that is not `rv64` |
| V-A3 | A region (`base + size`) goes past $2^{\text{address\_bits}}$ bytes |
| V-A4 | A region goes past the peripheral window, the base of a peripheral is not the window with `id << (address_bits - 4)`, or that shift falls outside the space |
| V-A5 | `address_bits` below `xlen` without `has_access_faults` in the profile (an access above the window must raise an access fault) |
| V-A6 | `boot.entry` or `boot.wait_restart` outside $2^{\text{address\_bits}}$ |

V-A5 is only checked when the profile is resolved, which `generate-memory-map` and `check-memory-map` always do when `address_bits` is below `xlen`.

### 9.4. Peripherals by offset, id and padding

Each entry of `peripherals` gives its address by `base` (absolute) or by `offset` (in bytes, from the base of the peripheral window), one of the two and never both. The `id` is optional, and `padding` reserves bytes right after the `size`, inside the slot. With `offset` the same YAML holds for any `address_bits`.

```yaml
address_bits: 32
peripherals:
  - {name: UART,  offset: 0x40000000}                           # id 4, derived
  - {name: PLIC,  offset: 0x70000000, size: 4M, padding: 4M}    # slot 7, 4 MiB of padding
  - {name: CLINT, base: 0xE0000000, id: 6}                      # absolute form, as before
```

| Field | Meaning |
| :--- | :--- |
| `offset` | Offset of the entry in the peripheral window. The address is the window plus the `offset` |
| `base` | Absolute address, which must be in the window or above it. The Tools converts it to `offset` |
| `id` | Index of the slot, from 0 to 7. When absent it is $\lfloor \text{offset} / 2^{\text{address\_bits} - 4} \rfloor$. When present it must be the slot of the `offset` |
| `size` | Bytes the peripheral decodes |
| `padding` | Bytes reserved after the `size`. When absent it is the rest of the slot of $2^{\text{address\_bits} - 4}$ bytes |

| Rule | Rejection condition |
| :--- | :--- |
| V-P1 | The entry does not have exactly one of `base` and `offset`, or the `base` is below the window |
| V-P2 | The given `id` is not the slot of the `offset` |
| V-P3 | The `size` plus the `padding` go past the end of the slot |
| V-P4 | Two peripherals take the same bytes (`size` plus `padding`) |
| V-S1 | The `strict_periph` key, when given, is not a boolean |

The granularity of the peripheral map is the slot: the decoder of the core accepts an address of the window when the bit of the slot is set in `PERIPH_SLOTS`, and the peripheral decodes only the low bits. The padding is a reserved area with no decoding of its own. The `strict_periph` key of the platform, true when absent, chooses the handling: when on, the padding is a fault region and an access to it raises an access fault; with `strict_periph: false` the access is handled like any address of an occupied slot, and only a slot with no peripheral raises an access fault.

The symbols of the `checks` gain `<NAME>.offset`. An entry that uses `offset` or `padding` gets the constants `<NAME>_OFFSET`, `<NAME>_SIZE` (zero without `size`) and `<NAME>_PAD` in the map package, in 32 bits like `<NAME>_BASE`, and a value that does not fit 32 bits is refused. The comment of `<NAME>_PAD` describes the padding as an access fault region when `strict_periph` is true. Entries with only `base` and `id` get nothing, and the `config_pkg` does not carry them, which keeps the text of the default package of the Common-Components.

## 10. The `config_pkg`

### 10.1. Contents

The `config_pkg` is the VHDL package of constants of a platform, written from the `platform.yaml`. It has the contract of the default package of the Common-Components (`src/config_pkg.vhd`), with the same unit name, constants, types and functions, and only the values change, so the generated version takes its place in the list of sources. With the default values (RV32IM, 32 address bits, no peripherals) the text is identical to the one of the Common-Components, except for the generation header. It is a package of constants, not a generic one, because the Quartus Lite refuses a generic package.

| Group | Constants |
| :--- | :--- |
| Base and widths | `IS_64`, `IS_BASE_E`, `ADDR_BITS`, `XLEN`, `REG_BITS`, `NUM_REGS` and the subtypes `word_t`, `reg_t`, `addr_t` and `map_addr_t` |
| Extensions and caches | One `HAS_<EXTENSION>` per key of the profile (`HAS_M` to `HAS_ACCESS_FAULTS`), `HAS_ICACHE` and `HAS_DCACHE` |
| Memory | `BOOT_MEMORY_BITS`, the map in bytes of type `map_addr_t` (`ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE`, `PERIPH_BASE`), `ROM_EXTERNAL`, `RAM_EXTERNAL` and `CACHE_WINDOW_BITS` |
| Peripherals | One `HAS_<PERIPHERAL>` for `UART`, `UART_PINS`, `UART_JTAG`, `TIMER`, `GPIO`, `DISPLAY`, `SWITCHES`, `KEYS`, `CLINT`, `PLIC` and `FLASH_CTRL`, and `STRICT_PERIPH`, the value of the `strict_periph` key of the platform (true when absent), which a variant changes with `--set STRICT_PERIPH=false` |
| Composed | `HAS_MULDIV` (`HAS_M or HAS_ZMMUL`), `HAS_ANY_COUNTER` (`HAS_ZICNTR or HAS_ZIHPM`) and `HAS_SSCOF` (`HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS`) |
| Functions | `isa_string`, the ISA text (`rv32im_zicsr_zicntr`), and `check_isa`, which fails at elaboration when a dependency between constants does not hold |

`map_addr_t` is `unsigned(ADDR_BITS downto 0)`, with one extra bit to represent the exclusive end $2^{\text{ADDR\_BITS}}$. Each address comes out as a hexadecimal literal with the digits that `ADDR_BITS` asks for (eight with 32 bits), so the width holds below and above 32 bits too. `HAS_<PERIPHERAL>` is true when the name is in `peripherals`, and the `UART` counts as `HAS_UART_JTAG` when `console` is `jtag` and as `HAS_UART_PINS` when `console` is `pins`. `ROM_EXTERNAL` and `RAM_EXTERNAL` say that the memory is reached through the port of the core (outside the chip or behind a cache), and have the values of `ROM_VIA_PORT` and `RAM_VIA_PORT` of the map package. The `HAS_E` of the map package is the `IS_BASE_E` here.

`check_isa` checks that the counters, the interrupts and the access faults have `Zicsr`, that `Sscofpmf` has `Zihpm` and interrupts, that `ADDR_BITS` is from 16 to 64 and above 32 only with `IS_64`, and the order of the BOOT_MEMORY, the ROM, the RAM, the external window and the peripheral window inside $2^{\text{ADDR\_BITS}}$. The entities call it once, in an `if check_isa generate`.

### 10.2. Generating it with the map

The key `generate.config_pkg` asks for the file, and `generate-memory-map` writes it (and `--check` compares it) with the others.

```yaml
generate:
  vhdl: {path: rtl/map_pkg.vhd, package: map_pkg, rom: FLASH, ram: RAM}
  config_pkg: {path: rtl/config_pkg.vhd}
```

A platform without the key does not generate the package, and its files do not change.

### 10.3. Split with the map package

At this stage the `config_pkg` comes next to the map package, which loses no constant. The constants both carry must agree.

| Constant of the `*_map_pkg` | Constant of the `config_pkg` |
| :--- | :--- |
| `HAS_E` | `IS_BASE_E` |
| `HAS_<EXTENSION>`, `HAS_ICACHE`, `HAS_DCACHE`, `BOOT_MEMORY_BITS`, `CACHE_WINDOW_BITS` | The same |
| `ROM_VIA_PORT`, `RAM_VIA_PORT` | `ROM_EXTERNAL`, `RAM_EXTERNAL` |
| `ROM_BASE_KIB`, `ROM_END_KIB`, `RAM_BASE_KIB`, `RAM_END_KIB`, `EXT_BASE_KIB`, `PERIPH_BASE_KIB` | `ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE`, `PERIPH_BASE`, in bytes |

Only the map package has `BOOT_MEMORY_SIZE_BYTES`, the `*_STORAGE_BYTES`, `RAM_LAST_PAGE`, the cache sizes, `ROM_VIA_PORT`, `RAM_VIA_PORT`, the `<NAME>_BASE` and `<NAME>_ID` of each peripheral and the constants of the CLINT, the PLIC and the SDRAM clock. Only the `config_pkg` has the base and the widths, the types, the composed constants, `HAS_<PERIPHERAL>` and the functions, and the map package also has `PERIPH_SLOTS`. A map package does not write a KiB value that does not fit a `natural`, nor the last page of the RAM above 32 bits.

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
| `--set NAME=VALUE` | Replaces `IS_64`, `IS_BASE_E` or a `HAS_*` (`true` or `false`) or `ADDR_BITS` (integer). Repeatable |
| `--output` | File to write. Without it the package goes to the standard output |

The variant is validated as a platform of its own, with V-A1 to V-A6 for its `ADDR_BITS` and `IS_64`, and the peripherals move to the window of the new width. A name that is not a constant of the package is an error. The header of the file lists the variant.

### 10.5. List of sources

`sources` keeps a single `config_pkg.vhd` in the list. When the file of the Common-Components and the one generated by the platform both appear, the generated one stays, at the position of the default, so every unit that uses it comes after it (see [sources](sources.md)).

### 10.6. Platforms that must declare more

Some platforms need one more declaration so that the generated `config_pkg` reflects their choice.

| Case | What to declare |
| :--- | :--- |
| Interrupts without `Zicsr` in the default profile (`check_isa` fails at elaboration) | Generate the variant with `--set HAS_ZICSR=true`, or turn `Zicsr` on in the profile |
| A `UART` whose connection (pins or JTAG) matters | `console: pins` or `console: jtag`, or the peripheral names `UART_PINS` and `UART_JTAG`. Without that only `HAS_UART` holds |
| `PERIPH_SLOTS` | Stays only in the map package, which writes it from `peripherals` |
| Address width below 26 bits with caches | `CACHE_WINDOW_BITS` never goes above `address_bits`, so the tag window is the whole space |

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
| `tests/test_memory_choice.py` | The `memory` section and the `--memory` option make the 16 combinations 16 different packages, the constants and the simulation parameters come from the choice, and rules V1 to V5, V7 and V10 fail with a clear message. |
| `tests/test_config_from_platform.py` | The `memory` keys, the `tohost` and `stdout` environment and the address widths come from the map, and the map wins over the file and its `extends`. |
| `tests/test_peripheral_offsets.py` | `offset` and `base` give the same map, the derived `id`, the same `offset` with another `address_bits`, one rejection for each of V-P1 to V-P4, V-S1 for `strict_periph`, the comment of `_PAD` according to the key and the `_OFFSET`, `_SIZE` and `_PAD` constants only on relative entries. |
| `tests/test_address_bits.py` | The `address_bits` field and the derived window, one rejection for each of V-A1 to V-A6, the window fixed by `periph_window`, `resolve` with the `rv64` profiles, `--profile` and the new keys of the `config.yaml`. |
| `tests/test_config_pkg.py` | The `config_pkg` for 32, 24 and 40 bits, the E base, the variants and what they refuse, the UART by `console`, writing with the map and `--check`, the coherence between the two packages, the command, and the proof that the map package and the `config_pkg` of the DE0-CV do not change. |
| `tests/test_generate_memory_map.py` | The specs, the linker script and the VHDL package come out of the map; `--check` catches a missing or edited file; an address off the KiB grid and an inconsistent map are rejected; the command writes and checks. |

## 12. Usage

```bash
uv run riscv-tools --root <project> check-memory-map --platform platforms/internal-mem.yaml
```

No `--config` needed. Exit status 1 and one `MISMATCH` line per disagreement when a copy diverges; meant for CI.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
