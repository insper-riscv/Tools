# `display`

Lê e escreve o registrador do display de sete segmentos da plataforma pelo JTAG virtual: os seis dígitos são um registrador de 24 bits que o programa ou o hospedeiro escreve (o bloco `seg_display` está no repositório [Peripherals](https://github.com/insper-riscv/Peripherals)). O módulo também guarda a bandeira de falha da sessão, que mantém o primeiro LED vermelho aceso, e é com ele que o `run` e o `certify-board` mostram o programa em execução.

## Funções

| Função | Faz |
| :--- | :--- |
| `read_display(link)` | lê o valor de 24 bits do registrador |
| `write_display(link, value)` | escreve um valor de até 24 bits e devolve o que a placa confirma |
| `write_fail(link, failed)` | acende ou apaga a bandeira de falha (o primeiro LED vermelho) |
| `check_display(link, count)` | escreve `count` valores pseudoaleatórios e lê cada um de volta, para provar o caminho do JTAG até o registrador |
| `encode_test(number)` | valor do registrador enquanto roda o programa de número `number` (de 1 a 999999), com os seis dígitos em decimal |
| `encode_act(number)` | valor do registrador enquanto roda o ELF de número `number` do ACT4 (de 1 a 9999): `A` e `C` em HEX5 e HEX4 e o número em decimal em HEX3 a HEX0, de modo que o primeiro ELF mostra `AC0001` |

## Comando

```bash
riscv-tools --config <config.yaml> display [VALOR | --check N]
```

Sem argumento o comando só lê o registrador. Com `VALOR` (seis dígitos hexadecimais, HEX5 primeiro) ele o escreve, e `--check N` roda a verificação de `N` escritas e leituras e termina com status 1 se algum valor voltar diferente.

O `run` mostra o número do programa quando `orchestrator.board_display` é verdadeiro, e o `certify-board`, o do ELF quando `act.board_display` é verdadeiro. Nos dois casos o primeiro LED vermelho fica aceso depois da primeira falha ou do primeiro tempo esgotado.

## Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha o registrador do display atrás de uma instância de JTAG virtual (a `de0-cv` do Insper-RISC-V).

## Testes

`tests/test_display.py` cobre a codificação dos números, a leitura da saída do script e a recusa de valores fora da faixa. `tests/test_runner_display.py` cobre o uso do display pelo `run`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
