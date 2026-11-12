"""The result of a rule and the helpers to word its message."""

from dataclasses import dataclass

ERROR = "E"
WARNING = "W"


@dataclass(frozen=True)
class Finding:
    """One message of the validator.

    Parameters
    ----------
    rule : str
        The rule that produced it (`V1` to `V22`, or `schema`).
    level : str
        `E` for an error, `W` for a warning.
    text : str
        The message without the level.
    """

    rule: str
    level: str
    text: str

    def __str__(self) -> str:
        """Format the finding as the plan words it.

        Returns
        -------
        str
            The level, a space and the message.
        """
        return f"{self.level} {self.text}"


def error(rule: str, text: str) -> Finding:
    """Make an error.

    Parameters
    ----------
    rule : str
        The rule.
    text : str
        The message.

    Returns
    -------
    Finding
        The error.
    """
    return Finding(rule, ERROR, text)


def warning(rule: str, text: str) -> Finding:
    """Make a warning.

    Parameters
    ----------
    rule : str
        The rule.
    text : str
        The message.

    Returns
    -------
    Finding
        The warning.
    """
    return Finding(rule, WARNING, text)


def size_text(value: int) -> str:
    """Write a byte count the way the platform files do.

    Parameters
    ----------
    value : int
        The bytes.

    Returns
    -------
    str
        `128M`, `64K` or the plain number when no unit divides it.
    """
    for unit, factor in (("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if value >= factor and value % factor == 0:
            return f"{value // factor}{unit}"
    return str(value)


def mhz_text(value: float) -> str:
    """Write a frequency without a useless decimal point.

    Parameters
    ----------
    value : float
        The frequency in MHz.

    Returns
    -------
    str
        `143` for 143.0 and `33.3` for 33.3.
    """
    return str(int(value)) if value == int(value) else str(value)
