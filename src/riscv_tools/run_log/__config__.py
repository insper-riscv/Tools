"""Defaults for the persistent per-kind run-log history.

Overridden under `run_log:` in a project's config.yaml.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "run_log": {
        # Relative to the project root — a project needing something
        # else (e.g. a build_dir sibling) can override this, but the
        # default is deliberately NOT under paths.build_dir: build/ is
        # something `compile` can wipe/regenerate freely, while a run's
        # own log history is worth keeping around independently of
        # that.
        "logs_dir": "logs",
    },
}
