# `vhdl_sort`

Ordena fontes VHDL na ordem de dependência que o GHDL consegue analisar. A fase `-a` (analyze) do GHDL precisa que as dependências de uma unidade de projeto (entidades que ela instancia, pacotes que ela usa com `use`) sejam analisadas antes da própria unidade; passar arquivos na ordem errada falha com `"primary unit ... not found"`. Ordenar à mão a lista de arquivos VHDL de um projeto é tedioso e quebra em silêncio assim que uma nova dependência é adicionada, então este módulo deriva a ordem do próprio conteúdo dos arquivos, por uma análise leve com regex (sem invocar o GHDL, sem um parser VHDL de verdade).

## Configuração

Nenhuma: recebe uma lista de caminhos de arquivos e a devolve reordenada; não tem seção própria no `config.yaml`, e não precisa de nenhum contexto de projeto.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_vhdl_sort.py::test_topo_sort_orders_entity_dependency` | Uma entidade é colocada depois das entidades que ela instancia. |
| `tests/test_vhdl_sort.py::test_topo_sort_orders_package_dependency` | Um pacote é colocado antes dos arquivos que o usam. |
| `tests/test_vhdl_sort.py::test_topo_sort_ignores_package_body` | Um corpo de pacote não cria dependência. |
| `tests/test_vhdl_sort.py::test_topo_sort_is_deterministic_for_unrelated_files` | Arquivos sem relação mantêm uma ordem estável. |
| `tests/test_vhdl_sort.py::test_topo_sort_breaks_cycles_without_raising` | Um ciclo de dependência é quebrado em vez de levantar erro. |
| `tests/test_vhdl_sort.py::test_topo_sort_skips_unreadable_file` | Um arquivo ilegível é pulado. |
| `tests/test_vhdl_sort.py::test_topo_sort_ignores_dependency_outside_input_set` | Uma dependência fora do conjunto de entrada é ignorada. |

## Uso

```bash
uv run riscv-tools vhdl-sort src/**/*.vhd
```

Não precisa de `--config`, é só análise do conteúdo dos arquivos. Útil ligado ao alvo de checagem de sintaxe VHDL de um `Makefile`, ou para conferir se a lista `sim.vhdl_sources` de um projeto está mesmo em ordem de dependência antes de entregá-la ao [`sim_runner`](sim_runner.md).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
