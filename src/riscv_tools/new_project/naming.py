"""The name of a project and the identifier derived from it."""

import re
import unicodedata

_SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_DIGITS = "0123456789"
_SEPARATORS = re.compile(r"[\s_-]+")


def _forbidden(title: str) -> str | None:
    """Find the first character a project name cannot have.

    Parameters
    ----------
    title : str
        The name as typed.

    Returns
    -------
    str or None
        The character, or None when every character is accepted.
    """
    for char in title:
        letter = char.isalpha()
        if not (letter or char in _DIGITS or char in " -_"):
            return char
    return None


def check_title(title: str) -> str:
    """Check the name of a project as the person typed it.

    The name is data: it is never placed in a shell command, a path or
    a YAML document without being derived into a slug or escaped.

    Parameters
    ----------
    title : str
        The name: letters (any case, with accents), digits, spaces,
        hyphens and underscores.

    Returns
    -------
    str
        The name without the spaces at its ends.

    Raises
    ------
    ValueError
        If the name is empty, has only spaces or has another character
        (slash, dot, quote, control character).
    """
    clean = title.strip(" ")
    if not clean:
        raise ValueError("the project name is empty")
    bad = _forbidden(clean)
    if bad is not None:
        raise ValueError(
            f"the project name {title!r} has the character {bad!r}; use "
            "letters, digits, spaces, hyphens and underscores"
        )
    return clean


def slugify(title: str) -> str:
    """Derive the identifier of a project from its name.

    The identifier is lower case without accents, with spaces and
    underscores turned into hyphens, repeated hyphens collapsed and
    none at the ends. It names the project folder, the platform, the
    files, the configurations and the Quartus project.

    Parameters
    ----------
    title : str
        The name as typed.

    Returns
    -------
    str
        The identifier, which starts with a letter and has only lower
        case letters, digits and single hyphens.

    Raises
    ------
    ValueError
        If the name is not accepted, or its identifier does not start
        with a letter or keeps a character outside `a-z` and `0-9`.
    """
    clean = check_title(title)
    plain = unicodedata.normalize("NFKD", clean)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    slug = _SEPARATORS.sub("-", plain.lower()).strip("-")
    if _SLUG.fullmatch(slug) is None:
        raise ValueError(
            f"the project name {title!r} gives the identifier {slug!r}, "
            "which must start with a letter and use only a to z, digits "
            "and single hyphens"
        )
    return slug


def check_slug(slug: str) -> str:
    """Check an identifier that is about to name a folder or a file.

    Parameters
    ----------
    slug : str
        The identifier.

    Returns
    -------
    str
        The same identifier.

    Raises
    ------
    ValueError
        If it is not made of lower case letters, digits and single
        hyphens, starting with a letter.
    """
    if _SLUG.fullmatch(slug) is None:
        raise ValueError(
            f"identifier {slug!r} must use lower case letters, digits "
            "and hyphens"
        )
    return slug
