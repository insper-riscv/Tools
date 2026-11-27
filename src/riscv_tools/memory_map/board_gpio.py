"""Adaptive GPIO blocks wired to a board's external expansion role."""

from typing import Any

from riscv_tools.memory_map.core import peripheral_list


def board_gpio_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """Return expansion banks, preserving legacy SW/KEY roles."""
    return [
        item
        for item in peripheral_list(platform)
        if item.get("kind") == "gpio" and item.get("roles") == ["gpio"]
    ]
