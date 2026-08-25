# Creating a RISC-V test in assembly

Useful when you need to pin down an exact instruction sequence or
addressing mode that a compiler is free to avoid — e.g. proving
whether `x0` as a load/store base register with a large immediate
behaves correctly, which GCC may or may not choose to emit for an
equivalent C expression.

## Where it goes

A folder under `paths.asm_dir` (typically `asm/`), named for what the
test does, containing a `src.S`:

```
asm/
└── section6-loadstore/
    └── src.S
```

Same convention as C tests (see
[creating-a-c-test.md](creating-a-c-test.md#where-it-goes)) — just
`asm_dir`/`src.S` instead of `c_dir`/`src.c`.

## Header comments

Identical convention to C tests — `RV32_EXT`, `RV32_TEST_KIND`,
`RV32_TIMEOUT_S` — written as `//` comments (GNU `as` accepts C++-style
line comments, not just `#`/`;`). See
[creating-a-c-test.md](creating-a-c-test.md#header-comments) for the
full reference.

## Entry point

`crt0.S` (in the consuming project) calls a symbol named `main` after
`.data`/`.bss` setup — your `.S` file must define exactly that:

```asm
    .section .text
    .globl main
main:
    ...
```

## Signaling PASS/FAIL

`rv32_test.h`'s `RV32_PASS()`/`RV32_FAIL()` are `static inline` C
functions, so a separate `.S` file can't `call` them — there's no
linkable symbol. Write the same two steps by hand instead, using the
consuming project's `memory.mailbox_addr` / `memory.go_flag_addr` (see
its `config.yaml` — commonly `0x3FFC`/`0x3FF8`, right past the end of
usable RAM):

```asm
    // mailbox_addr = 1 (PASS) or 2 (FAIL)
    lui  x15, 0x4
    addi x14, x0, 1            // or 2 for FAIL
    sw   x14, -4(x15)          // mailbox_addr

    // Jump back into crt0.S's restart loop — NOT an infinite spin.
    // This is what lets the orchestrator JTAG-reload the next test
    // onto the same, already-programmed bitstream (see
    // rv32_wait_restart in crt0.S) instead of needing a full
    // recompile+reprogram after every single test.
    j rv32_wait_restart
```

Ending in your own `1: j 1b` spin loop instead of `j
rv32_wait_restart` will make the whole suite hang on the *next* test —
the core never returns to the state the orchestrator expects to
JTAG-reload it from.

## Full example

See `asm/section6-loadstore/src.S` in the consuming project's repo
for a complete worked example (loads a base register, does a
LUI+SW+LW round trip, then signals PASS as above).

## Building, inspecting, running

Same CLI as C tests:

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # every test, real
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # unit-kind only, sim
uv run riscv-tools --config <project>/config.yaml run
```

`compile --emit asm` is a no-op passthrough for `.S` files — they're
already assembly, there's nothing to compile down to.
