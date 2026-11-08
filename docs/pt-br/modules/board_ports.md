# `board_ports`

Monta as portas do topo de uma placa (nome, largura, direção e pino de cada bit) a partir dos papéis.

## 1. Função

Transforma o relógio de referência, o reset, os papéis de E/S, o console por pinos e as memórias de dispositivo em portas. Os geradores de pinos, de `.sdc` e de topo leem as mesmas portas, de modo que nome, largura e pino de cada sinal nascem uma só vez.

## 2. Regras

| Regra | Efeito |
| :--- | :--- |
| Formatos de barramento | `LEDR[3]` e `LEDR3` formam o vetor `LEDR`; um radical com um só membro sem colchetes fica escalar |
| Display | Uma porta `HEX<d>` de 7 bits por dígito, a partir de `HEX[5:0][6:0]` |
| Memória | Os sinais com o prefixo do grupo e `_` (`DRAM_`) formam uma porta por radical; `signals` pode ser uma lista de prefixos |
| Papel obrigatório ausente | Erro V5 |
| Papel opcional ausente | Aviso V6 e nenhuma porta |
| Console `pinos` sem UART | Erro V4 |
| Reset em um bit de outro papel (`KEY[0]`) | Vira apelido (`KEY(0)`) da porta do papel, sem pino próprio, para o pino não ser atribuído duas vezes; sem o papel, vira a porta escalar `KEY_0` |

## 3. Relógio que sai pelo pino

A função `memory_clock_port` acha a porta escalar de saída cujo nome termina em `CLK` dentro de um grupo de memória, o relógio que o `.sdc` constrange.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_ports.py` | Portas da DE0-CV, nomes planos, apelido de reset, grupos com dois prefixos, SRAM, V4 a V6 e plano de relógios |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
