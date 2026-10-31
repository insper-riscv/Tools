"""timing_paths: reading, naming and grouping paths, no Quartus."""

import pytest

from riscv_tools import timing_paths

SRC = "core:CORE|reg_mem_wb:u_reg_mem_wb|r_ext_ram_op[0]"
OUT = "core:CORE|reg_ex_mem:u_reg_ex_mem|r_alu_out[13]"
OUTPUT = "\n".join(
    [
        "Info: Running Quartus Prime Timing Analyzer",
        f"PATH\tclkA\t-2.016\t21.772\t{SRC}\t{OUT}",
        f"PATH\tclkA\t-1.885\t21.634\t{SRC}\t"
        "core:CORE|reg_ex_mem:u_reg_ex_mem|r_alu_out[11]",
        "PATH\tclkB\t-0.205\t5.100\t"
        "sdram_ctrl:S|st.ST_ACT\tsdram_ctrl:S|ack_i",
        "Info: done",
    ]
)


def test_paths_are_read_from_the_marked_lines() -> None:
    """Paths are read from the marked lines."""
    paths = timing_paths.parse_paths(OUTPUT)
    assert [p.slack for p in paths] == [-2.016, -1.885, -0.205]
    assert paths[0].source == SRC and paths[0].clock == "clkA"


def test_a_malformed_line_is_an_error() -> None:
    """A malformed line is an error."""
    with pytest.raises(ValueError, match="malformed"):
        timing_paths.parse_paths("PATH\tclkA\t1.0")


@pytest.mark.parametrize(
    "node, expected",
    [
        (SRC, "MEM/WB r_ext_ram_op"),
        (OUT, "EX/MEM r_alu_out"),
        ("core:CORE|stage_ex:u_ex|alu:u_alu|r_sum[3]", "u_ex|u_alu|r_sum"),
        ("sdram_ctrl:S|ack_i", "S|ack_i"),
    ],
)
def test_register_names_drop_the_bit_and_name_the_stage(
    node: str, expected: str
) -> None:
    """Register names drop the bit and name the stage."""
    assert timing_paths.register_of(node) == expected


def test_bits_of_a_register_pair_fold_into_one_group_worst_first() -> None:
    """Bits of a register pair fold into one group worst first."""
    groups = timing_paths.group_paths(timing_paths.parse_paths(OUTPUT))
    assert [(g.source, g.destination, g.paths) for g in groups] == [
        ("MEM/WB r_ext_ram_op", "EX/MEM r_alu_out", 2),
        ("S|st.ST_ACT", "S|ack_i", 1),
    ]
    assert groups[0].slack == -2.016 and groups[0].delay == 21.772


def test_table_has_one_row_per_group() -> None:
    """Table has one row per group."""
    table = timing_paths.format_table(
        timing_paths.group_paths(timing_paths.parse_paths(OUTPUT))
    )
    assert table.count("\n") == 4
    assert (
        "| `clkA` | `MEM/WB r_ext_ram_op` | `EX/MEM r_alu_out` | 2 "
        "| -2.016 | 21.772 |" in table
    )
