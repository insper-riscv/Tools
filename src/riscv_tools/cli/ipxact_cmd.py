"""The subcommands that extract, generate and check IP-XACT files."""

import argparse
import sys

from riscv_tools.cli.common import project_root
from riscv_tools.ipxact import core
from riscv_tools.ipxact.extract import extract
from riscv_tools.ipxact.model import ExtractError


def _fail(problems: list[str], label: str) -> None:
    """Print the problems and exit with status 1 when there are any."""
    if not problems:
        return
    for problem in problems:
        print(f"IPXACT {problem}", file=sys.stderr)
    print(f"{label}: {len(problems)} problem(s)", file=sys.stderr)
    sys.exit(1)


def cmd_ipxact_extract(args: argparse.Namespace) -> None:
    """Implement `riscv-tools ipxact extract`.

    Prints the generics and the ports of every entity of the
    repository, as read from the VHDL (see ipxact.extract.extract).
    Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.root.

    Returns
    -------
    None
        Prints the entities; exits with status 1 when GHDL rejects the
        sources or an entity uses a construct with no IP-XACT form.
    """
    try:
        extraction = extract(project_root(args))
    except ExtractError as error:
        print(f"ipxact extract: {error}", file=sys.stderr)
        sys.exit(2)
    for item in extraction.found:
        entity = item.entity
        print(f"{entity.name} ({item.component}, {entity.source})")
        for generic in entity.generics:
            print(f"  generic {generic.name} := {generic.default}")
        for port in entity.ports:
            limits = "".join(f"({a}:{b})" for a, b in port.vectors)
            print(
                f"  port {port.direction} {port.name} {port.type_name}{limits}"
            )
    _fail(
        [f"{name}: {why}" for name, why in extraction.failures.items()],
        "ipxact extract",
    )


def cmd_ipxact_generate(args: argparse.Namespace) -> None:
    """Implement `riscv-tools ipxact generate`.

    Writes `ipxact/<name>.<version>.component.xml` for every entity of
    the repository and validates what it wrote. With `--check` it writes
    nothing and fails when a stored document differs from the one the
    VHDL gives. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.check and args.root.

    Returns
    -------
    None
        Prints the result; exits with status 1 on any problem.
    """
    root = project_root(args)
    try:
        planned = core.plan(root)
    except ExtractError as error:
        print(f"ipxact generate: {error}", file=sys.stderr)
        sys.exit(2)
    _fail(planned.problems, "ipxact generate")
    if args.check:
        _fail(core.differences(root, planned.documents), "ipxact generate")
        print(f"ipxact OK: {len(planned.documents)} component(s) current")
        return
    names = core.write(root, planned.documents)
    _fail(core.validate(root), "ipxact generate")
    print(f"ipxact: wrote {len(names)} component(s) to {core.OUTPUT}/")


def cmd_ipxact_check(args: argparse.Namespace) -> None:
    """Implement `riscv-tools ipxact check`.

    Fails when an entity has no stored component or has a stale one, a
    stored document differs from the VHDL, or the standard rejects it
    (the schema and the semantic consistency rules of annex B). Writes
    nothing. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.root.

    Returns
    -------
    None
        Prints the result; exits with status 1 on any problem.
    """
    root = project_root(args)
    _fail(core.check(root), "ipxact check")
    print("ipxact OK")
