# Creating a GitHub Actions workflow per task

`riscv-tools` doesn't ship a single "the" CI workflow — different
tasks need different runners and different triggers, and bundling
them into one workflow makes each slower and harder to reason about.
Split by task instead: one workflow per concern, each with the
trigger and runner that actually fits it.

| Task | Needs | Typical trigger |
|---|---|---|
| Simulation-only tests | Just the GCC toolchain — any GitHub-hosted runner | Every push/PR |
| Real-hardware tests | A self-hosted runner with the board + JTAG cable attached | Every push/PR, or `workflow_dispatch` if hardware time is scarce |
| Regenerating goldens | The GCC toolchain + a built Spike (no hardware) | `workflow_dispatch`, on demand |

Every job below starts the same way — checking out with submodules
(this repo's `vendor/*` are git submodules) and setting up `uv`:

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      submodules: recursive
  - uses: astral-sh/setup-uv@v3
  - run: uv sync
    working-directory: Tools   # wherever this repo is checked out relative to your project
```

## Simulation-only tests

Cheapest to run: no hardware, no self-hosted runner, just the RISC-V
toolchain, GHDL, and the `sim` extra (cocotb + cocotb-tools — see
[configuration.md](configuration.md#sim--needs-the-sim-extra-uv-sync---extra-sim)
for the `sim:` config keys `sim_runner` needs). `sim_runner`/`riscv-tools
sim` drives cocotb/GHDL against every test's `.hex`, polling the same
PASS/FAIL mailbox convention as real hardware — your project still
supplies its own `sim.test_module` (the cocotb test that knows the
DUT's actual VHDL signal names), `sim_runner` just runs it per test and
collects results.

```yaml
name: sim
on: [push, pull_request]

jobs:
  sim:
    runs-on: ubuntu-latest
    container:
      image: ghdl/ghdl:6.0.0-mcode-ubuntu-24.04   # ships GHDL pre-installed

    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra sim
        working-directory: Tools

      # your own toolchain install step here (riscv32-unknown-elf-gcc on PATH)

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit hex
        working-directory: Tools
      - run: uv run riscv-tools --config ../config.yaml --root .. sim
        working-directory: Tools

      - name: Upload waveforms
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: waveforms
          path: "**/*.ghw"
          if-no-files-found: ignore
```

## Real-hardware tests

Needs a self-hosted runner with the board and JTAG cable physically
attached — see your runner setup docs for how that's configured. The
important CI-specific detail is `concurrency`: the default push-trigger
behavior silently cancels a superseded run, which is dangerous mid
`quartus_pgm` (leaves the board in a partially-programmed state) —
pin `cancel-in-progress: false` so a run always finishes before the
next one starts.

```yaml
name: real
on:
  push:
  workflow_dispatch:

concurrency:
  group: real-${{ github.ref }}
  cancel-in-progress: false

jobs:
  real:
    runs-on: [self-hosted, fpga]   # whatever label your runner registered under
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
        working-directory: Tools

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit mif
        working-directory: Tools
      - run: uv run riscv-tools --config ../config.yaml --root .. run
        working-directory: Tools
```

## Regenerating goldens

On demand only — `workflow_dispatch`, not on every push. Needs a
built Spike, not hardware, so it can run on a normal GitHub-hosted
runner. Cache the Spike build (see
[generating-a-golden.md](generating-a-golden.md)'s `RISCV_ISA_SIM_DIR`
section) so this doesn't rebuild Spike from scratch on every run.

There's a real gap the CLI doesn't paper over: `generate-golden` needs
`--start`/`--end` for the byte range to snapshot, which isn't
recorded anywhere for a *brand-new* test — you still choose that by
hand the first time (see
[creating-a-c-test.md](creating-a-c-test.md#unit-vs-memory-tests)).
What CI *can* fully automate is **re**generating already-existing
goldens — e.g. after an RTL or toolchain change, to confirm the
expected values haven't shifted — by reading each existing golden
JSON's own address range and re-running `generate-golden` over the
same range:

```yaml
name: regenerate-goldens
on: workflow_dispatch

jobs:
  regenerate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
        working-directory: Tools

      - uses: actions/cache@v4
        with:
          path: ${{ runner.temp }}/riscv-isa-sim
          key: riscv-isa-sim-${{ hashFiles('Tools/.git/modules/vendor/riscv-isa-sim/HEAD') }}
      - run: uv run python -c "from riscv_tools import golden_generator; golden_generator.setup()"
        working-directory: Tools
        env:
          RISCV_ISA_SIM_DIR: ${{ runner.temp }}/riscv-isa-sim

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit mif
        working-directory: Tools

      - name: Regenerate every existing golden
        working-directory: Tools
        run: |
          # golden.json only exists next to src.c/src.S for
          # "memory"-kind tests (see creating-a-c-test.md) — every
          # other test has nothing to regenerate here.
          for golden in ../c/*/golden.json ../asm/*/golden.json; do
            [ -f "$golden" ] || continue
            name=$(basename "$(dirname "$golden")")
            elf="../build/real/$name.elf"
            march=$(jq -r --arg n "$name" '.[] | select(.name == $n) | .march' ../build/real/manifest.json)
            # jq has no hex-parsing builtin, but its keys are always
            # zero-padded to the same width (write_golden_json's own
            # format), so lexicographic min/max already equals numeric
            # min/max — only the "+1" for the exclusive end needs real
            # arithmetic, which bash's $(( )) does natively on 0x literals.
            start=$(jq -r 'keys | min' "$golden")
            max_key=$(jq -r 'keys | max' "$golden")
            end=$(printf '0x%X' $((max_key + 1)))
            uv run riscv-tools --config ../config.yaml generate-golden "$elf" \
                --march "$march" --start "$start" --end "$end" --out "$golden"
          done

      # then diff/commit/open a PR with whatever changed, using your
      # own git steps — regenerating on its own never pushes anything
```
