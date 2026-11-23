"""Generics da cache de dados que o topo gerado passa ao SoC."""

from types import SimpleNamespace
from typing import Any, cast

from support import check_equal

from riscv_tools.top_generator.generics import dcache_generics


def _spec(dcache: dict[str, Any]) -> Any:
    """Monta um topo só com o `platform.yaml` que a função lê."""
    return cast(Any, SimpleNamespace(platform={"memory": {"dcache": dcache}}))


def test_the_early_lookup_becomes_a_generic() -> None:
    """`early_lookup: true` liga a leitura adiantada da cache."""
    generics = dcache_generics(_spec({"early_lookup": True}))
    check_equal(generics, ["dcache_early_lookup => true"])


def test_the_valid_in_ram_becomes_a_generic() -> None:
    """`valid_in_ram: true` guarda a validade das linhas numa RAM."""
    generics = dcache_generics(_spec({"valid_in_ram": True}))
    check_equal(generics, ["dcache_valid_in_ram => true"])


def test_without_the_early_lookup_no_generic_is_passed() -> None:
    """Sem a chave, ou com ela falsa, o SoC fica com o padrão."""
    check_equal(dcache_generics(_spec({})), [])
    check_equal(dcache_generics(_spec({"early_lookup": False})), [])


def test_the_buffer_the_scratch_and_the_early_lookup_come_together() -> None:
    """Os três generics saem na ordem fila, memória, leitura cedo."""
    generics = dcache_generics(
        _spec(
            {
                "write_buffer": 4,
                "scratch_kib": 32,
                "scratch_base": 0x43FE8000,
                "early_lookup": True,
                "valid_in_ram": True,
            }
        )
    )
    check_equal(
        generics,
        [
            "dcache_write_buffer => 4",
            "dcache_scratch_kib => 32",
            f"dcache_scratch_base_kib => {0x43FE8000 // 1024}",
            "dcache_early_lookup => true",
            "dcache_valid_in_ram => true",
        ],
    )
