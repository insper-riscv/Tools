# Generating a golden JSON via Spike

## Requirements

Spike and the RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`,
`-objcopy`, `-nm`) on `PATH`, installed as described in
[insper-riscv/Infra](https://github.com/insper-riscv/Infra)
(`GCC_SETUP.md` and `SPIKE_SETUP.md`). This package does not build
either of them.

The Spike has to keep its debug module away from address 0, which the
Infra build does. Without that, Spike aborts at startup with `devices at
[0, 1000) and [0, 10000) overlap` for any target whose ROM starts at
address 0. `generate-golden` runs a one-time probe for this before its
first Spike run and stops with a pointer to `SPIKE_SETUP.md` when it
fails.

A `RV32_TEST_KIND: memory` test needs a golden JSON: the expected
byte value at each address [`mem_validator`](modules/mem_validator.md)
checks after the test runs (see [creating-a-c-test.md](creating-a-c-test.md#unit-vs-memory-tests)).
Instead of working out those values by hand, `golden_generator` runs
the compiled test under Spike (the RISC-V reference simulator) and
reads them back from its memory dump.

## How it works

Your project's `crt0.S`/`link.ld` define `tohost`/`fromhost` (HTIF:
Host-Target InterFace, the standard convention Spike/`riscv-tests`
use) and translate the mailbox's PASS/FAIL value into a write to
`tohost` once a test finishes (see the HTIF section of your project's
own docs, or [creating-an-asm-test.md](creating-an-asm-test.md) if
you're writing the test in assembly).

`generate-golden` takes these steps:

1. Resolves the entry point and `tohost` from the compiled ELF's symbol
   table (`nm`).
2. Copies the ELF and, with `objcopy --add-symbol`, defines
   `begin_signature` and `end_signature` at the requested range, plus
   `fromhost` right after `tohost` when the link script doesn't define
   it (Spike ignores `tohost` without it) and a `tohost` alias when
   `emulator.tohost_symbol` names it differently. The original ELF is
   untouched.
3. Runs `spike --isa=... -m<regions> --disable-dtb --pc=<entry>
   +signature=<file> +signature-granularity=4` on the copy. Spike runs
   until the test writes a nonzero value to `tohost`, whether it
   passed or failed, exits, and writes the range as one 32-bit word per
   line.
4. Converts the words into `{byte_address: byte_value}`, little-endian,
   shifted to be RAM-relative.

The step is bounded by `emulator.timeout_s`: a test that never writes
`tohost` fails the generation instead of hanging it.

This never touches real hardware: it is a full software simulation,
useful specifically because it's fast and doesn't need a board or a
JTAG cable connected.

## Generating a golden JSON

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # produces the .elf

uv run riscv-tools --config <project>/config.yaml generate-golden \
    build/real/my_test.elf \
    --march rv32im \
    --start 0x10 --end 0x20 \
    --out c/my_test/golden.json
```

- `--march` should match the test's own march (the `RV32_EXT` header,
  resolved the same way `compile` resolves it: see
  [creating-a-c-test.md](creating-a-c-test.md#header-comments)).
- `--start`/`--end` are byte addresses (hex or decimal both work):
  the half-open range `[start, end)` to snapshot, rounded up to whole
  32-bit words.
- `--out` is where the golden JSON gets written, in the exact format
  [`mem_validator`](modules/mem_validator.md) expects.

The resulting file is a plain JSON `{hex byte address: int byte
value}` map, safe to check in, and to hand-edit afterward if you
need to (e.g. to intentionally relax a check).

## Verifying it works on your setup

`tests/test_generate_golden.py` (in this package's own repo) is a
real end-to-end test of this whole path: it compiles two tiny fixture
programs (one C, one hand-written asm; see
`tests/fixtures/htif_min/`), runs them through `generate_golden`
against the installed Spike, and checks the bytes that come back are
exactly right, little-endian order included. Run it yourself to
confirm your Spike works before trusting a golden it produces:

```bash
uv sync --group dev
uv run pytest tests/test_generate_golden.py -v
```

It skips automatically (not fails) if `spike` or the RISC-V GCC
toolchain aren't available.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
