# `quartus_project`

Gera o `.qpf` e o `.qsf` (sem os pinos) com família, dispositivo e a lista de fontes.

## 1. Função

Escreve a revisão do projeto, o dispositivo, o topo, o `.sdc`, o modo de otimização, a semente e as fontes, cada uma com o tipo de atribuição da sua extensão (`VHDL_FILE`, `VERILOG_FILE`, `SYSTEMVERILOG_FILE`, `QIP_FILE`).

## 2. Origem dos dados

| Dado | Origem |
| :--- | :--- |
| Texto da família | `quartus_family` do arquivo de família |
| Dispositivo | `device` do `board.yaml` |
| Fontes | O fecho do `sources` (`--target`), mais os arquivos gerados |
| Pinos e atribuições do PLL | Anexados ao fim, escritos pelos geradores de pinos e de PLL |

O módulo não escreve atribuições por pino, e uma lista de fontes só entra pelo fecho dos `provides`.

## 3. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Família, dispositivo, topo, `.sdc` e fontes geradas no `.qsf` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
