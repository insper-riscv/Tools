"""Read the fields of a YAML mapping with their types checked.

Every schema of the board catalog (board, family, chip, pins and the
new fields of the platform) reads its mapping through `Section`, so a
wrong type, a missing field or a misspelled key is reported the same way
everywhere, all together, with the dotted path of the field.
"""

from collections.abc import Callable
from typing import Any, cast


class SchemaError(ValueError):
    """A file whose content does not follow its schema.

    Parameters
    ----------
    problems : list of str
        One line per problem, each starting with the dotted path.
    """

    def __init__(self, problems: list[str]) -> None:
        """Keep the problems and join them as the message.

        Parameters
        ----------
        problems : list of str
            One line per problem.
        """
        super().__init__("; ".join(problems))
        self.problems = problems


def _is_int(value: Any) -> bool:
    """Tell whether a value is an integer and not a boolean.

    Parameters
    ----------
    value : Any
        The parsed value.

    Returns
    -------
    bool
        True for an `int` that is not a `bool`.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    """Tell whether a value is an integer or a float, not a boolean.

    Parameters
    ----------
    value : Any
        The parsed value.

    Returns
    -------
    bool
        True for a number.
    """
    return _is_int(value) or isinstance(value, float)


_KINDS: dict[str, tuple[str, Callable[[Any], bool]]] = {
    "text": ("a string", lambda v: isinstance(v, str)),
    "int": ("an integer", _is_int),
    "number": ("a number", _is_number),
    "flag": ("true or false", lambda v: isinstance(v, bool)),
    "map": ("a mapping", lambda v: isinstance(v, dict)),
    "list": ("a list", lambda v: isinstance(v, list)),
}


class Section:
    """A mapping read field by field, collecting what is wrong.

    Parameters
    ----------
    label : str
        The dotted path of the mapping, for the messages.
    raw : Any
        The parsed value; a value that is not a mapping is reported and
        read as an empty one.
    problems : list of str
        Receives one line for each problem found by this section and by
        the sections taken from it.
    """

    def __init__(self, label: str, raw: Any, problems: list[str]) -> None:
        """Wrap a parsed value, reporting it when it is not a mapping.

        Parameters
        ----------
        label : str
            The dotted path of the mapping.
        raw : Any
            The parsed value.
        problems : list of str
            Receives the problems.
        """
        self.label = label
        self.problems = problems
        self.seen: set[str] = set()
        if isinstance(raw, dict):
            self.raw = cast("dict[str, Any]", raw)
        else:
            problems.append(f"{label} must be a mapping")
            self.raw = {}

    def fail(self, key: str, detail: str) -> None:
        """Report a problem of one field.

        Parameters
        ----------
        key : str
            The field.
        detail : str
            What is wrong with it.
        """
        self.problems.append(f"{self.label}.{key} {detail}")

    def _read(
        self, key: str, kind: str, required: bool, nullable: bool
    ) -> Any:
        """Read one field and check its type.

        Parameters
        ----------
        key : str
            The field.
        kind : str
            A key of the table of types.
        required : bool
            Whether a missing field is a problem.
        nullable : bool
            Whether an explicit `null` is a valid value.

        Returns
        -------
        Any
            The value; None when it is missing, null or of a wrong type
            (the latter two after reporting).
        """
        self.seen.add(key)
        if key not in self.raw:
            if required:
                self.fail(key, "is required")
            return None
        value = self.raw[key]
        if value is None:
            if not nullable:
                self.fail(key, "must not be null")
            return None
        name, accepts = _KINDS[kind]
        if accepts(value):
            return value
        self.fail(key, f"must be {name}")
        return None

    def text(
        self,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        choices: tuple[str, ...] = (),
    ) -> str | None:
        """Read a string field, optionally one of a fixed set.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.
        nullable : bool, optional
            Whether `null` is valid.
        choices : tuple of str, optional
            The accepted values; any string when empty.

        Returns
        -------
        str or None
            The value, None when absent or invalid.
        """
        value = cast("str | None", self._read(key, "text", required, nullable))
        if value is not None and choices and value not in choices:
            self.fail(key, f"must be one of {', '.join(choices)}")
            return None
        return value

    def integer(
        self,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        minimum: int | None = None,
    ) -> int | None:
        """Read an integer field.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.
        nullable : bool, optional
            Whether `null` is valid.
        minimum : int, optional
            The smallest accepted value.

        Returns
        -------
        int or None
            The value, None when absent or invalid.
        """
        value = cast("int | None", self._read(key, "int", required, nullable))
        if value is not None and minimum is not None and value < minimum:
            self.fail(key, f"must be at least {minimum}")
            return None
        return value

    def number(
        self,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        minimum: float | None = None,
    ) -> float | None:
        """Read an integer or float field.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.
        nullable : bool, optional
            Whether `null` is valid.
        minimum : float, optional
            The smallest accepted value.

        Returns
        -------
        float or None
            The value, None when absent or invalid.
        """
        value = cast(
            "float | None", self._read(key, "number", required, nullable)
        )
        if value is not None and minimum is not None and value < minimum:
            self.fail(key, f"must be at least {minimum}")
            return None
        return value

    def flag(
        self, key: str, *, required: bool = True, default: bool = False
    ) -> bool:
        """Read a boolean field.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.
        default : bool, optional
            The value when the field is absent or invalid.

        Returns
        -------
        bool
            The value, or the default.
        """
        value = cast("bool | None", self._read(key, "flag", required, False))
        return default if value is None else value

    def section(
        self, key: str, *, required: bool = True, nullable: bool = False
    ) -> Section | None:
        """Read a nested mapping as a section of its own.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.
        nullable : bool, optional
            Whether `null` is valid.

        Returns
        -------
        Section or None
            The nested section, None when absent, null or not a mapping.
        """
        value = self._read(key, "map", required, nullable)
        if value is None:
            return None
        return Section(f"{self.label}.{key}", value, self.problems)

    def items(self, key: str, *, required: bool = True) -> list[Any]:
        """Read a list field.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.

        Returns
        -------
        list of Any
            The items; empty when absent or not a list.
        """
        value = self._read(key, "list", required, False)
        return [] if value is None else cast("list[Any]", value)

    def texts(self, key: str, *, required: bool = True) -> list[str]:
        """Read a list of strings.

        Parameters
        ----------
        key : str
            The field.
        required : bool, optional
            Whether a missing field is a problem.

        Returns
        -------
        list of str
            The strings; empty when absent or malformed.
        """
        found = self.items(key, required=required)
        if all(isinstance(item, str) for item in found):
            return cast("list[str]", found)
        self.fail(key, "must be a list of strings")
        return []

    def one_or_more(self, key: str) -> tuple[str, ...]:
        """Read a field that is one string or a non-empty list of them.

        Parameters
        ----------
        key : str
            The field.

        Returns
        -------
        tuple of str
            The strings; empty, after reporting, when the field is
            neither (and when it is absent).
        """
        raw = self.get(key)
        if isinstance(raw, str):
            return (raw,)
        if isinstance(raw, list) and raw:
            found = cast("list[Any]", raw)
            if all(isinstance(item, str) for item in found):
                return tuple(cast("list[str]", found))
        self.fail(key, "must be a string or a list of strings")
        return ()

    def names(self) -> list[str]:
        """List the keys the mapping has.

        Returns
        -------
        list of str
            The keys, in file order.
        """
        return list(self.raw)

    def get(self, key: str) -> Any:
        """Take a raw value, marking its key as known.

        Parameters
        ----------
        key : str
            The field.

        Returns
        -------
        Any
            The raw value, None when absent.
        """
        self.seen.add(key)
        return self.raw.get(key)

    def done(self) -> None:
        """Report the keys no accessor read, which no schema defines."""
        self.problems.extend(
            f"{self.label}.{key} is not a field of the schema"
            for key in self.raw
            if key not in self.seen
        )


def raise_if(problems: list[str]) -> None:
    """Raise the schema error of the problems, when there are any.

    Parameters
    ----------
    problems : list of str
        What the sections collected.

    Raises
    ------
    SchemaError
        If `problems` is not empty.
    """
    if problems:
        raise SchemaError(problems)


def present(value: Any) -> Any:
    """Take a value that `raise_if` already guaranteed to exist.

    Parameters
    ----------
    value : Any
        A field read after the problems were checked.

    Returns
    -------
    Any
        The same value.

    Raises
    ------
    SchemaError
        If the value is None, which only happens when a reader forgot to
        report the field as a problem.
    """
    if value is None:
        raise SchemaError(["a required field was read as missing"])
    return value
