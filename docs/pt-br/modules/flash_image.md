# `flash_image`

Empacota um programa na imagem de uma banca da FLASH, confere uma imagem e a envia, pela UART JTAG, ao programa que atualiza a FLASH. O módulo só conhece o formato da imagem; quem apaga e grava a FLASH é a rotina de atualização do sistema, e o mapa das bancas vem do `platform.yaml` (ver [`memory_map`](memory_map.md)).

## 1. Formato da imagem

Uma banca começa por uma página de cabeçalho de 256 bytes, e o programa (a carga) vem logo depois. Os campos são palavras de 32 bits em little-endian, e o resto da página fica no estado apagado (`0xFF`). A rotina de atualização grava a carga primeiro e a página do cabeçalho por último, então uma banca sem cabeçalho válido é uma banca cuja atualização não terminou.

| Deslocamento | Campo | Conteúdo |
| :--- | :--- | :--- |
| 0 | magia | `0x52564946` |
| 4 | tamanho | bytes da carga, múltiplo de 4 |
| 8 | crc | CRC-32 (IEEE 802.3, o do zlib) da carga |
| 12 | versão | versão da imagem; a maior é a mais nova |
| 16 | crc do cabeçalho | CRC-32 dos primeiros 16 bytes |

A carga é o `.bin` que o linker gerou para a banca, preenchido com `0xFF` até um múltiplo de 4 bytes. O programa de uma banca é ligado a partir de `base + 256` (símbolos `BANK_<nome>_PAYLOAD` do mapa).

## 2. Funções

| Função | Faz |
| :--- | :--- |
| `pack(payload, version, bank_size)` | devolve a página do cabeçalho seguida da carga; recusa carga vazia, versão fora de $[0, 2^{32}-2]$ e imagem maior que a banca |
| `parse_header(image)` | lê e valida o cabeçalho (magia, CRC do cabeçalho, tamanho); uma banca apagada é recusada pela magia |
| `verify(image)` | confere o cabeçalho, o comprimento e o CRC da carga |
| `send_image(link, image, on_bytes)` | entrega os bytes da imagem, em ordem e em blocos de 16 KiB, à UART JTAG; o programa lê o cabeçalho e depois a quantidade de bytes que ele indica |

## 3. Comando

```bash
riscv-tools --root <projeto> flash-image pack programa.bin --output imagem.bin --version 3 --platform src/cyclone-v/de0-cv/platform.yaml --bank B
riscv-tools flash-image verify imagem.bin
riscv-tools --config <config.yaml> flash-image send imagem.bin
```

`pack` com `--platform` e `--bank` confere que a imagem cabe na banca. `send` exige `--config` e confere a imagem antes de enviá-la; o que o programa imprime durante o envio vai para a saída padrão. `pack` e `verify` não precisam de `--config`.

## 4. Pré-requisitos

- `send`: Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha a UART JTAG.

## 5. Testes

`tests/test_flash_image.py` cobre o formato, os danos que a conferência precisa pegar e o envio contra um leitor substituto.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
