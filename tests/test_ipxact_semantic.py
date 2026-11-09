"""Tests for the schema and semantic rules applied to a component."""

from pathlib import Path

import pytest
from support import check, check_equal, check_in

from riscv_tools.ipxact.component import Source, build, serialize
from riscv_tools.ipxact.model import Entity, Generic, Port
from riscv_tools.ipxact.schema import schema_errors
from riscv_tools.ipxact.semantic import check_component
from riscv_tools.ipxact.vlnv import Vlnv

ENTITY = Entity(
    "demo",
    "src/demo.vhd",
    (
        Generic("width", "positive", "8", "Largura.", 1, 64),
        Generic("depth", "natural", "(width * 2)", "Profundidade.", 0),
    ),
    (
        Port(
            "i_clk", "in", "std_logic", (), "Clock.", "ieee.std_logic_1164.all"
        ),
        Port(
            "o_d",
            "out",
            "std_logic_vector",
            (("(width - 1)", "0"),),
            "Dado.",
            "ieee.std_logic_1164.all",
        ),
    ),
    "Bloco de teste",
)
SOURCE = Source(
    Vlnv("insper.edu.br", "demo", "demo", "1.0.0"),
    "blocks",
    ("src/demo.vhd",),
    ("base",),
)


def _write(tmp_path: Path, mutate: tuple[str, str] | None = None) -> Path:
    """Write the demo component, optionally with one text replaced."""
    text = serialize(build(ENTITY, SOURCE))
    if mutate is not None:
        check_in(mutate[0], text)
        text = text.replace(*mutate)
    path = tmp_path / "demo.1.0.0.component.xml"
    path.write_text(text)
    return path


def test_valid_component(tmp_path: Path) -> None:
    """The generated document breaks no rule."""
    path = _write(tmp_path)
    check_equal(schema_errors(path), [])
    check_equal(check_component(path), [])


def test_schema_rejects_a_direction(tmp_path: Path) -> None:
    """The schema refuses a direction that is not one of its values."""
    path = _write(
        tmp_path, ("<ipxact:direction>in", "<ipxact:direction>sideways")
    )
    check(schema_errors(path))


@pytest.mark.parametrize(
    ("mutate", "rule"),
    [
        (("(width - 1)", "(missing - 1)"), "SCR 5.18"),
        (("(width - 1)", "(width -"), "SCR 5.17"),
        (("(width - 1)", "(width - 99)"), "C.7.11"),
        (("<ipxact:viewRef>rtl", "<ipxact:viewRef>other"), "C.29.2"),
        (("<ipxact:value>8<", "<ipxact:value>(depth + 1)<"), "SCR 5.19"),
        (("<ipxact:value>8<", "<ipxact:value>100<"), "SCR 5.13"),
        (('parameterId="width" ', ""), "SCR 5.2"),
    ],
)
def test_semantic_rules(
    tmp_path: Path, mutate: tuple[str, str], rule: str
) -> None:
    """Each rule the module checks names itself when broken."""
    found = " ".join(check_component(_write(tmp_path, mutate)))
    check_in(rule, found)


def test_module_parameter_used_outside(tmp_path: Path) -> None:
    """A module parameter named outside its instantiation is refused."""
    text = serialize(build(ENTITY, SOURCE)).replace(
        '<ipxact:moduleParameter usageType="typed" dataType="positive">',
        '<ipxact:moduleParameter parameterId="mp" usageType="typed"'
        ' dataType="positive">',
        1,
    )
    path = tmp_path / "demo.1.0.0.component.xml"
    path.write_text(text.replace("(width - 1)", "(mp - 1)", 1))
    check_in("SCR 5.14", " ".join(check_component(path)))


def test_root_must_be_a_document(tmp_path: Path) -> None:
    """The document element has to be one of the legal types."""
    path = tmp_path / "x.xml"
    path.write_text("<root/>")
    check_in("SCR 1.10", " ".join(check_component(path)))
