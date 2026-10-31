# Creating a GitHub Actions workflow per task

`riscv-tools` doesn't ship a single "the" CI workflow: different tasks need different runners and different triggers, and bundling them into one workflow makes each slower and harder to reason about. Split by task instead: one workflow per concern, each with the trigger and runner that actually fits it.

| Task | Needs | Typical trigger |
|---|---|---|
| Simulation-only tests | The `ci-elf` image (GHDL, RISC-V GCC, Spike, uv, Python and cocotb) on a GitHub-hosted runner | Every push/PR |
| Real-hardware tests | A self-hosted runner with Quartus, the board and the JTAG cable, running the `ci-elf` image in a container | Push to the main branch, or `workflow_dispatch` |
| Regenerating goldens | The `ci-elf` image (GCC and Spike) on a GitHub-hosted runner, no hardware | `workflow_dispatch`, on demand |

## 1. The CI images

The images come from [insper-riscv/Infra](https://github.com/insper-riscv/Infra) and already carry everything a job needs, so a workflow installs no toolchain and no `uv`: it runs the job inside the image.

| Image | Adds | Use it for |
|---|---|---|
| `ghcr.io/insper-riscv/ci-vhdl` | GHDL, Yosys, `uv`, Python 3.14, cocotb | Jobs that only simulate VHDL |
| `ghcr.io/insper-riscv/ci-elf` | The RISC-V GCC with picolibc and Spike | Jobs that compile tests and run `riscv-tools` |
| `ghcr.io/insper-riscv/ci-act4` | The ACT4 dependencies | `certify` |

`latest` is the last publication. For a reproducible run, use the `sha-<commit>` tag of the publication you want.

The consuming project depends on this repository as a submodule (normally `tools/Tools`) and lists `riscv-tools` as an editable path dependency in its own `pyproject.toml`, so `uv sync` at the root of the project installs everything and `uv run riscv-tools` works from there. Every job below starts the same way:

```yaml
runs-on: ubuntu-26.04
container:
  image: ghcr.io/insper-riscv/ci-elf:latest
steps:
  - uses: actions/checkout@v7
    with:
      submodules: true
  - run: uv sync
```

`submodules: true` is what brings this repository in. If the project's config refers to sibling repositories (such as `../Core`), the job also clones them next to the checkout, since a bare CI checkout has no parent directory with them.

## 2. Simulation-only tests

The cheapest to run: no hardware and no self-hosted runner. `sim` drives cocotb/GHDL against the `.hex` of every test, polling the same `tohost` convention as real hardware (see [configuration.md](configuration.md#sim) for the `sim:` keys). Your project still supplies its own `sim.test_module`, the cocotb test that knows the real VHDL signal names of the design under test.

```yaml
name: sim
on: [push, pull_request]

concurrency:
  group: sim-${{ github.ref }}
  cancel-in-progress: true

jobs:
  sim:
    runs-on: ubuntu-26.04
    container:
      image: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - uses: actions/checkout@v7
        with:
          submodules: true
      - run: uv sync

      - run: uv run riscv-tools --config config.yaml generate-header
      - run: uv run riscv-tools --config config.yaml compile --emit hex
      - run: uv run riscv-tools --config config.yaml sim

      - name: Upload waveforms
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: waveforms
          path: "**/*.ghw"
          if-no-files-found: ignore
```

`compile` also generates the golden of every C `memory` test under Spike, which is why this job needs the `ci-elf` image and not only `ci-vhdl`.

## 3. Real-hardware tests

Needs a self-hosted runner with Quartus, the board and the JTAG cable. Its setup is in the `RUNNER_SETUP.md` and `QUARTUS_INSTALL.md` guides of Infra. The host provides only Quartus, Docker, the JTAG server (`jtagd`) and the runner: the job runs everything else in the `ci-elf` image, with Quartus mounted read-only.

The `concurrency` block matters here. Canceling a run in the middle of a `quartus_pgm` leaves the board half programmed, so every ref shares one group and `cancel-in-progress` stays `false`. A manual run also asks for a `confirm` input that must equal a repository secret, as a second check on top of the write access that already gates who can trigger it.

```yaml
name: real
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      confirm:
        description: "Value of the FPGA_RUN_SECRET secret"
        required: true

concurrency:
  group: physical-fpga
  cancel-in-progress: false

jobs:
  real:
    runs-on: [self-hosted, quartus, fpga]   # the labels your runner was registered with
    env:
      IMAGE: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - name: Authorize manual run
        if: github.event_name == 'workflow_dispatch'
        run: |
          [ "${{ inputs.confirm }}" = "${{ secrets.FPGA_RUN_SECRET }}" ] \
            || { echo "::error::confirmation does not match"; exit 1; }

      - uses: actions/checkout@v7
        with:
          submodules: true

      - run: docker pull "$IMAGE"

      # jtagconfig starts the host's jtagd if none is running.
      - name: Start the JTAG server of the host
        run: /opt/altera_lite/25.1std/quartus/bin/jtagconfig

      - name: Build, program and run
        run: |
          docker run --rm --network host --userns=host \
            --user "$(id -u):$(id -g)" -e HOME=/tmp/h \
            -v /opt/altera_lite:/opt/altera_lite:ro \
            -v "$PWD:/workspace" -w /workspace "$IMAGE" bash -c '
              export PATH=/opt/altera_lite/25.1std/quartus/bin:$PATH
              uv sync
              uv run riscv-tools --config config.yaml generate-header
              uv run riscv-tools --config config.yaml compile --emit mif
              uv run riscv-tools --config config.yaml run'
```

| Option | What it does |
|---|---|
| `-v /opt/altera_lite:/opt/altera_lite:ro` | The Quartus installation of the host, read-only; the image has none |
| `--network host` | The `jtagd` of the host listens on `localhost:1309`, and the programmer inside the container connects to it there |
| `--user "$(id -u):$(id -g)"` and `-e HOME=/tmp/h` | The files the build writes belong to the runner user, and Quartus gets a writable home |
| `--userns=host` | Keeps `--network host` valid on a Docker daemon that remaps users, and does nothing on one that does not |

## 4. Regenerating goldens

On demand only: `workflow_dispatch`, not on every push. It needs Spike and the RISC-V GCC but no hardware, so it runs on a GitHub-hosted runner inside the `ci-elf` image.

C `memory` tests need nothing here, since `compile` regenerates their golden every time. The goldens to regenerate are the versioned ones that sit next to an assembly test's `src.S` (see [creating-an-asm-test.md](creating-an-asm-test.md)). A gap the CLI doesn't hide: `generate-golden` needs `--start`/`--end` for the byte range to capture, and nothing records it for a *new* test, so you still choose it by hand the first time. What CI can fully automate is **re**generating the existing goldens (for example after an RTL or toolchain change, to confirm the expected values did not move), reading the address range from the existing golden JSON itself:

```yaml
name: regenerate-goldens
on: workflow_dispatch

jobs:
  regenerate:
    runs-on: ubuntu-26.04
    container:
      image: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - uses: actions/checkout@v7
        with:
          submodules: true
      - run: uv sync

      - run: uv run riscv-tools --config config.yaml compile --emit mif

      - name: Regenerate every existing golden
        run: |
          for golden in asm/*/golden.json; do
            [ -f "$golden" ] || continue
            name=$(basename "$(dirname "$golden")")
            elf="build/real/$name.elf"
            march=$(jq -r --arg n "$name" '.[] | select(.name == $n) | .march' build/real/manifest.json)
            # The keys always have the same width, zero-padded (the
            # format golden JSON files are written in), so their
            # lexicographic min/max is also the numeric one. Only the
            # exclusive "+1" at the end needs real arithmetic, which
            # bash does natively on 0x literals.
            start=$(jq -r 'keys | min' "$golden")
            max_key=$(jq -r 'keys | max' "$golden")
            end=$(printf '0x%X' $((max_key + 1)))
            uv run riscv-tools --config config.yaml generate-golden "$elf" \
                --march "$march" --start "$start" --end "$end" --out "$golden"
          done

      # then diff/commit/open a PR with what changed, using your own git
      # steps: regenerating on its own never pushes anything
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
