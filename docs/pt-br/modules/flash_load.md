# `flash_load`

Grava a FLASH que fica na SDRAM pela porta de debug, com o núcleo preso, e confere a gravação pelo CRC-32 que a placa calcula. É o que o `riscv-tools load-flash`, o `flash-image send --via debug` e o método `sdram_debug` do [`rom_writer`](rom_writer.md) usam.

## 1. Fluxo

1. O bitstream precisa anunciar `HOLD` e CRC ([`sdram_debug`](sdram_debug.md), seção 3.1). Sem os dois, a gravação é recusada antes de qualquer escrita, porque o núcleo e a JTAG escreveriam a FLASH ao mesmo tempo e as caches guardariam linhas antigas.
2. O núcleo é preso em reset. O reset limpa as linhas válidas da cache de instruções, então o núcleo que sai do reset busca da SDRAM.
3. O conteúdo é escrito em rajada. Os primeiros bytes de um banco, o cabeçalho de 256 bytes, vão por último, e uma gravação interrompida deixa um banco que a BOOT não valida.
4. O CRC-32 do trecho, calculado na placa, é comparado com o do conteúdo.
5. O núcleo é solto, também quando a conferência falha, e a BOOT escolhe o banco íntegro de maior versão.

O botão de reset da placa reinicia só o núcleo, então o conteúdo da FLASH sobrevive a ele. Uma reconfiguração do FPGA apaga a SDRAM, e a FLASH é gravada de novo depois dela.

## 2. Pedido

| Verificação | Erro |
| :--- | :--- |
| Conteúdo vazio | `the image is empty` |
| Endereço ou cabeçalho que não é de palavra | `the address and the header must be words` |
| Trecho fora da região `FLASH` | `is outside the FLASH` |
| Bitstream sem `HOLD` e CRC | `no hold and CRC` |
| CRC da placa diferente do conteúdo | `CRC-32 of the board` |

## 3. ELF

`load_segments` lê os segmentos `PT_LOAD` de um ELF de 32 bits little-endian, e `flat_binary` os junta num binário contínuo com zeros nos vãos. Com `--bank`, o `load-flash` empacota o binário com o cabeçalho do banco, e o programa precisa começar 256 bytes depois da base do banco. Sem `--bank`, um ELF de um segmento é gravado no endereço de carga dele.

## 4. Comando

```bash
uv run riscv-tools --config config.yaml load-flash --platform src/platform.yaml --elf app.elf --bank A --version 3
uv run riscv-tools --config config.yaml load-flash --image img.bin --bank A
uv run riscv-tools --config config.yaml load-flash --image raw.bin --address 0x1000
```

## 5. Testes

`tests/test_flash_load.py` roda o fluxo contra um modelo da placa: a rajada, o `HOLD`, a ordem do cabeçalho, o CRC, os pedidos recusados e o ELF.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
