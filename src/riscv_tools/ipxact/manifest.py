"""Read the IP-XACT sections of a repository's `paths.yaml`.

Two sections hold the data a person writes; everything else in the
IP-XACT files is generated from the VHDL.

```yaml
ipxact:
  # Entities (or components of `provides`) with no IP-XACT component,
  # and the reason; the list changes only with a justification.
  exceptions:
    sdram_ctrl: the limit of a port calls dram_a_bits

interfaces:
  generic_register:          # an entity
    buses:                   # the bus interfaces of the entity
      - name: clock          # unique in the entity
        contract: clock      # the bus definition the interface follows
        role: target         # initiator, target, system, ...
        ports: {prefix: i_clk}      # or {names: [i_clk, i_rst]}
    unbound:                 # ports that belong to no interface
      i_d: data input with no bus contract
```

A port belongs to exactly one interface or is listed in `unbound` with
its justification; the check that every port is covered runs with the
bus definitions.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

ROLES = frozenset(
    {
        "initiator",
        "target",
        "system",
        "mirroredInitiator",
        "mirroredTarget",
        "mirroredSystem",
        "monitor",
    }
)


@dataclass(frozen=True)
class Bus:
    """A bus interface of an entity.

    Parameters
    ----------
    name : str
        The interface name, unique in the entity.
    contract : str
        The name of the bus definition it follows.
    role : str
        The interface mode (`ROLES`).
    prefix : str
        The prefix of the ports that belong to it, empty when `names`
        lists them.
    names : tuple of str
        The ports that belong to it by name.
    """

    name: str
    contract: str
    role: str
    prefix: str
    names: tuple[str, ...]


@dataclass(frozen=True)
class EntityInterfaces:
    """The interface data of one entity.

    Parameters
    ----------
    buses : tuple of Bus
        The bus interfaces.
    unbound : dict of str to str
        The ports that belong to no interface and why.
    """

    buses: tuple[Bus, ...]
    unbound: dict[str, str]


def _section(root: Path) -> dict[str, Any]:
    """Read `paths.yaml` as a mapping, empty when absent."""
    manifest = root / "paths.yaml"
    if not manifest.is_file():
        return {}
    data = yaml.safe_load(manifest.read_text())
    return cast("dict[str, Any]", data) if isinstance(data, dict) else {}


def exceptions(root: Path) -> tuple[dict[str, str], list[str]]:
    """Read the entities that have no component, with their reasons.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    tuple of (dict of str to str, list of str)
        The exceptions and one line for each malformation.
    """
    raw = _section(root).get("ipxact")
    if raw is None:
        return {}, []
    body = cast("dict[str, Any]", raw) if isinstance(raw, dict) else None
    listed = None if body is None else body.get("exceptions", {})
    if not isinstance(listed, dict):
        return {}, ["ipxact.exceptions is a mapping of name to reason"]
    found = cast("dict[Any, Any]", listed)
    problems = [
        f"ipxact.exceptions.{name} is a non-empty reason"
        for name, reason in found.items()
        if not isinstance(reason, str) or not reason.strip()
    ]
    return {str(k): str(v) for k, v in found.items()}, problems


def _bus(entity: str, raw: Any, problems: list[str]) -> Bus | None:
    """Read one bus interface, reporting what is malformed."""
    where = f"interfaces.{entity}.buses"
    if not isinstance(raw, dict):
        problems.append(f"{where}: an interface is a mapping")
        return None
    body = cast("dict[str, Any]", raw)
    ports = body.get("ports")
    prefix, names = "", ()
    if isinstance(ports, dict):
        listed = cast("dict[str, Any]", ports)
        prefix = str(listed.get("prefix", ""))
        names = tuple(str(n) for n in listed.get("names", []))
    if not prefix and not names:
        problems.append(f"{where}: `ports` has a `prefix` or `names`")
    problems.extend(
        f"{where}: `{key}` is a non-empty string"
        for key in ("name", "contract")
        if not isinstance(body.get(key), str) or not body.get(key)
    )
    if body.get("role") not in ROLES:
        problems.append(
            f"{where}: `role` is one of {', '.join(sorted(ROLES))}"
        )
    return Bus(
        str(body.get("name", "")),
        str(body.get("contract", "")),
        str(body.get("role", "")),
        prefix,
        names,
    )


def _entity(
    name: str, raw: Any, problems: list[str]
) -> EntityInterfaces | None:
    """Read the interface data of one entity."""
    if not isinstance(raw, dict):
        problems.append(f"interfaces.{name}: a mapping with buses and unbound")
        return None
    body = cast("dict[str, Any]", raw)
    buses = [
        bus
        for item in body.get("buses", [])
        if (bus := _bus(name, item, problems)) is not None
    ]
    names = [bus.name for bus in buses]
    problems.extend(
        f"interfaces.{name}: interface {each} is declared twice"
        for each in sorted({n for n in names if names.count(n) > 1})
    )
    return EntityInterfaces(
        tuple(buses), _unbound(name, body.get("unbound", {}), problems)
    )


def _unbound(name: str, raw: Any, problems: list[str]) -> dict[str, str]:
    """Read the ports that belong to no interface and their reasons."""
    listed = cast("dict[Any, Any]", raw) if isinstance(raw, dict) else None
    if listed is None or not all(
        isinstance(v, str) and v.strip() for v in listed.values()
    ):
        problems.append(f"interfaces.{name}.unbound maps a port to a reason")
        return {}
    return {str(k): str(v) for k, v in listed.items()}


def load_interfaces(
    root: Path,
) -> tuple[dict[str, EntityInterfaces], list[str]]:
    """Read the `interfaces` section of the repository.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    tuple of (dict of str to EntityInterfaces, list of str)
        The data of each entity and one line for each malformation.
    """
    raw = _section(root).get("interfaces")
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, ["interfaces is a mapping of entities"]
    problems: list[str] = []
    found: dict[str, EntityInterfaces] = {}
    for name, body in cast("dict[Any, Any]", raw).items():
        entity = _entity(str(name), body, problems)
        if entity is not None:
            found[str(name)] = entity
    return found, problems


def manifest_problems(root: Path) -> list[str]:
    """List what is malformed in the IP-XACT sections of `paths.yaml`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of str
        One line for each malformation, empty when both sections are
        absent or well formed.
    """
    return [*exceptions(root)[1], *load_interfaces(root)[1]]
