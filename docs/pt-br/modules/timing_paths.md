# `timing_paths`

Lista os piores caminhos de setup de um projeto do Quartus já compilado, por registrador. O Timing Analyzer informa os caminhos bit a bit (`r_alu_out[13]`); o módulo pede os piores de cada domínio de clock, junta os bits de um mesmo registrador em uma linha e mostra o caminho crítico como "deste registrador para aquele", de modo que o estágio que domina aparece de imediato.

## Funções

| Função | Faz |
| :--- | :--- |
| `run_timing_paths(project_dir, project_name, npaths, model)` | roda o `quartus_sta` sobre o projeto compilado e devolve os caminhos de todos os domínios |
| `parse_paths(output)` | lê as linhas marcadas da saída do script Tcl; uma linha malformada é erro |
| `register_of(node)` | nome do registrador de um nó, sem o índice do bit, com os registradores de barreira do pipeline escritos como `IF/ID`, `ID/EX`, `EX/MEM` e `MEM/WB` |
| `group_paths(paths)` | junta os bits de cada par de registradores em um grupo, do pior para o melhor |
| `format_table(groups)` | tabela com uma linha por grupo |

## Comando

```bash
riscv-tools --config <config.yaml> timing-paths [--npaths N] [--model slow|fast] [--out ARQUIVO]
```

O projeto é o de `quartus.project_dir` e `quartus.project_name` da configuração. `--npaths` (30 por padrão) é a quantidade de caminhos pedidos em cada domínio, `--model` escolhe o modelo lento (1100 mV e 85 C, o padrão) ou o rápido, e `--out` grava a tabela também em um arquivo.

## Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_sta`) e o banco de dados de uma compilação completa do projeto, por exemplo a de `de0-cv_synth.tcl`.

## Testes

`tests/test_timing_paths.py` cobre a leitura das linhas marcadas, o erro de linha malformada, os nomes dos registradores, a junção dos bits e a tabela.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
