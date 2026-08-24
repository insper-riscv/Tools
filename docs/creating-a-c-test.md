# Creating a RISC-V test in C

## Where it goes

Drop a `.c` file into the consuming project's real or sim test
directory (`paths.tests_real_dir` / `paths.tests_sim_dir` in that
project's `config.yaml` — typically `tests/c/real/` and
`tests/c/sim/`). `riscv-tools compile` picks up every `.c`/`.S` file
in that directory automatically; there's nothing else to register.

## Header comments

Three optional `//` comments at the top of the file configure how
`compiler` (see `riscv_tools/compiler/headers.py`) builds and runs it:

```c
// RV32_EXT: M          // extensions ADDED to the implicit rv32i base.
// RV32_EXT: M,A        // order doesn't matter — "A,M" also becomes rv32ima.
// RV32_TEST_KIND: unit          // default. Checked via the PASS/FAIL
                                  // mailbox only.
// RV32_TEST_KIND: memory        // also dumps the whole RAM and compares
                                  // it against a golden JSON (see below).
// RV32_TIMEOUT_S: 5             // real tests only — how long the
                                  // orchestrator waits for this test's
                                  // mailbox before falling back to a full
                                  // reprogram+retry. Defaults to
                                  // quartus.default_timeout_s. Keep simple
                                  // unit tests low; give slower/memory
                                  // tests more.
```

## Writing the test

```c
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

`rv32_test.h` is supplied by the CONSUMING project (it defines
`RV32_PASS`/`RV32_FAIL` against that project's own mailbox address and
`rv32_wait_restart`, from its `crt0.S`) — this package doesn't ship it,
only the tooling that compiles against it.

Avoid `(volatile unsigned int *)0x0` — GCC treats a literal null
pointer as undefined behavior and may optimize the whole access away
regardless of `volatile`. Pick a nonzero address for anything at the
start of RAM/ROM.

## `unit` vs `memory` tests

- `unit` (the default): passing means the mailbox reads PASS. Good
  enough when the test can fully judge itself with an `if`.
- `memory`: also requires `tests/c/real/golden/<name>.json` — a map of
  byte address (hex string) to expected byte value (0-255):

  ```json
  {
    "0x00000010": 17,
    "0x00000011": 17
  }
  ```

  `compiler` fails fast at compile time if a `memory` test is missing
  its golden file. Write it by hand, or generate it by running the
  compiled ELF under Spike instead of guessing the expected bytes:

  ```bash
  uv run riscv-tools --config <project>/config.yaml generate-golden \
      build/real/my_test.elf --march rv32im --start 0x10 --end 0x20 \
      --out tests/c/real/golden/my_test.json
  ```

  See `mem_validator`'s section in the top-level README — this
  requires `vendor/riscv-isa-sim` built first.

## Building, inspecting, running

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # real/FPGA
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # sim
uv run riscv-tools --config <project>/config.yaml compile --emit asm   # inspect codegen (gcc -S)
uv run riscv-tools --config <project>/config.yaml run                  # real hardware suite
```

See [creating-an-asm-test.md](creating-an-asm-test.md) for writing a
test directly in RISC-V assembly instead — e.g. to pin down an exact
addressing mode a compiler might not choose on its own.
