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
automatically: the folder name becomes the test's name in the
manifest; there's nothing else to register.

## Header comments

Three optional `//` comments at the top of `src.c` configure how
[`compiler`](modules/compiler.md) builds and runs the test:

| Header | Meaning |
| :--- | :--- |
| `RV32_EXT: M` | Extensions ADDED to the implicit `rv32i` base. Comma-separated; order doesn't matter (`M,A` and `A,M` both become `rv32ima`). |
| `RV32_TEST_KIND: unit` | Default if omitted. Checked via the PASS/FAIL mailbox only. Builds for both real hardware and sim. See [`unit` vs `memory` tests](#unit-vs-memory-tests) below. |
| `RV32_TEST_KIND: memory` | A `unit` test, expanded: also gets a `results` global checked against golden.json after the mailbox reads PASS. See [`unit` vs `memory` tests](#unit-vs-memory-tests) below. |
| `RV32_TIMEOUT_S: 5` | Real tests only: how long the orchestrator waits for this test's mailbox before falling back to a full reprogram+retry. Defaults to `quartus.default_timeout_s`. Keep simple unit tests low; give slower/memory tests more. |

```c
// RV32_EXT: M
// RV32_TEST_KIND: memory
// RV32_TIMEOUT_S: 5
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
`memory.mailbox_addr`: don't hand-write it, generate (or regenerate,
after changing that address) with:

```bash
uv run riscv-tools --config <project>/config.yaml generate-header
```

Writes to `<paths.include_dir>/rv32_test.h` by default (`--out` to
override). `rv32_wait_restart` itself still comes from your project's
own `crt0.S`: this package only owns the mailbox side.

Avoid `(volatile unsigned int *)0x0`: GCC treats a literal null
pointer as undefined behavior and may optimize the whole access away
regardless of `volatile`. Pick a nonzero address for anything at the
start of RAM/ROM.

## `unit` vs `memory` tests

`memory` is `unit`, expanded, not a separate, unrelated kind: take any
working `unit` test, add a `results` global it writes its answer
into, change the header comment to `memory`, and it's now a `memory`
test. Nothing about its `RV32_PASS()`/`RV32_FAIL()` logic changes.

- `unit` (the default): passing means the mailbox reads PASS. Good
  enough when the test can fully judge itself with an `if`. Builds
  for both `compile --emit mif` (real) and `--emit hex` (sim).
- `memory`: mailbox PASS, **and then** a `results` global is checked
  against golden.json, on both real hardware (a JTAG RAM dump) and
  sim (the same check, done live off the RAM write bus instead, since
  sim has no way to dump a memory array directly; see a project's own
  `sim/test_c_program.py`). A test signaling FAIL, or timing out,
  never reaches that second check at all, the same as a `unit` test
  failing the same way. This is what catches a test that reached
  `RV32_PASS()` with a wrong computed value (e.g. a sum that came out
  off by one): the mailbox alone can't tell "ran to completion" apart
  from "ran to completion and got the wrong answer."

  Unlike an asm memory test (see
  [creating-an-asm-test.md](creating-an-asm-test.md)), a C memory test
  carries **no checked-in golden.json**: declare a `results` global
  instead:

  ```c
  // RV32_TEST_KIND: memory
  #include "rv32_test.h"

  volatile unsigned int results[3];

  int main(void) {
      results[0] = ...;
      results[1] = ...;
      results[2] = ...;
      RV32_PASS();
  }
  ```

  At compile time (both `--emit mif` and `--emit hex`), the golden is
  generated automatically: it resolves `results`' address/size from
  the compiled ELF's symbol table (`nm -S`, same mechanism as
  `generate-golden --symbol`), runs the ELF under Spike (see
  [golden_generator](modules/golden_generator.md)), and writes a fresh
  `<build_dir>/<name>.golden.json`, never a file you write or commit.
  Correctness is validated as "this project's CPU produces the same
  memory contents Spike does for the same program," not against a
  value someone worked out by hand once that can silently go stale
  after an edit. Requires `vendor/riscv-isa-sim` built first (handled
  automatically: see [generating-a-golden.md](generating-a-golden.md)
  for the mechanics if you want to run Spike by hand instead, e.g. to
  debug a mismatch).

  `results` can hold whatever the test wants checked (plain values, a
  small struct, an array); the only requirement is that it's a real,
  sized global (`volatile`, so the compiler can't optimize the writes
  away), not a raw pointer to a hardcoded address.

  Both `compile --emit mif` (real) and `--emit hex` (sim) build and
  fully verify a `memory` test now: the golden compare against Spike
  runs the same way for both, so a wrong computed value is caught on
  the fast per-push GHDL suite, not just once run for real.

## Building, inspecting, running

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # real/FPGA, every test
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # sim, every test
uv run riscv-tools --config <project>/config.yaml compile --emit asm   # inspect codegen (gcc -S)
uv run riscv-tools --config <project>/config.yaml run                  # real hardware suite
uv run riscv-tools --config <project>/config.yaml sim                  # sim suite (cocotb/GHDL)
```

See [creating-an-asm-test.md](creating-an-asm-test.md) for writing a
test directly in RISC-V assembly instead: e.g. to pin down an exact
addressing mode a compiler might not choose on its own.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
