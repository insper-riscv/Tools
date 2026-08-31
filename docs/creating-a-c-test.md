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
                                  // it against golden.json (see below).
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
- `memory`: also verifies memory contents, not just the mailbox — but
  unlike an asm memory test (see
  [creating-an-asm-test.md](creating-an-asm-test.md)), a C memory test
  carries **no checked-in golden.json**. Declare a `results` global
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

  At `compile --emit mif` time, `_generate_c_golden` (cli.py) resolves
  `results`' address/size from the compiled ELF's symbol table (`nm
  -S`, same mechanism as `generate-golden --symbol`), runs the ELF
  under Spike (the RISC-V Foundation's own reference simulator —
  `golden_generator.generate_golden`), and writes a fresh
  `build/real/<name>.golden.json` — never a file you write or commit.
  Correctness is validated as "this project's CPU produces the same
  memory contents Spike does for the same program," not against a
  value someone worked out by hand once that can silently go stale
  after an edit. Requires `vendor/riscv-isa-sim` built first (handled
  automatically — see [generating-a-golden.md](generating-a-golden.md)
  for the mechanics if you want to run Spike by hand instead, e.g. to
  debug a mismatch).

  `results` can hold whatever the test wants checked — plain values,
  a small struct, an array — the only requirement is that it's a real,
  sized global (`volatile`, so the compiler can't optimize the writes
  away), not a raw pointer to a hardcoded address.

  Both `compile --emit mif` (real) and `--emit hex` (sim) build a `.c`
  memory test — sim just never runs the RAM check (`sim_runner` only
  ever reads the PASS/FAIL mailbox), so it still catches "this doesn't
  even run to completion" on the fast per-push GHDL suite, while the
  actual computed-values check only happens for real, against Spike,
  on real hardware. An asm memory test's checked-in golden.json is the
  opposite — real-hardware only, `--emit hex` skips it entirely (see
  [creating-an-asm-test.md](creating-an-asm-test.md)) — since there's
  no Spike run backing it to make a sim-time RAM check meaningful.

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
