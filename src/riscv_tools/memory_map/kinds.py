"""The kinds of peripheral that `peripherals` accepts in `kind`.

A peripheral with no `kind` is a plain window (`base` and `size`). With
a `kind` it is one of these, and this is the only place that lists
them.

- `gpio` and `seg_display` take `base` and `groups`, never `size`: the
  window comes from the groups.
- `timer` takes `base` and `size`, which is at least 32 bytes.
"""

from typing import Any

KIND_TIMER = "timer"
GROUP_KINDS = ("gpio", "seg_display")
KINDS = (*GROUP_KINDS, KIND_TIMER)


def is_group_block(item: dict[str, Any]) -> bool:
    """Tell whether a peripheral is a block of groups.

    Parameters
    ----------
    item : dict of {str: Any}
        One entry of `peripherals`.

    Returns
    -------
    bool
        True for `gpio` and `seg_display`.
    """
    return item.get("kind") in GROUP_KINDS
