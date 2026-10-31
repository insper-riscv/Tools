"""Helpers shared by the subcommands: config, run log, manifest."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

from riscv_tools import (
    run_log,
)
from riscv_tools.jtag import JtagLink, detect_jtag_hardware
from riscv_tools.settings import load_config


def jtag_link(cfg: dict[str, Any]) -> JtagLink:
    """Build a JtagLink for the connected cable and the chip.

    The chip is the one of the project.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config, uses quartus.jtag_device.

    Returns
    -------
    JtagLink
        A JtagLink with a live-detected hardware_name (see
        jtag.detect_jtag_hardware) and cfg's device_name.
    """
    return JtagLink(
        hardware_name=detect_jtag_hardware(),
        device_name=cfg["quartus"]["jtag_device"],
    )


def start_run(
    args: argparse.Namespace, kind: str
) -> tuple[dict[str, Any], Path]:
    """Load the config, resolve the project root and open the run log.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments (uses args.config and args.root).
    kind : str
        Name of the log directory under run_log.logs_dir.

    Returns
    -------
    tuple[dict[str, Any], Path]
        The loaded config and the project root.
    """
    cfg = load_config(args.config)
    root = project_root(args)
    run_log.start(root, kind, cfg["run_log"]["logs_dir"])
    return cfg, root


def start_certification(
    args: argparse.Namespace, kind: str
) -> tuple[dict[str, Any], Path]:
    """Start a certification run, applying the --extensions override.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments (uses args.extensions as well).
    kind : str
        Name of the log directory under run_log.logs_dir.

    Returns
    -------
    tuple[dict[str, Any], Path]
        The loaded config and the project root.
    """
    cfg, root = start_run(args, kind)
    if args.extensions is not None:
        cfg["act"]["extensions"] = args.extensions
    return cfg, root


def load_manifest(
    args: argparse.Namespace, manifest_dir: Path, emit: str
) -> tuple[Path, list[dict[str, Any]]]:
    """Read the manifest.json of a run, or exit if it is missing.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments (uses args.manifest).
    manifest_dir : Path
        Directory holding the default manifest.json.
    emit : str
        Value of `compile --emit` that writes the manifest, for the
        hint printed when the file is missing.

    Returns
    -------
    tuple[Path, list[dict[str, Any]]]
        The manifest path and its parsed entries.
    """
    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else manifest_dir / "manifest.json"
    )
    if not manifest_path.is_file():
        print(
            f"{manifest_path} not found; run "
            f"`riscv-tools compile --emit {emit}` first",
            file=sys.stderr,
        )
        sys.exit(1)
    manifest: list[dict[str, Any]] = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    return manifest_path, manifest


class _RealRun(NamedTuple):
    """Everything a subcommand needs to run a real-hardware manifest."""

    cfg: dict[str, Any]
    root: Path
    build_dir: Path
    manifest_path: Path
    manifest: list[dict[str, Any]]


def start_real_run(args: argparse.Namespace, kind: str) -> _RealRun:
    """Start a run over the manifest compiled for the board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments (uses args.config, args.root and
        args.manifest).
    kind : str
        Name of the log directory under run_log.logs_dir.

    Returns
    -------
    _RealRun
        The config, project root, real build directory, manifest path
        and manifest entries.
    """
    cfg, root = start_run(args, kind)
    build_dir = root / cfg["paths"]["build_dir"] / "real"
    manifest_path, manifest = load_manifest(args, build_dir, "mif")
    return _RealRun(cfg, root, build_dir, manifest_path, manifest)


def project_root(args: argparse.Namespace) -> Path:
    """Resolve the consuming project's root directory for a subcommand.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    Path
        Path(args.root).resolve() if --root was passed, else the
        current working directory.
    """
    return Path(args.root).resolve() if args.root else Path.cwd()
