# `mem_validator`

Compares a RAM dump (a `.mif`, one 32-bit word per line, see [`ram_dump`](ram_dump.md)) against a golden JSON of expected byte values. Used for `RV32_TEST_KIND: memory` tests, where the PASS/FAIL mailbox alone isn't enough to prove a test did the right thing: it wrote the right values to memory, not just that it reached its own pass signal.

## Golden JSON format

A flat JSON object mapping byte-address strings to expected byte values (0-255), e.g. `{"0": 18, "1": 52, "2": 86}`. Produced either by hand, checked into the test's own directory, or generated dynamically by [`golden_generator`](golden_generator.md) running the test under Spike.

## Configuration

None: takes the dump path and golden JSON path as direct arguments; no `config.yaml` section of its own.

## Usage

Not its own CLI subcommand: called internally by [`orchestrator`](orchestrator.md) right after [`ram_dump`](ram_dump.md), for every `memory`-kind test in a suite.
