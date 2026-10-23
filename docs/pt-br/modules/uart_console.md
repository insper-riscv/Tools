# `uart_console`

Mostra o que um programa imprime enquanto roda, pela UART JTAG da plataforma: uma UART cuja outra ponta é uma instância de JTAG virtual (os registradores e o protocolo de varredura estão no `docs/EXTERNAL_BUS.md` do Memory). É a visão ao vivo ao lado do [`sdram_debug`](sdram_debug.md), que lê o buffer de stdout depois do fato: a UART mostra a saída de um programa que ainda roda, ou que travou, e dá entrada a ele.

O console varre a UART em sequência; cada varredura traz até quatro bytes. A UART é a segunda instância de JTAG virtual do projeto; a porta de debug da SDRAM é a primeira.

## Funções

| Função | Faz |
| :--- | :--- |
| `read_console(link, on_bytes, seconds, send)` | escuta por `seconds` segundos (0 até ser interrompido), chama `on_bytes` com cada trecho assim que chega, entrega ao programa antes os bytes de `send`, e devolve tudo o que leu |
| `decode_line(line)` | decodifica uma linha de saída do script em bytes, ou `None` para uma linha sem dados |

## Comando

```bash
riscv-tools --config <config.yaml> console [--seconds N] [--send TEXTO]
```

Um programa só imprime na UART depois que um host a varreu, então inicie o console antes ou durante a execução; um programa que não encontra ninguém ouvindo não espera por ninguém. Quando o programa imprime mais rápido que o console lê (cerca de quatro bytes por varredura), ele espera espaço na fila até um limite e então descarta o byte; o buffer de stdout na SDRAM guarda todos os bytes até o tamanho dele.

## Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha a UART JTAG (a plataforma da SDRAM do TopLevel).

## Testes

`tests/test_uart_console.py` roda o módulo contra um substituto do script. Em simulação, a plataforma da SDRAM do TopLevel lê a UART do mesmo jeito durante cada programa e compara o fluxo com o buffer de stdout.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
