"""Compile the `config_pkg` of the profile, not the platform's."""

from pathlib import Path

FILE_NAME = "config_pkg.vhd"


def with_profile_config_pkg(
    sources: list[str], text: str, directory: Path
) -> list[str]:
    """Replace the `config_pkg.vhd` of the sources by the profile's.

    The base and the extensions of the core are constants of the
    `config_pkg`, so a profile other than the one the platform file was
    written for only reaches the core through another copy of it.

    Parameters
    ----------
    sources : list of str
        The VHDL sources, in dependency order.
    text : str
        The `config_pkg` of the profile (`sim.config_pkg`); empty keeps
        the sources as they are.
    directory : Path
        Where the profile's copy is written.

    Returns
    -------
    list of str
        The sources, with every `config_pkg.vhd` taken from `directory`.

    Raises
    ------
    ValueError
        `text` is given and no source is a `config_pkg.vhd`.
    """
    if not text:
        return sources
    if not any(Path(src).name == FILE_NAME for src in sources):
        raise ValueError(f"sim.config_pkg is set but no source is {FILE_NAME}")
    directory.mkdir(parents=True, exist_ok=True)
    copy = directory / FILE_NAME
    copy.write_text(text, encoding="utf-8")
    return [
        str(copy) if Path(src).name == FILE_NAME else src for src in sources
    ]
