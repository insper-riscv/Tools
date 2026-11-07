# `pin_assignments`

Escreve as atribuições de pino e de padrão de E/S do `.qsf`, derivando as demais do papel.

## 1. Função

É o único lugar que escreve `set_location_assignment` e as atribuições por instância dos pinos. A posição e o padrão de E/S vêm do `pins.yaml`. As demais atribuições derivam do papel da porta e nunca são copiadas de um `.qsf`.

## 2. Atribuições derivadas

| Papel | Atribuições |
| :--- | :--- |
| `sdram` | `FAST_OUTPUT_REGISTER` nas saídas e bidirecionais; `FAST_OUTPUT_ENABLE_REGISTER`, `FAST_INPUT_REGISTER` e `PAD_TO_INPUT_REGISTER_DELAY 0` nos bidirecionais; nenhuma no relógio do pino |
| `leds`, `display` | `CURRENT_STRENGTH_NEW DEFAULT` e `SLEW_RATE 1`; a família com `slew_rate: false` (MAX 10, cujo ajuste recusa a opção nos pinos 3.3-V LVTTL) recebe só a primeira |

## 3. Recusas

| Condição | Mensagem |
| :--- | :--- |
| Pino `inferred` sem `--accept-inferred-pins` (V16) | `E pin M16 for SPI_FLASH_CS is inferred, not confirmed; pass --accept-inferred-pins` |
| Dois sinais no mesmo pino | `E pin X is assigned to both A and B` |

Só os sinais das portas usadas entram na checagem, de modo que os apelidos de pino do `conflicts` do `pins.yaml` que o topo não usa nunca são atribuídos.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_pin_assignments.py` | Posições e padrões, registradores de E/S e atribuições de LED derivados do papel, família sem variação de tensão lenta, V16 e pino repetido |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
