# Finding Fmax (clock frequency sweep)

## What this is for

Fmax is the highest clock frequency your design actually works at on
real hardware — not the number Quartus' static timing analysis
*predicts*, but an empirical answer from actually running the board at
increasing frequencies until it breaks. Timing analysis tells you
whether a design *should* close timing at a given frequency; running
it is the only way to know it actually computes the right answer up
there, since voltage/temperature/silicon variation and any timing
model gaps aren't captured by static analysis alone.

`riscv-tools freq-sweep` automates this: it repeatedly edits your
project's PLL to a candidate frequency, does a full recompile +
reprogram (a clock frequency is baked in at synthesis time, so there's
no faster JTAG-reload shortcut the way there is for same-frequency
tests — see [configuration.md](configuration.md#quartus)), waits for
the program to run, dumps RAM, and compares it against a golden JSON —
either sweeping linearly across a range or binary-searching for the
breaking point.

This is the generalized, config-driven version of a workflow that
started as a project-specific script (a fixed PLL file, fixed
parameter names, fixed golden path); `freq_sweep`/`orchestrator` here
read everything project-specific from your `config.yaml` instead.

## Requirements

- A `freq_sweep:` config section — see the [configuration
  reference](configuration.md#freq_sweep--only-needed-for-riscv-tools-freq-sweep)
  for every key. At minimum you need `pll_file` pointing at your
  project's PLL source; the parameter-name templates
  (`freq_param_template`/`phase_param_template`) default to Quartus'
  `altpll` megafunction convention (`output_clock_frequencyN`/
  `phase_shiftN`) and `phase_count` defaults to `1` (a plain
  single-phase PLL) — override only if your PLL doesn't match.
- A fixed test `.mif` and a matching golden JSON — the *same* program
  is baked into ROM and checked at every candidate frequency, so pick
  (or write) one that exercises enough of the design to actually
  reveal timing failures (a program that barely touches memory won't
  tell you much). See [creating-a-c-test.md](creating-a-c-test.md#unit-vs-memory-tests)
  and [generating-a-golden.md](generating-a-golden.md) if you don't
  already have one.
- The same real-hardware setup `run`/`program` need: a board connected
  over JTAG, `quartus_sh`/`quartus_pgm` on `PATH`, and `quartus.*`/
  `memory.*` configured (see [configuration.md](configuration.md)).

## How it works

For each candidate frequency, `orchestrator.run_freq_sweep_at`:

1. Rewrites `pll_file` in place (`freq_sweep.set_pll_freq`) — for each
   of `phase_count` clock outputs, replaces the frequency parameter
   with the new value and recomputes that output's phase offset so
   multi-phase outputs stay proportionally spaced at the new
   frequency (0°, 120°, 240° for a 3-way PLL, evenly spaced for any
   other `phase_count`).
2. Runs a full recompile + program (`quartus_program.full_reconfigure`
   — the same slow path `run`'s JTAG-reload fallback and `program`
   use), with the fixed test `.mif` baked in as the ROM's init_file.
3. Waits `quartus.program_wait_seconds`.
4. Dumps the whole RAM (`ram_dump.dump_ram`) and compares it against
   the golden JSON (`mem_validator.compare`).

A compile/program failure or a RAM-dump failure at one candidate
frequency is caught and recorded as that candidate's status rather
than aborting the whole sweep — one bad frequency (e.g. one that fails
to close timing badly enough that programming itself glitches)
shouldn't stop you from finding out about the frequencies around it.

## Running a sweep

```bash
# Linear: test every frequency from --start to --stop, in --step
# increments. Stops early once 3 candidates in a row fail — past that
# point Fmax has likely already been found, so continuing just burns
# more full-reconfigure cycles for no new information.
uv run riscv-tools --config <project>/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json \
    --start 1 --stop 30 --step 2

# Binary search: converges on the boundary between --low (must PASS)
# and --high (must FAIL) faster than a linear sweep, at the cost of
# not showing you the shape of the pass/fail curve below the boundary.
uv run riscv-tools --config <project>/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json \
    --binary --low 1 --high 50
```

Both modes write every candidate's result to `--out` (default
`<build_dir>/freq_sweep/freq_sweep_results.json`) as they go, and
print a summary — highest passing frequency for a linear sweep, the
converged `[lo, hi]` bracket for binary search:

```json
[
  { "freq_mhz": 1.0, "status": "pass" },
  { "freq_mhz": 3.0, "status": "pass" },
  { "freq_mhz": 5.0, "status": "fail" }
]
```

`status` is one of `pass`, `fail` (RAM dump didn't match the golden),
`program_fail` (compile or JTAG programming itself failed), or
`dump_fail` (programming succeeded but the RAM dump failed).

Binary search's convergence tolerance is fixed at 0.5 MHz via the CLI
— call `orchestrator.run_freq_sweep_binary(..., tolerance=...)`
directly from Python if you need a tighter or looser bracket.

## Interpreting the result

- **Linear sweep**: the highest frequency with `status: "pass"` is
  your empirical Fmax for *this* board, *this* bitstream, and
  whatever ambient conditions it happened to run under.
- **Binary search**: the final `[lo, hi]` bracket (`lo` PASS, `hi`
  FAIL) — Fmax is somewhere in between; narrow it further with a
  tighter `tolerance` if you need more precision.
- If the upper bound you gave (`--stop` or `--high`) still passes, the
  real Fmax is higher than you searched — rerun with a wider range.

Voltage and temperature aren't controlled during a sweep, so the
result is empirical to that specific board at whatever conditions it
happened to run under — not a formal timing-closure guarantee, and not
necessarily reproducible bit-for-bit on a different board of the same
part.
