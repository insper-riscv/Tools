# `run_log`

Rotates and tees a run's full console output into a persistent per-kind log history. `run`/`sim`/`certify` (see [`orchestrator`](orchestrator.md), [`sim_runner`](sim_runner.md), [`certify`](certify.md)) print a lot of progress output that's otherwise gone the moment a terminal scrolls past it or the session ends; this module writes everything to `<root>/<run_log.logs_dir>/<kind>/latest.log` too, so there's always a `tail -f` target for the run in progress plus a rotated history of every run before it.

A stale `latest.log` from a previous run is archived under its own recorded start timestamp before a new one begins, rather than silently overwritten.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `run_log.logs_dir` | Where log history is kept, relative to the project root (default `"logs"`). Deliberately not under `paths.build_dir`, since `compile` can wipe/regenerate the build directory freely, while a run's own log history is worth keeping around independently of that. |

## Usage

Not its own CLI subcommand: automatic on every `run`/`sim`/`certify` invocation. Nothing to configure to get it; only `run_log.logs_dir` is worth overriding, and only if a project wants log history somewhere other than the default.
