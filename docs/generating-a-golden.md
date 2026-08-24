# Generating a golden JSON via Spike

A `RV32_TEST_KIND: memory` test needs a golden JSON — the expected
byte value at each address `mem_validator.compare` checks after the
test runs (see [creating-a-c-test.md](creating-a-c-test.md#unit-vs-memory-tests)).
Instead of working out those values by hand, `golden_generator` runs
the compiled test under Spike (the RISC-V reference simulator,
`vendor/riscv-isa-sim`) and reads them back directly from simulated
memory.

## How it works

Your project's `crt0.S`/`link.ld` define `tohost`/`fromhost` (HTIF —
Host-Target InterFace, the standard convention Spike/`riscv-tests`
use) and translate the mailbox's PASS/FAIL value into a write to
`tohost` once a test finishes (see the HTIF section of your project's
own docs, or [creating-an-asm-test.md](creating-an-asm-test.md) if
you're writing the test in assembly).

`golden_generator.generate_golden`:

1. Resolves `tohost`'s address from the compiled ELF's symbol table
   (`nm`).
2. Runs `spike -d --debug-cmd=<script>` — Spike's interactive debug
   console, scripted via a command file rather than piped to stdin
   (spike's console is written for an interactive TTY and doesn't
   reliably detect EOF on a pipe).
3. The script tells Spike to run *while* `tohost` reads 0, i.e. stop
   the instant the test signals it's done — regardless of whether it
   passed or failed, since either writes a nonzero value.
4. Reads back the requested byte range and returns it as
   `{byte_address: byte_value}`.

This never touches real hardware — it's a full software simulation,
useful specifically because it's fast and doesn't need a board or a
JTAG cable connected.

## Building Spike

`vendor/riscv-isa-sim` needs to be compiled once before
`generate-golden` can run. `golden_generator.setup()` does this for
you:

```python
from riscv_tools import golden_generator

golden_generator.setup()
```

- If `emulator.spike_bin` (default `"spike"`) already resolves to a
  runnable binary — on `PATH`, or an existing file — `setup()` leaves
  it alone and does nothing.
- Otherwise it checks `device-tree-compiler` (`dtc`) is installed —
  the one dependency Spike's `./configure` hard-fails without — and
  builds `vendor/riscv-isa-sim` if it hasn't been built already.
- Raises `FileNotFoundError` if the submodule was never checked out:
  run `git submodule update --init --recursive` first.

Run `golden_generator.update()` after pulling a change that moves the
`vendor/riscv-isa-sim` submodule pin — it rebuilds only if the
checked-out commit has actually moved since the last build, so it's
cheap to call unconditionally (e.g. in a setup script that runs on
every checkout).

See the top-level README's `golden_generator` section for the full
dependency list, manual build steps, and the `RISCV_ISA_SIM_DIR`
environment variable (for pointing at a CI cache directory instead of
this repo's own submodule checkout).

## Generating a golden JSON

Once Spike is built:

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # produces the .elf

uv run riscv-tools --config <project>/config.yaml generate-golden \
    build/real/my_test.elf \
    --march rv32im \
    --start 0x10 --end 0x20 \
    --out tests/c/real/golden/my_test.json
```

- `--march` should match the test's own march (the `RV32_EXT` header,
  resolved the same way `compile` resolves it — see
  [creating-a-c-test.md](creating-a-c-test.md#header-comments)).
- `--start`/`--end` are byte addresses (hex or decimal both work) —
  the half-open range `[start, end)` to snapshot. `end - start` must
  be a multiple of 4.
- `--out` is where the golden JSON gets written, in the exact format
  `mem_validator.compare` expects.

The resulting file is a plain JSON `{hex byte address: int byte
value}` map — safe to check in, and to hand-edit afterward if you
need to (e.g. to intentionally relax a check).

## Verifying it works on your setup

`tests/test_generate_golden.py` (in this package's own repo) is a
real end-to-end test of this whole path: it compiles two tiny fixture
programs (one C, one hand-written asm — see
`tests/fixtures/htif_min/`), runs them through `generate_golden`
against a real built Spike, and checks the bytes that come back are
exactly right, little-endian order included. Run it yourself to
confirm your Spike build works before trusting a golden it produces:

```bash
uv sync --group dev
uv run pytest tests/test_generate_golden.py -v
```

It skips automatically (not fails) if `spike` or the RISC-V GCC
toolchain aren't available.
