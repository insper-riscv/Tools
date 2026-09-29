# `sim_runner`

Dirige a simulação cocotb/GHDL, a contraparte de simulação do [`orchestrator`](orchestrator.md), que dirige o hardware real por JTAG. Não tem conhecimento específico de DUT: o `test_module` cocotb do próprio projeto (veja Configuração abaixo) conhece a hierarquia real de sinais VHDL e consulta o mailbox PASS/FAIL direto dos sinais simulados, a mesma convenção que o [`mailbox`](mailbox.md) usa no hardware real.

Precisa do extra opcional `sim` (`cocotb` + `cocotb-tools`, mais o GHDL no `PATH`); não é uma dependência obrigatória do pacote, então projetos que só usam o lado de hardware real não precisam instalá-lo.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `sim.toplevel` | Entidade VHDL de topo que o GHDL elabora e à qual o cocotb se conecta. Sem padrão; específica do projeto. |
| `sim.vhdl_sources` | Fontes VHDL, em ordem de dependência (veja [`vhdl_sort`](vhdl_sort.md)). Sem padrão. |
| `sim.test_module` | O módulo de teste cocotb do próprio projeto. Sem padrão; é a peça que conhece os nomes de sinal do DUT e consulta o mailbox dele. |
| `sim.ghdl_std` | Padrão VHDL contra o qual o GHDL analisa (padrão `"08"`, VHDL-2008). |
| `sim.parameters` | Generics VHDL definidos no toplevel na etapa de execução do GHDL, por exemplo um modelo de ROM só de simulação que carrega a imagem por um generic em vez de uma variável de ambiente. Vazio por padrão. |

## Pré-requisitos

- O GHDL no `PATH`.
- O extra `sim` (`uv sync --extra sim`): `cocotb` e `cocotb-tools`.

## Testes

Os testes são pulados quando o GHDL ou o cocotb não estão disponíveis.

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_sim_runner.py::test_sim_runner_reports_pass` | Um DUT cujo teste passa é reportado como passou. |
| `tests/test_sim_runner.py::test_sim_runner_reports_fail` | Um DUT cujo teste falha é reportado como falhou. |
| `tests/test_sim_runner.py::test_sim_runner_parameters_reach_ghdl` | `sim.parameters` viram generics VHDL na etapa de execução do GHDL. |

## Uso

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
