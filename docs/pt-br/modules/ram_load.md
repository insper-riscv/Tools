# `ram_load`

Carrega um ou mais arquivos na SDRAM pela porta de debug JTAG ([`sdram_debug`](sdram_debug.md)), lê cada um de volta para conferir e só então escreve a magia na palavra `launch`, que avisa o programa da placa que a imagem está completa. É o subcomando `load-ram`.

## 1. Fluxo

| Passo | Operação |
| :--- | :--- |
| 1 | A palavra `launch` é zerada, para que uma magia antiga não dispare uma imagem pela metade |
| 2 | Cada arquivo é escrito por `sdram_debug.load_words` numa só sessão do script |
| 3 | O arquivo é lido de volta em blocos de 65.536 palavras e comparado; a primeira diferença aborta a carga, com a magia ainda sem escrever |
| 4 | A magia é escrita em `launch`, sempre por último |

Antes do passo 1 o pedido inteiro é validado: endereços alinhados a palavra, dentro da SDRAM, sem sobreposição e sem cobrir `launch`. Um pedido inválido não escreve nada. O último bloco de um arquivo cujo tamanho não é múltiplo de 4 é completado com zeros.

## 2. Configuração

| Chave | Significado |
| :--- | :--- |
| `memory.ram_base` | Endereço de byte da base da SDRAM, o endereço padrão do binário |
| `memory.ram_words` | Tamanho da SDRAM em palavras, que limita os segmentos |
| `memory.launch_addr` | Endereço da palavra `launch`, que o mapa da plataforma reserva em `reserved.launch` |

## 3. Opções

| Opção | Significado |
| :--- | :--- |
| `binary` | Arquivo carregado em `--address` |
| `--address` | Endereço de byte do binário; a base da SDRAM quando omitido |
| `--wad` e `--wad-address` | Segundo arquivo e o endereço dele, acima do binário; os dois juntos |
| `--launch-address` | Endereço da palavra `launch`, no lugar de `memory.launch_addr` |
| `--magic` | Valor escrito em `launch`, `0x4D4F4F44` por padrão |
| `--no-launch` | Carrega sem escrever a magia |
| `--no-verify` | Pula a leitura de volta |

## 4. Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha a porta de debug da SDRAM e o programa que consulta `launch` (a plataforma `doom` do Insper-RISC-V).

## 5. Testes

`tests/test_ram_load.py` roda o módulo contra uma SDRAM simulada em memória no lugar do script: ordem das escritas (magia por último), diferença na leitura de volta, pedidos inválidos, uma WAD de 4.196.020 bytes e o subcomando.

## 6. Uso

```bash
uv run riscv-tools --config src/cyclone-v/doom/config.yaml load-ram doom.bin \
    --wad doom1.wad --wad-address 0x40100000
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
