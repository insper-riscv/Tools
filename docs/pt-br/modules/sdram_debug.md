# `sdram_debug`

Lê e escreve palavras da SDRAM pela porta de debug JTAG dela: o equivalente do [`mem_edit`](mem_edit.md) para uma RAM que fica fora da FPGA. A porta de debug é um segundo mestre do controlador da SDRAM, atrás de uma instância de JTAG virtual (o protocolo está no `docs/SDRAM_DEBUG.md` do Memory), então o host lê e escreve a memória com o core rodando, parado ou travado.

Um endereço de palavra conta palavras de 32 bits a partir da base da SDRAM. O [`ram_target`](ram_target.md) escolhe entre este módulo e o `mem_edit` para a RAM de um projeto; os outros módulos não o chamam direto.

## Funções

| Função | Faz |
| :--- | :--- |
| `read_words(link, word_address, word_count)` | lê palavras contíguas |
| `write_word(link, word_address, value, byte_enable)` | escreve uma palavra, os bytes por `byte_enable` |
| `fill(link, word_address, word_count, value)` | preenche um intervalo; quem executa é a placa, então zerar os 64 MB leva cerca de dois segundos, e não um deslocamento por palavra |

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_backend` | `sdram_debug` faz da RAM a SDRAM atrás desta porta; o padrão, `ismce`, é uma instância de memória da FPGA |

## Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha a porta de debug (a plataforma da SDRAM do TopLevel).

## Testes

`tests/test_sdram_debug.py` roda o módulo contra um substituto do script. Na placa, a plataforma da SDRAM do TopLevel roda a suíte de hardware real por ele.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
