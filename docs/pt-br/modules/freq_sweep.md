# `freq_sweep`

Edita no lugar o arquivo-fonte do PLL de um projeto para mudar a frequência do clock de saída (e, num PLL multifase, as defasagens). É só uma reescrita de texto: sem interação com hardware/JTAG aqui, e recompilar e reprogramar depois da edição é responsabilidade de quem chama (veja o sweep de frequência do [`orchestrator`](orchestrator.md)).

Os padrões de nome de parâmetro, as strings de unidade e quantas saídas de clock defasadas reescrever vêm todos da seção `freq_sweep:` do `config.yaml` do próprio projeto, e não são fixos no código, então um projeto com uma instância de megafunção de PLL de outro nome, ou com um wrapper VHDL em vez de Verilog (desde que use a mesma sintaxe de instanciação `.param("valor")`), configura isso sem mexer no código deste módulo.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `freq_sweep.pll_file` | Caminho do arquivo-fonte do PLL. Sem padrão; específico do projeto. |
| `freq_sweep.phase_count` | Quantas saídas de clock com fases igualmente espaçadas a instância do PLL tem (padrão `1`, um PLL simples de fase única). |
| `freq_sweep.freq_param_template` | Nome do parâmetro de frequência com `"{idx}"` (padrão `"output_clock_frequency{idx}"`, acompanhando a megafunção `altpll` do Quartus). |
| `freq_sweep.phase_param_template` | O mesmo, para a defasagem (padrão `"phase_shift{idx}"`). |
| `freq_sweep.freq_unit` | Sufixo de unidade escrito depois do valor de frequência (padrão `"MHz"`). |
| `freq_sweep.phase_unit` | Sufixo de unidade escrito depois do valor de defasagem (padrão `"ps"`). |

## Pré-requisitos

Nenhum para reescrever o fonte do PLL. Um sweep completo também precisa do que o [orchestrator](orchestrator.md) precisa.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_freq_sweep.py::test_set_pll_freq_rewrites_frequency_and_phases` | A frequência e as defasagens são reescritas. |
| `tests/test_freq_sweep.py::test_set_pll_freq_single_phase_default` | Uma única fase usa a defasagem padrão. |
| `tests/test_freq_sweep.py::test_set_pll_freq_missing_param_left_unchanged` | Um parâmetro que o arquivo não tem é deixado como está. |
| `tests/test_freq_sweep.py::test_set_pll_freq_custom_param_template` | Um template de nome de parâmetro personalizado é respeitado. |
| `tests/test_freq_sweep.py::test_get_pll_freq_reads_phase_zero` | A frequência é lida da fase 0. |
| `tests/test_freq_sweep.py::test_get_pll_freq_returns_none_when_absent` | Uma frequência ausente é lida como `None`. |
| `tests/test_freq_sweep.py::test_set_then_get_pll_freq_round_trips` | Uma frequência escrita é lida de volta sem alteração. |

## Uso

Não é um subcomando próprio da CLI: é chamado internamente pelo comando `freq-sweep` do [`orchestrator`](orchestrator.md) a cada frequência candidata, antes de uma recompilação + reprogramação + comparação. Passo a passo completo: [docs/finding-fmax.md](../finding-fmax.md).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
