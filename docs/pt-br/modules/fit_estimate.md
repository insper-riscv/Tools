# `fit_estimate`

Estima se um perfil cabe numa placa e julga o resultado. A estimativa soma o custo de cada bloco do perfil com a tabela de calibração da família (um arquivo de dados, substituível); a mesma política julga a estimativa e o relatório do ajuste do Quartus.

## Política

As constantes são do Tools e não há opção para forçar o resultado.

| Utilização $ de um recurso | Resultado |
| :--- | :--- |
|  \le 0{,}85$ | passa |
| /bin/bash{,}85 < u \le 1{,}00$ | aviso (a estimativa erra algumas unidades percentuais; só o ajuste decide) |
|  > 1{,}00$ | erro |

A lógica estimada só falha quando a família está validada, isto é, o erro máximo de validação da tabela é de até 10 %. Antes disso o resultado é o aviso V18 e o ajuste decide.

## Mensagens

| Regra | Origem | Gravidade |
| :--- | :--- | :--- |
| V11 | blocos de RAM da memória emulada e das caches acima do orçamento | erro; aviso entre 85 % e 100 % |
| V12 | lógica estimada acima da capacidade | erro |
| V13 | lógica estimada entre 85 % e 100 % | aviso |
| V14 | relatório do ajuste estoura recursos; todos são listados de uma vez (lógica, bits e blocos de RAM, multiplicadores, PLLs, pinos) | erro; aviso na faixa de 85 % a 100 % |
| V18 | família sem calibração, ou coeficiente sem medida | aviso |

## Tabela de calibração

`boards/calibration/<família>.yaml` traz a unidade (`alm` ou `le`), os coeficientes, o erro (`rms_pct`, `max_pct`, perfis de validação e `map_to_fit_ratio`) e o Fmax por grau. Um coeficiente `null` é uma medida ainda não feita e faz o estimador emitir V18. As chaves de extensões, extras, periféricos e controladores vêm do vocabulário dos catálogos, e uma chave fora dele é recusada.

O custo lógico estimado é

$$ \hat{L} = r \left( L_{nucleo} + \sum_e L_e + L_{hpm}(n, w) + \sum_c L_c(s_c) + \sum_p L_p + \sum_b L_b \right) $$

com {hpm} = a_0 + a_1 n + a_2 n w$,  = c_0 + c_1 s_c$ e $ a razão entre o ajuste e a síntese (`map_to_fit_ratio`, 1 quando não medida). Os blocos de RAM são

$$ N_{blocos} = \sum_m \left\lceil \frac{8 s_m}{b_{bloco}} \right\rceil + N_{caches} + N_{regs} $$

As implicações da ISA valem na função `terms`: Zicntr e Zihpm implicam Zicsr, M implica Zmmul, e Sscofpmf exige Zihpm e interrupções. A calibração usa a mesma função para ajustar, de modo que o ajuste e a estimativa não divergem.

## Funções

| Função | Faz |
| :--- | :--- |
| `estimate(spec, tabela, capacidade, placa)` | blocos, lógica e as mensagens V11, V12, V13 e V18 |
| `terms(spec, bits_por_bloco)` | valor de cada termo do modelo para um perfil |
| `estimate_logic(spec, tabela, bits_por_bloco)` | soma dos termos com coeficiente e a lista dos que não têm |
| `blocks_needed(spec, bits_por_bloco)` | blocos de RAM do perfil |
| `report_findings(uso, capacidade)` | V14 a partir do relatório do ajuste |
| `classify(usado, total)` | aplica a política |
| `capacity_from_resources(mapa)`, `load_capacity(arquivo)` | capacidades a partir do `resources` de um `board.yaml` |
| `load_table(arquivo, vocabulário)`, `table_from_mapping`, `empty_table` | tabela de calibração |

## Comando

```bash
riscv-tools --root . check-fit --reports <pasta com *.fit.summary> --board boards/<placa>/board.yaml
```

Lista todos os recursos que passam da capacidade e sai com status 1 quando há erro.

## Testes

`tests/test_fit_estimate.py` cobre os limiares, a ausência de opção de forçar, as implicações da ISA, a soma sobre tabelas fictícias, cada mensagem V11 a V14 e V18, a tabela vazia, a validação do vocabulário e o comando `check-fit`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
