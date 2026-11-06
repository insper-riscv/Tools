"""Each kind of generated text is written by exactly one module."""

from pathlib import Path

from support import check_equal

SRC = Path(__file__).resolve().parents[1] / "src" / "riscv_tools"

# Marcador do texto escrito, e o único módulo que pode tê-lo.
WRITERS = {
    '"set_location_assignment': "pin_assignments",
    "FAST_OUTPUT_REGISTER": "pin_assignments",
    "CURRENT_STRENGTH_NEW": "pin_assignments",
    "create_generated_clock -name": "sdc_generator",
    "set_multicycle_path": "sdc_generator",
    "derive_pll_clocks": "sdc_generator",
    "altera_pll #(": "pll_generator",
    "PLL_COMPENSATION_MODE": "pll_generator",
    "PROJECT_REVISION": "quartus_project",
    "TOP_LEVEL_ENTITY": "quartus_project",
    "SOC_ENTITY": "top_generator",
    "T_RCD_PS": "chip_package",
}


def _modules_with(marker: str) -> set[str]:
    """Lista os módulos do pacote que contêm o marcador."""
    return {
        path.relative_to(SRC).parts[0]
        for path in SRC.rglob("*.py")
        if marker in path.read_text(encoding="utf-8")
    }


def test_no_two_generators_write_the_same_kind_of_text() -> None:
    """A second writer of any marker would be a second generator."""
    for marker, owner in WRITERS.items():
        check_equal(_modules_with(marker), {owner}, marker)


def test_only_the_quartus_program_module_compiles() -> None:
    """The compile command lives in one place."""
    check_equal(_modules_with('"--flow"'), {"quartus_program"})
