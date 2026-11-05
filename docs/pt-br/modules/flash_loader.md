# `flash_loader`

Grava e lê a FLASH interna de uma só cópia pelo carregador JTAG dela: o equivalente do [`mem_edit`](mem_edit.md) para uma FLASH de duas portas, que o Quartus Lite não deixa regravar pelo In-System Memory Content Editor. O carregador é uma instância de JTAG virtual diante da porta B da FLASH (o protocolo está em `docs/pt-br/rom/flash_loader.md` do Memory) e só escreve com o núcleo parado.

Um endereço de palavra conta palavras de 32 bits a partir do início do IP da FLASH. O [`rom_writer`](rom_writer.md) escolhe entre este módulo e o `mem_edit` pela chave `quartus.rom_write_method`.

## Funções

| Função | Faz |
| :--- | :--- |
| `load_image(link, words, word_address, restart)` | para o núcleo, grava a imagem em poucas varreduras longas, confere a contagem e a soma de verificação que o carregador informa e, com `restart` verdadeiro, libera o núcleo, que reinicia pela BOOT_ROM |
| `read_words(link, word_address, word_count)` | para o núcleo e lê palavras contíguas; o núcleo continua parado |
| `halt(link)` | para o núcleo |
| `release(link)` | libera o núcleo |
| `image_checksum(first_word, words)` | soma de cada palavra com o endereço dela, módulo $2^{32}$, a mesma que o carregador mantém |

$$\text{soma} = \sum_{i} \left( \text{palavra}_i + \text{endereço}_i \right) \bmod 2^{32}$$

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.rom_write_method` | `jtag_loader` faz do `rom_writer` um chamador deste módulo; o padrão, `mem_edit`, usa o In-System Memory Content Editor |

## Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha o carregador da FLASH (a plataforma `internal-mem` do Insper-RISC-V).

## Testes

`tests/test_flash_loader.py` roda o módulo contra um substituto do script. Na placa, a suíte de hardware da plataforma `internal-mem` passa por ele.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
