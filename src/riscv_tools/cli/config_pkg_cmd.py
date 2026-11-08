"""The subcommand that writes the `config_pkg` of a platform."""

import argparse
import sys
from pathlib import Path

from riscv_tools.cli.common import project_root
from riscv_tools.memory_map import load_platform
from riscv_tools.memory_map.config_pkg import parse_overrides, render_variant


def cmd_generate_config_pkg(args: argparse.Namespace) -> None:
    """Implement `riscv-tools generate-config-pkg`.

    Writes the `config_pkg` of the platform, or of a variant of it set
    with `--set NAME=VALUE` (for the formal proof and for the matrix of
    profiles), to `--output` or, without it, to the standard output.
    Doesn't touch args.config: it only reads the platform file.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.platform, args.set, args.output
        and args.root.

    Returns
    -------
    None
        Writes the package; exits the process with status 1 when the
        platform or the variant is inconsistent.
    """
    root = project_root(args)
    platform_file = Path(args.platform)
    if not platform_file.is_absolute():
        platform_file = root / platform_file
    try:
        overrides = parse_overrides(args.set or [])
        text = render_variant(
            load_platform(platform_file), platform_file, root, overrides
        )
    except ValueError as error:
        print(f"ERROR {error}", file=sys.stderr)
        sys.exit(1)
    if not args.output:
        sys.stdout.write(text)
        return
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"generated: {output}")
