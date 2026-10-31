"""Tests for cli_filters."""

import argparse
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from riscv_tools import boot_rom, cli, run_log, sim_runner
from riscv_tools.cli import (
    common,
    filter_manifest,
    suite_cmd,
)

MANIFEST_PATH = Path("build/manifest.json")
MANIFEST: list[dict[str, Any]] = [
    {"name": "alpha"},
    {"name": "uart-echo"},
    {"name": "beta"},
    {"name": "uart-tx"},
]


def _names(entries: list[dict[str, Any]]) -> list[str]:
    return [str(entry["name"]) for entry in entries]


def test_manifest_filter_without_options_preserves_order() -> None:
    """Manifest filter without options preserves order."""
    selected = filter_manifest(MANIFEST, MANIFEST_PATH, [], [])

    assert _names(selected) == ["alpha", "uart-echo", "beta", "uart-tx"]


def test_manifest_filter_only_accepts_repeated_comma_separated_groups() -> (
    None
):
    """Manifest filter only accepts repeated comma separated groups."""
    selected = filter_manifest(
        MANIFEST,
        MANIFEST_PATH,
        [" beta,alpha ", "beta"],
        [],
    )

    assert _names(selected) == ["beta", "alpha"]


def test_manifest_filter_exclude_preserves_remaining_manifest_order() -> None:
    """Manifest filter exclude preserves remaining manifest order."""
    selected = filter_manifest(
        MANIFEST,
        MANIFEST_PATH,
        [],
        ["uart-echo", "uart-tx"],
    )

    assert _names(selected) == ["alpha", "beta"]


def test_manifest_filter_exclude_wins_over_only() -> None:
    """Manifest filter exclude wins over only."""
    selected = filter_manifest(
        MANIFEST,
        MANIFEST_PATH,
        ["beta,alpha"],
        ["beta"],
    )

    assert _names(selected) == ["alpha"]


@pytest.mark.parametrize("option", ["only", "exclude"])
def test_manifest_filter_rejects_unknown_names(
    option: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Manifest filter rejects unknown names."""
    only = ["missing"] if option == "only" else []
    exclude = ["missing"] if option == "exclude" else []

    with pytest.raises(SystemExit) as exc_info:
        filter_manifest(MANIFEST, MANIFEST_PATH, only, exclude)

    assert exc_info.value.code == 1
    assert f"--{option} names not found" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["only", "exclude"])
@pytest.mark.parametrize("group", ["", " , "])
def test_manifest_filter_rejects_an_explicit_empty_filter(
    option: str,
    group: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Manifest filter rejects an explicit empty filter."""
    only = [group] if option == "only" else []
    exclude = [group] if option == "exclude" else []

    with pytest.raises(SystemExit) as exc_info:
        filter_manifest(MANIFEST, MANIFEST_PATH, only, exclude)

    assert exc_info.value.code == 1
    assert (
        f"--{option} requires at least one test name"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    ("manifest", "exclude"),
    [
        ([], []),
        (MANIFEST, ["alpha,uart-echo,beta,uart-tx"]),
    ],
)
def test_manifest_filter_rejects_an_empty_selection(
    manifest: list[dict[str, Any]],
    exclude: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Manifest filter rejects an empty selection."""
    with pytest.raises(SystemExit) as exc_info:
        filter_manifest(manifest, MANIFEST_PATH, [], exclude)

    assert exc_info.value.code == 1
    assert "No tests selected" in capsys.readouterr().err


def test_cmd_run_rejects_bad_filter_before_opening_jtag(
    tmp_path: Path,
) -> None:
    """Cmd run rejects bad filter before opening jtag."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST))
    args = argparse.Namespace(
        config=tmp_path / "config.yaml",
        root=tmp_path,
        manifest=str(manifest_path),
        only=[],
        exclude=["missing"],
    )
    cfg = {
        "paths": {"build_dir": "build"},
        "run_log": {"logs_dir": "logs"},
    }

    with (
        mock.patch.object(common, "load_config", return_value=cfg),
        mock.patch.object(run_log, "start"),
        mock.patch.object(suite_cmd, "jtag_link") as link,
        pytest.raises(SystemExit),
    ):
        cli.cmd_run(args)

    link.assert_not_called()


def test_cmd_sim_rejects_bad_filter_before_building_boot_rom(
    tmp_path: Path,
) -> None:
    """Cmd sim rejects bad filter before building boot rom."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST))
    args = argparse.Namespace(
        config=tmp_path / "config.yaml",
        root=tmp_path,
        manifest=str(manifest_path),
        only=[],
        exclude=["missing"],
    )
    cfg = {
        "paths": {"build_dir": "build", "boot_rom": "boot_rom.S"},
        "run_log": {"logs_dir": "logs"},
        "sim": {"image": "hex"},
    }

    with (
        mock.patch.object(common, "load_config", return_value=cfg),
        mock.patch.object(run_log, "start"),
        mock.patch.object(boot_rom, "build_boot_rom") as build_boot_rom,
        mock.patch.object(sim_runner, "run_suite") as run_suite,
        pytest.raises(SystemExit),
    ):
        cli.cmd_sim(args)

    build_boot_rom.assert_not_called()
    run_suite.assert_not_called()
