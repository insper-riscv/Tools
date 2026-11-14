# `compiler`

Compiles one bare-metal test source (`.c`, `.cc`, `.cpp` or `.S`) into a linked `.elf`/`.bin`. This is what `compile --emit mif|hex|asm` (see Usage below) calls once per test discovered in a project's `c_dir`/`asm_dir`.

## Per-test header conventions

A test's own source file declares its build/run requirements in comments at the top, parsed by this module:

| Header | Meaning |
| :--- | :--- |
| `// RV32_EXT: M` | Compiled with `-march=rv32im` (extension letters add onto the implicit `rv32i` base; comma-separated, order doesn't matter, normalized via `isa.canonical_order`). Omitted entirely means plain `rv32i`. |
| `// RV32_TEST_KIND: unit` | Default if omitted. Checked through `tohost` only (see [`htif`](htif.md)). |
| `// RV32_TEST_KIND: memory` | Also dumps RAM and compares it against a golden JSON (see [`mem_validator`](mem_validator.md), [`golden_generator`](golden_generator.md)). |
| `// RV32_TIMEOUT_S: 5` | How long [`orchestrator`](orchestrator.md) waits for this test's `tohost` before falling back to a full reprogram. Defaults to `orchestrator`'s `default_timeout_s`. |

## C library

`toolchain.libc` selects what a test links against:

| Value | Flags | Use |
| :--- | :--- | :--- |
| `none` (default) | `-nostdlib` | Works with any toolchain. A test that needs `malloc` or similar gets it from the project's own `paths.syscalls`. |
| `picolibc` | `--specs=picolibc.specs -Wl,--no-gc-sections` | For a GCC configured with picolibc, such as the one Infra's `manual/GCC_SETUP.md` builds (and its `ci-elf` image carries) for `rv32im`/`ilp32`. `strlen`, `memcpy`, `printf` and the rest come from picolibc. |

The startup code stays the project's own `crt0.S` (`-nostartfiles` in both cases). `picolibc.specs` turns on `--gc-sections`, which drops every section a link script neither keeps nor reaches from its entry, so it is switched off again. That toolchain has a single library variant (`rv32im`/`ilp32`), so a test built for a narrower `-march` links library code that may use instructions its core lacks, such as multiplication and division in `printf`.

## C++

`toolchain.cxx: true` (default `false`) lets a test be written in C++, as the `src.cc` or `src.cpp` of its folder under `c_dir`. It needs `toolchain.libc: picolibc` or a `toolchain.specs`, and a toolchain built with the `libstdc++` of the test's variant.

| Part | What changes with `cxx: true` for a `.cc` or `.cpp` test |
| :--- | :--- |
| Driver | The toolchain's `g++`: the `gcc` name with `g++` in its place, or `toolchain.gxx`. It adds `-lstdc++` and `-lm` itself |
| Standard | ISO/IEC 14882:2024 (C++23), `-std=c++23 -Wall -Wextra -Wpedantic -Werror` |
| Extra flags | `toolchain.cxx_options`, a list for C++ sources only, such as `["-fno-exceptions", "-fno-rtti"]` |
| Specs, without `toolchain.specs` | `--specs=picolibcpp.specs --crt0=hosted`, which links `crtbegin.o` and `crtend.o` and makes a returning `main` call `exit`, and the `picolibcpp.ld` linker script (`-T`, unless `paths.linker_script`) |
| Specs, with `toolchain.specs` | The file generated with `cxx: true` (see [`memory_map`](memory_map.md)), which already carries all of it |
| The project's C sources | Those of `paths.sources` are compiled apart, as C, and linked into the test; the C++-only flags of `emulator.gcc_flags` stay out of that compile |

`crtbegin.o` registers the unwind frames and `crtend.o` ends `.eh_frame`. `picolibc.specs` leaves both out, and without them a `throw` jumps to address 0 or reads garbage at the end of the table. So the project's own `crt0` (`paths.crt0`) does not work with C++, and the compile refuses that combination.

`picolibc.specs` and a specs file that already includes it cannot share a command line. The driver stops with `attempt to rename spec 'link' to already defined spec 'picolibc_link'`, so a test gets one of the two, and the project's `toolchain.specs` already includes `picolibc.specs`.

Before compiling, the compile checks that the toolchain has the `libstdc++.a` of the variant (the test's `-march` and `-mabi`). Without it the test fails with `toolchain.cxx is true but the toolchain has no libstdc++.a for the variant -march=... -mabi=...: the toolchain must be built with libstdc++ for it`, instead of `cannot find -lstdc++` at link time or a missing `bits/c++config.h` at compile time.

`libstdc++` asks the runtime for `getentropy`, `read`, `open` and `close` (through `std::random_device`, which every program with `new` or an exception carries) and for the `stdout` and `stderr` streams (through the `std::terminate` handler). The four functions come ready from `generate.syscalls` of [`memory_map`](memory_map.md), and the streams are those of the platform's `stdio.c`.

Atomics are out of scope. GCC does not build `libatomic` for `riscv32-unknown-elf`, so an 8-byte `std::atomic`, and any `std::atomic` on a variant without the A extension, ends with `__atomic_*` undefined at link time.

## C23 standard

Every C source compiled by this package follows ISO/IEC 9899:2024 (C23). The test compile, `c_to_asm`, the boot memory and the NOR programmer pass GCC `-std=c23` (not `-std=gnu23`) and `-Wall -Wextra -Wpedantic -Werror`, so any warning stops the build. The flags live in the `C_STANDARD_FLAGS` constant, already included in `optimize_flags`. The generated `rv32_test.h` declares `rv32_wait_restart` with the standard `[[noreturn]]` attribute, not `__attribute__`.

## Platform specs file

With `toolchain.specs`, the project has no `crt0.S` and no linker script. The specs file is the whole description of the platform, and the toolchain does the rest:

```
%include <picolibc.specs>
%rename link rv32imfpga_picolibc_link

*link:
%(rv32imfpga_picolibc_link) --defsym=__flash=0x800 --defsym=__flash_size=30K --defsym=__ram=0x8000 --defsym=__ram_size=160K-24 %{!DRV32_SPIKE:--defsym=rv32_wait_restart=0x100}

*startfile:
crt0-hosted%O%s
```

| Piece | Comes from |
| :--- | :--- |
| Linker script | The toolchain's `picolibc.ld`, which the GCC driver adds when it sees no `-T`; the `--defsym` values place flash and RAM |
| Startup | The toolchain's `crt0-hosted`: sets `sp` and `gp`, copies `.data` from flash, clears `.bss`, sets up TLS, runs constructors, calls `main`, and calls `exit` with what `main` returns |
| `_exit` | The project, through `paths.sources` (picolibc does not provide it) |

A test compiled this way is a hosted program: `-ffreestanding` is not passed, `main` may return (and falls back to `return 0`), and `-nostartfiles` is passed only when `paths.crt0` names a startup file of the project's own. `toolchain.libc` is ignored.

The toolchain's linker script drops sections nothing references (`--gc-sections`). A C test of kind `memory` is checked through its `results` array, which it may only declare (a test that just checks `.bss` is zeroed never reads it), so the compile passes `-Wl,--undefined=results` for those tests to keep it.

The same specs file serves any `gcc` command, outside this package: `gcc --specs=rv32im-fpga.specs main.c _exit.c`.

### Image for Spike

When a program's image ends in code that lives elsewhere on the hardware, Spike cannot run it as is. `emulator.sources` and `emulator.gcc_flags` build a second ELF for Spike from the same sources plus a stand-in: in the example above, the hardware's `rv32_wait_restart` is a boot memory routine at address `0x100`, and the Spike ELF is built with `-DRV32_SPIKE`, which leaves that fixed address out of the link, and with a source that defines `rv32_wait_restart` as ordinary code (it only waits, since the test has already written `tohost`) and the `tohost` and `fromhost` symbols. Without `emulator.sources`, Spike runs the test's own image.

## Hex file format

With `sim.hex_format: verilog`, the simulation `.hex` comes straight from the linked ELF through `objcopy -O verilog --verilog-data-width=4` instead of from the flat binary. The file keeps the image's real word addresses:

```
@00000200
00100293 00200313 FF9FF06F
@00000203
DEADBEEF
```

A program linked at `0x800` starts at `@00000200` (word address), so it needs no leading zero words, and a gap between sections becomes a new `@` line. The default `words` format keeps one 32-bit word per line.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `toolchain.gcc` | GCC binary name/path (default `riscv32-unknown-elf-gcc`). |
| `toolchain.objcopy` | objcopy binary name/path (default `riscv32-unknown-elf-objcopy`). |
| `toolchain.libc` | `none` or `picolibc` (default `none`); see [C library](#c-library). |
| `toolchain.cxx` | `true` turns C++ on (default `false`); see [C++](#c). |
| `toolchain.gxx` | `g++` binary name/path; by default the `gcc` one with `g++` in its place. |
| `toolchain.cxx_options` | List of flags for C++ sources only (empty by default). |
| `isa.base` | Base ISA letter, always `i`, never written in a test's own header. |
| `isa.default_ext` | Extension string used when a test has no `RV32_EXT` header at all. Empty by default (plain `rv32i`). |
| `isa.canonical_order` | Fixed letter order extension letters get sorted into before being appended to the base ISA string, so `RV32_EXT: A,M` and `RV32_EXT: M,A` both normalize to the same `-march=` value. |
| `toolchain.specs` | Optional path of the platform's GCC specs file; with it, `paths.crt0` and `paths.linker_script` are not needed (see Platform specs file). |
| `paths.sources` | Optional list of source files compiled into every test (the platform's `_exit`, for instance). |
| `paths.include_dir`, `paths.crt0`, `paths.linker_script`, `paths.build_dir`, `paths.c_dir`, `paths.asm_dir` | All project-specific paths inside the consuming repo; no default, every project must set (except `paths.crt0` and `paths.linker_script`, optional with `toolchain.specs`) these. |

## Prerequisites

- The RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, provided by the `ci-elf` image of [insper-riscv/Infra](https://github.com/insper-riscv/Infra), or installed as in its `manual/GCC_SETUP.md`.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_compiler_headers.py::test_canonical_march_no_ext` | A test with no extension header resolves to the base ISA. |
| `tests/test_compiler_headers.py::test_canonical_march_single_ext` | One extension letter is appended to the base. |
| `tests/test_compiler_headers.py::test_canonical_march_order_independent` | Extension letters are sorted into the canonical order. |
| `tests/test_compiler_headers.py::test_parse_header_defaults` | Headers that are absent fall back to the defaults. |
| `tests/test_compiler_headers.py::test_parse_header_all_fields` | `RV32_EXT`, `RV32_TEST_KIND` and `RV32_TIMEOUT_S` are all read. |
| `tests/test_cli_compile.py::test_discover_tests_finds_c_and_asm_sorted_by_name` | C and assembly tests are found and sorted by name. |
| `tests/test_cli_compile.py::test_discover_tests_empty_when_no_folders` | No test folders yields no tests. |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | A C test, a C memory test and an assembly test compile and land in the manifest. |
| `tests/test_cli_compile.py::test_cmd_compile_only_builds_just_the_named_tests` | `--only` builds just the named tests and the manifest lists only them. |
| `tests/test_cli_compile.py::test_cmd_compile_only_rejects_an_unknown_test` | `--only` with a name that does not exist exits with an error. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | The same tests compile for simulation. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_uses_the_verilog_format_when_configured` | `sim.hex_format: verilog` writes the `objcopy` layout. |
| `tests/test_compiler_hex.py::test_elf_to_verilog_hex_keeps_the_real_word_address` | An image linked at `0x800` starts at `@00000200` with no zero padding. |
| `tests/test_compiler_libc.py::test_libc_flags_defaults_to_no_libc` | Without `toolchain.libc`, tests link with `-nostdlib`. |
| `tests/test_compiler_libc.py::test_libc_flags_picolibc_keeps_sections_the_link_script_does_not_reach` | `picolibc` selects the specs and turns garbage collection of sections off. |
| `tests/test_compiler_libc.py::test_libc_flags_rejects_an_unknown_library` | An unknown value raises an error naming the key. |
| `tests/test_compiler_libc.py::test_picolibc_provides_libc_functions` | A test calling `strlen` links with `picolibc` (skipped without a GCC configured with picolibc). |
| `tests/test_compiler_libc.py::test_no_libc_leaves_libc_functions_undefined` | The same test fails to link with `none` (skipped without a GCC configured with picolibc). |
| `tests/test_platform_runtime.py::test_compile_needs_no_crt0_or_linker_script` | With a specs file, a test compiles and links with no `crt0` and no linker script: `_start` is at the flash base and the boot memory's routine at its fixed address. |
| `tests/test_platform_runtime.py::test_cmd_compile_builds_every_kind_and_the_goldens` | A C test, a C memory test, a test that returns from `main`, one with initialized data and an assembly test compile; Spike generates the golden from the image built with the stand-in. |
| `tests/test_platform_runtime.py::test_cmd_spike_run_passes_programs_that_return_from_main` | The same tests pass under Spike, including the ones that return from `main` and the one checking `.data`, `.bss` and a constant. |
| `tests/test_platform_runtime.py::test_cmd_compile_hex_places_the_image_at_the_flash_base` | The simulation image starts at the flash base. |
| `tests/test_compiler_cxx.py::test_cxx_with_picolibc_is_on` | `cxx: true` with picolibc or with a specs file turns C++ on; without picolibc, or with a non-boolean, it is refused. |
| `tests/test_compiler_cxx.py::test_the_gxx_is_the_gcc_with_the_name_changed` | The `g++` comes from the `gcc` name, or from `toolchain.gxx`. |
| `tests/test_compiler_cxx.py::test_cxx_flags_use_the_cpp_specs_and_linker_script` | The flags carry `picolibcpp.specs` and `picolibcpp.ld`, unless the project has a linker script. |
| `tests/test_compiler_cxx.py::test_the_library_of_another_variant_is_refused` | The `libstdc++.a` of the default variant, which the driver returns for another variant, does not count. |
| `tests/test_compiler_cxx.py::test_a_variant_without_the_library_is_refused_by_name` | The refusal names the variant and says the toolchain needs `libstdc++`. |
| `tests/test_compiler_cxx.py::test_a_cxx_source_refuses_a_project_crt0` | `paths.crt0` with C++ is refused before any compiler runs. |
| `tests/test_compiler_cxx.py::test_c_extras_drop_the_flags_only_cpp_takes` | The C sources of a C++ test are compiled without the C++-only flags. |
| `tests/test_compiler_cxx.py::test_discovery_finds_cc_and_cpp_tests` | A folder with `src.cc` or `src.cpp` is a test. |
| `tests/test_cxx_generate.py::test_cxx_specs_register_the_unwind_frames` | The specs file with `cxx: true` links `crtbegin` and `crtend` and picks the `crt0` outright. |
| `tests/test_cxx_generate.py::test_cxx_false_is_the_c_specs_file` | With `cxx` false the specs file is identical to the C one. |
| `tests/test_cxx_generate.py::test_syscalls_are_the_stubs_the_libstdcxx_needs` | `generate.syscalls` writes `getentropy`, `read`, `open` and `close`, each with `ENOSYS`. |
| `tests/test_cxx_generate.py::test_syscalls_are_for_cxx_only` | `generate.syscalls` without `cxx: true` in some specs file is refused. |
| `tests/test_cxx_runtime.py::test_cxx_programs_run` | A global constructor, a virtual call with `new` and `delete`, `std::array` and `std::vector` pass in Spike on `rv32i` and `rv32im` (skipped without a toolchain with `libstdc++`). |
| `tests/test_cxx_runtime.py::test_throw_and_catch_run_the_destructors` | A `throw` is caught and destroys the locals, through the frames `crtbegin` registers. |
| `tests/test_cxx_runtime.py::test_no_exceptions_no_rtti_runs` | `-fno-exceptions -fno-rtti` still links and runs. |

## Usage

Not its own CLI subcommand: it's what `compile` (see the top-level [README](../../../README.en.md#usage)) runs once per discovered test, before handing the result to [`bin_to_image`](bin_to_image.md) (for `.mif`/`.hex`), [`c_to_asm`](c_to_asm.md) (for `.S` inspection), or [`golden_generator`](golden_generator.md) (for a `memory`-kind C test's auto-generated golden).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
