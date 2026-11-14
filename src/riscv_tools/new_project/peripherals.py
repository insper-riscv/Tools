"""The peripherals a new project can ask for, by name.

`--peripherals ledr,sw,key,hex,uart` writes one block of `peripherals`
for each name, at the base the table gives; without the option the
platform starts with `peripherals: {}`.
"""

from collections.abc import Iterable

# Nome pedido e as linhas do bloco, abaixo do nome do periférico.
CATALOG: dict[str, tuple[str, tuple[str, ...]]] = {
    "ledr": (
        "LEDR",
        (
            "kind: gpio",
            "role: leds",
            "base: 0x80002000",
            "groups: solo",
        ),
    ),
    "sw": (
        "SW",
        (
            "kind: gpio",
            "role: switches",
            "base: 0x80003000",
            "groups: all",
        ),
    ),
    "key": (
        "KEY",
        (
            "kind: gpio",
            "role: keys",
            "base: 0x80004000",
            "groups: all",
        ),
    ),
    "hex": (
        "HEX",
        ("kind: seg_display", "base: 0x80005000", "groups: all"),
    ),
    "uart": ("UART", ("base: 0xC0000000", "size: 1K")),
    "clint": ("CLINT", ("base: 0xE0000000", "size: 64K")),
    "plic": ("PLIC", ("base: 0xF0000000", "size: 4M")),
}


def parse_peripherals(text: str) -> tuple[str, ...]:
    """Read the value of `--peripherals`.

    Parameters
    ----------
    text : str
        The names, separated by commas.

    Returns
    -------
    tuple of str
        The names in lower case, in the order written.

    Raises
    ------
    ValueError
        If a name is unknown or repeated.
    """
    names = tuple(n.strip().lower() for n in text.split(",") if n.strip())
    unknown = [name for name in names if name not in CATALOG]
    if unknown:
        raise ValueError(
            f"unknown peripheral {unknown[0]!r}; known: {', '.join(CATALOG)}"
        )
    if len(set(names)) != len(names):
        raise ValueError("a peripheral is listed twice")
    return names


def block_text(names: Iterable[str]) -> str:
    """Write the `peripherals` block of the platform file.

    Parameters
    ----------
    names : iterable of str
        The names of the catalog; none gives `peripherals: {}`.

    Returns
    -------
    str
        The block, ending in a line break, in the order of the names
        (which is the order of the indexes).
    """
    entries = [CATALOG[name] for name in names]
    if not entries:
        return "peripherals: {}\n"
    lines = ["peripherals:"]
    for key, fields in entries:
        lines.append(f"  {key}:")
        lines += [f"    {field}" for field in fields]
    return "\n".join(lines) + "\n"
