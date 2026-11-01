"""Expand the repeatable test name filters of the CLI."""


def split_test_name_groups(groups: list[str] | None) -> list[str]:
    """Expand repeatable comma-separated CLI values, deduplicated.

    Parameters
    ----------
    groups : list of str, optional
        The values of a repeatable option, each holding names separated
        by commas.

    Returns
    -------
    list of str
        The names in the order given, without blanks or repeats.
    """
    names: list[str] = []
    seen: set[str] = set()
    for group in groups or []:
        for raw_name in group.split(","):
            name = raw_name.strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return names
