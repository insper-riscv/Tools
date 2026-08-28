# Creating a RISC-V test in C

## Where it goes

Create a folder under the consuming project's `paths.c_dir`
(typically `c/`), named for what the test does, containing a
`src.c`:

```
c/
└── example-add/
    └── src.c
```

`riscv-tools compile` picks up every `<c_dir>/<name>/src.c` folder
automatically — the folder name becomes the test's name in the
manifest; there's nothing else to register.

## Header comments

Three optional `//` comments at the top of `src.c` configure how
`compiler` (see `riscv_tools/compiler/headers.py`) builds and runs it:

```c
// RV32_EXT: M          // extensions ADDED to the implicit rv32i base.
// RV32_EXT: M,A        // order doesn't matter, "A,M" also becomes rv32ima.
// RV32_TEST_KIND: unit          // default. Checked via the PASS/FAIL
                                  // mailbox only. Builds for both real
                                  // hardware and sim.
// RV32_TEST_KIND: memory        // also dumps the whole RAM and compares
                                  // it against manifest.json (see below).
                                  // Real hardware only — sim_runner
                                  // doesn't verify RAM contents, so
                                  // `compile --emit hex` skips these.
// RV32_TIMEOUT_S: 5             // real tests only, how long the
                                  // orchestrator waits for this test's
                                  // mailbox before falling back to a full
                                  // reprogram+retry. Defaults to
                                  // quartus.default_timeout_s. Keep simple
                                  // unit tests low; give slower/memory
                                  // tests more.
```

## Writing the test

```c
// c/example-mem/src.c
#include "rv32_test.h"

int main(void) {
    volatile unsigned int *buf = (volatile unsigned int *)0x10;
    buf[0] = 0x11111111;

    if (buf[0] == 0x11111111) {
        RV32_PASS();
    } else {
        RV32_FAIL();
    }
}
```

`rv32_test.h` is generated from your `config.yaml`'s
`memory.mailbox_addr` — don't hand-write it, generate (or regenerate,
after changing that address) with:

```bash
uv run riscv-tools --config <project>/config.yaml generate-header
```

Writes to `<paths.include_dir>/rv32_test.h` by default (`--out` to
override). `rv32_wait_restart` itself still comes from your project's
own `crt0.S` — this package only owns the mailbox side.

Avoid `(volatile unsigned int *)0x0` — GCC treats a literal null
pointer as undefined behavior and may optimize the whole access away
regardless of `volatile`. Pick a nonzero address for anything at the
start of RAM/ROM.

## `unit` vs `memory` tests

- `unit` (the default): passing means the mailbox reads PASS. Good
  enough when the test can fully judge itself with an `if`. Builds
  for both `compile --emit mif` (real) and `--emit hex` (sim).
- `memory`: also requires `c/<name>/manifest.json` — a map of byte
  address (hex string) to expected byte value (0-255), next to
  `src.c`:

  ```
  c/
  └── example-mem/
      ├── src.c
      └── manifest.json
  ```

  ```json
  {
    "0x00000010": 17,
    "0x00000011": 17
  }
  ```

  `compiler` fails fast at compile time if a `memory` test is missing
  its `manifest.json`. Write it by hand, or generate it by running the
  compiled ELF under Spike instead of guessing the expected bytes.

  Easiest: declare the results as one C global and point
  `generate-golden` at its name — the address and size are both
  resolved automatically from the ELF's symbol table (`nm -S`), no
  address arithmetic required:

  ```c
  volatile unsigned int results[3];
  ```

  ```bash
  uv run riscv-tools --config <project>/config.yaml generate-golden \
      build/real/example-mem.elf --march rv32im --symbol results \
      --out c/example-mem/manifest.json
  ```

  `--symbol` only works for a sized data object — a compiler emits
  accurate size info for C globals automatically, but a hand-written
  asm label needs an explicit `.size name, . - name` directive to get
  one (plain labels don't get it for free). If that's inconvenient,
  `--start`/`--end` (explicit byte addresses) still work exactly as
  before — the two forms are mutually exclusive.

  ```bash
  uv run riscv-tools --config <project>/config.yaml generate-golden \
      build/real/example-mem.elf --march rv32im --start 0x10 --end 0x20 \
      --out c/example-mem/manifest.json
  ```

  See [generating-a-golden.md](generating-a-golden.md) — this
  requires `vendor/riscv-isa-sim` built first (`golden_generator.setup()`).

  `memory` tests build for `--emit mif` (real) only — `compile --emit
  hex` skips them, since `sim_runner` only ever checks the PASS/FAIL
  mailbox, never RAM contents; building one for sim would silently
  under-verify it (a wrong computed value would still report PASS)
  instead of catching the mistake.

## Building, inspecting, running

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # real/FPGA, every test
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # sim, unit tests only
uv run riscv-tools --config <project>/config.yaml compile --emit asm   # inspect codegen (gcc -S)
uv run riscv-tools --config <project>/config.yaml run                  # real hardware suite
```

See [creating-an-asm-test.md](creating-an-asm-test.md) for writing a
test directly in RISC-V assembly instead — e.g. to pin down an exact
addressing mode a compiler might not choose on its own.
