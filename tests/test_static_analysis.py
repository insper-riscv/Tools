"""Static code quality gate: ruff, pyright, and deptry must all be clean.

Runs the same checks CI/a human would run by hand, as real subprocess
invocations against this repo's actual source (not a lint-rule unit
test) — so a lint/type/dependency regression fails `pytest`, not just
a separately-remembered `uv run ruff check` step.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Resolved relative to sys.executable rather than left as a bare name
# on PATH — guarantees we run *this* venv's ruff/pyright/deptry (the
# dev-group versions pinned in pyproject.toml), regardless of what
# invoked pytest.
_BIN_DIR = Path(sys.executable).parent


def _tool(name: str) -> str:
    path = _BIN_DIR / name
    return str(path) if path.is_file() else name


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{' '.join(cmd)} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}{proc.stderr}"
        )


def test_ruff_check() -> None:
    _run([_tool("ruff"), "check", "src", "tests"])


def test_ruff_format() -> None:
    _run([_tool("ruff"), "format", "--check", "src", "tests"])


def test_pyright() -> None:
    _run([_tool("pyright")])


def test_deptry() -> None:
    _run([_tool("deptry"), "."])
