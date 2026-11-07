# `quartus_reports`

Lê os resumos de recursos que o Quartus escreve ao fim da síntese e do ajuste. O módulo só lê: as capacidades da placa, os limites e a política de cabimento ficam em `fit_estimate`.

## Arquivos lidos

| Arquivo | Conteúdo |
| :--- | :--- |
| `<revisão>.map.summary` | Resumo da síntese, linhas `Nome : valor`; a linha de lógica das famílias de ALM traz `N/A` |
| `<revisão>.map.rpt` | Tabela "Analysis & Synthesis Resource Usage Summary" (estimativa de ALMs ou elementos lógicos) e a hierarquia por entidade |
| `<revisão>.fit.summary` | Resumo do ajuste, com cada recurso e a sua capacidade (`8,058 / 18,480 ( 44 % )`) |
| `<revisão>.fit.rpt` | Tabela "Fitter Resource Usage Summary", usada quando não há `fit.summary` |

## Unidades por família

| Família | Lógica | Multiplicadores | RAM interna |
| :--- | :--- | :--- | :--- |
| Cyclone V | ALMs | `Total DSP Blocks` (blocos DSP; a 5CEBA4 tem 66) | `Total block memory bits` e `Total RAM Blocks` |
| Cyclone IV E, MAX 10, Cyclone 10 LP | `Total logic elements` | `Embedded Multiplier 9-bit elements` | `Total memory bits` |

## Funções

| Função | Faz |
| :--- | :--- |
| `parse_summary(texto)` | lê um `*.map.summary` ou `*.fit.summary`; sem nenhuma linha de recurso é erro |
| `parse_map_report(relatório, resumo)` | lê a estimativa de lógica da síntese, os pinos e PLLs do resumo e a hierarquia até uma profundidade |
| `parse_fit_report(relatório, resumo)` | lê o ajuste, cada recurso com a sua capacidade |
| `parse_entities(relatório, profundidade)` | linhas da tabela de uso por entidade (ALUTs, registradores e bits de memória, com os dos filhos) |
| `parse_quantity(texto)` | lê `8,058 / 18,480 ( 44 % )` ou `4638`; `N/A` devolve `None` |
| `succeeded(uso)` | verdadeiro quando o estado do passo começa por `Successful` |

## Testes

`tests/test_quartus_reports.py` lê os arquivos reais de uma síntese e de um ajuste da Cyclone V (`tests/fixtures/quartus_reports/cyclone-v`) e um resumo de família de elementos lógicos, e confere o erro de arquivo sem recursos.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
