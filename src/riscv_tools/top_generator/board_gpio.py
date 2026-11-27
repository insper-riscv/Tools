"""Wire an adaptive GPIO register bank to numbered expansion pins."""

from typing import Any

from riscv_tools.board_inputs import InputError
from riscv_tools.memory_map.groups import expand, problems
from riscv_tools.top_generator.spec import TopSpec, role_ports

_MAX_FIELDS = 255
_GROUP_WORD_BITS = 4


def gpio_groups(spec: TopSpec, item: dict[str, Any]) -> list[list[int]]:
    """Validate group members against the physical board ports."""
    count = sum(p.width for p in role_ports(spec, "gpio"))
    if not 1 <= count <= _MAX_FIELDS:
        raise InputError(
            f"GPIO {item['name']}: board needs 1..255 expansion pins"
        )
    groups = expand(item["groups"], count)
    found = problems(str(item["name"]), groups, count)
    if (
        found
        or not groups
        or len(groups) > _MAX_FIELDS
        or sum(map(len, groups)) > _MAX_FIELDS
    ):
        raise InputError(f"GPIO {item['name']}: invalid groups: {found}")
    return groups


def gpio_lines(spec: TopSpec, item: dict[str, Any]) -> list[str]:
    """Instantiate the register bank and connect physical ports."""
    ports = role_ports(spec, "gpio")
    count = sum(p.width for p in ports)
    groups = gpio_groups(spec, item)
    members = [pin for group in groups for pin in group]
    sizes_hex = "".join(f"{len(g):02x}" for g in reversed(groups))
    members_hex = "".join(f"{pin:02x}" for pin in reversed(members))
    bits = _GROUP_WORD_BITS + (len(groups) - 1).bit_length()
    name = str(item["name"])
    pos = f"{name.upper()}_EXT_POS"
    maps = [
        "i_clk => clk_core",
        "i_rst => soc_rst",
        "i_data_in => ext_wdata",
        f"i_address => ext_addr({bits - 1} downto 0)",
        f"i_write => ext_we({pos})",
        f"i_read => ext_re({pos})",
        f"o_data_out => ext_rdata(32 * {pos} + 31 downto 32 * {pos})",
        # No interrupt source is declared for expansion GPIO yet.
        "o_irq => open",
    ]
    offset = 0
    for port in ports:
        if (
            not port.vector
            or port.direction != "inout"
            or port.active != "high"
        ):
            raise InputError(
                f"GPIO {name}: expected active-high inout expansion vectors"
            )
        maps.append(
            f"io_gpio_pins({offset + port.width - 1} downto {offset})"
            f" => {port.name}"
        )
        offset += port.width
    return [
        f"\t{name.lower()}_gpio_inst : entity work.gpio",
        "\t\tgeneric map (",
        f"\t\t\tpin_count => {count}, group_count => {len(groups)},",
        f"\t\t\tmember_count => {len(members)},",
        f'\t\t\tgroup_sizes => x"{sizes_hex}",',
        f'\t\t\tgroup_members => x"{members_hex}",',
        f"\t\t\tpin_dirs => ({2 * count - 1} downto 0 => '0'),",
        f"\t\t\tpin_active_low => ({count - 1} downto 0 => '0')",
        "\t\t)",
        "\t\tport map (",
        ",\n".join(f"\t\t\t{m}" for m in maps),
        "\t\t);",
        f"\text_irq({pos}) <= '0';",
        "",
    ]
