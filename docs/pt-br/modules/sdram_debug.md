# `sdram_debug`

Lê e escreve palavras da SDRAM pela porta de debug JTAG dela: o equivalente do [`mem_edit`](mem_edit.md) para uma memória que fica fora da FPGA. A porta de debug é um segundo mestre do controlador da SDRAM, atrás de uma instância de JTAG virtual (o protocolo de palavra está em [`docs/pt-br/ram/sdram_debug.md`](https://github.com/insper-riscv/Memory/blob/main/docs/pt-br/ram/sdram_debug.md) do Memory), então o host lê e escreve a memória com o núcleo rodando, parado ou preso.

Um endereço de palavra conta palavras de 32 bits a partir do início do chip, e não da base de uma região. A conversão do endereço de byte do SoC para a palavra do chip é da [`sdram_windows`](sdram_windows.md). O [`ram_target`](ram_target.md) escolhe entre este módulo e o `mem_edit` para a RAM de um projeto, e o [`flash_load`](flash_load.md) usa as operações da seção 3 para gravar a FLASH.

## 1. Funções

| Função | Faz |
| :--- | :--- |
| `read_words(link, word_address, word_count)` | lê palavras contíguas |
| `write_word(link, word_address, value, byte_enable)` | escreve uma palavra, os bytes por `byte_enable` |
| `fill(link, word_address, word_count, value)` | preenche um intervalo; quem executa é a placa, então zerar os 64 MB leva cerca de dois segundos |
| `load_words(link, word_address, words)` | escreve palavras contíguas numa sessão, uma por comando |
| `capabilities(link)` | lê o que o bitstream sabe fazer (seção 3.1) |
| `set_hold(link, hold)` | prende ou solta o núcleo em reset |
| `crc32(link, word_address, word_count)` | CRC-32 de um trecho, calculado na placa |
| `stream_write(link, word_address, words, burst)` | escreve em rajada de `burst` palavras por deslocamento; o resto, que não completa uma rajada, vai palavra a palavra |
| `stream_read(link, word_address, word_count, burst)` | lê em rajada, com o mesmo tratamento do resto |

## 2. Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_backend` | `sdram_debug` faz da RAM a SDRAM atrás desta porta; o padrão, `ismce`, é uma instância de memória da FPGA |
| `quartus.sdram_debug_instance` | Índice da instância de JTAG virtual da porta de debug (3 no topo gerado) |

## 3. Contrato com o Memory

Esta seção é o contrato que o `sdram_dbg_master` e o `sdram_jtag_core` do Memory cumprem para o hospedeiro gravar a FLASH em rajada. O hospedeiro só usa uma operação que a palavra de capacidades (seção 3.1) anuncia, e um bitstream que não a anuncia continua funcionando com as funções da seção 1 que já existiam.

O registrador `DEBUG` (instrução 1 do nó de JTAG virtual) mantém o formato de 64 bits de hoje.

| Sentido | Campos |
| :--- | :--- |
| Entrada | `op` nos bits 63 a 60, `be` nos bits 59 a 56, palavra nos bits 55 a 32, dado nos bits 31 a 0 |
| Saída | status nos bits 63 a 56, última palavra nos bits 55 a 32, dado lido nos bits 31 a 0 |

O bit 24 do endereço de palavra viaja no bit 3 do `op`, como nas outras operações. O status tem `ocupado` (bit 0), `erro` (bit 1), `SDRAM inicializada` (bit 2) e `sobrecarga` (bit 3). A operação 7, hoje livre, passa a ser `CONTROLE`, e o campo `be` escolhe o subcomando.

| `be` | Subcomando | Entrada | Efeito e resposta |
| :--- | :--- | :--- | :--- |
| 0 | `INFO` | nenhuma | A resposta traz a palavra de capacidades (seção 3.1) |
| 1 | `HOLD` | bit 0 do dado | 1 prende o núcleo em reset e 0 o solta; a resposta devolve o nível atual |
| 2 | `CRC_INICIA` | palavra inicial no campo de palavra e contagem de palavras no dado | Zera o acumulador e percorre as palavras pelo mestre B; fica `ocupado` até acabar |
| 3 | `CRC_LE` | nenhuma | A resposta traz o CRC-32 do último `CRC_INICIA` |
| 4 | `PONTEIRO` | palavra inicial no campo de palavra | Carrega o ponteiro de rajada de leitura e de escrita; a leitura já busca a primeira rajada |

Um subcomando que o bitstream não implementa responde com o dado zero e sem o bit de erro, de modo que `INFO` de um bitstream antigo lê zero e nada é anunciado.

### 3.1. Palavra de capacidades

| Bits | Campo |
| :--- | :--- |
| 7 a 0 | Versão do contrato, 1 neste documento |
| 15 a 8 | Palavras por deslocamento da rajada, de 1 a 128 (1024 a 4096 bits no máximo); 0 sem rajada |
| 16 | Existe o `HOLD` |
| 17 | Existe o `CRC_INICIA` e o `CRC_LE` |

### 3.2. O CRC-32

O acumulador começa em `0xFFFFFFFF`, processa os bytes de cada palavra do menos para o mais significativo (little-endian, a ordem de memória) com o polinômio refletido `0xEDB88320` e termina com a inversão dos 32 bits, o mesmo resultado de `zlib.crc32` sobre os bytes do trecho. O cálculo roda no clock do controlador e lê as palavras pelo mestre B, então concorre com o núcleo e com a outra cache pelo rodízio do árbitro.

### 3.3. A rajada

A rajada usa duas instruções do nó de JTAG virtual, além da instrução 1.

| Instrução | Registrador | Efeito |
| :--- | :--- | :--- |
| 2 | `STREAM_WRITE`, $32 N$ bits com $N$ o campo de rajada | O deslocamento carrega $N$ palavras, a palavra 0 nos bits 31 a 0. Na atualização do registrador as $N$ palavras vão, com todos os bytes habilitados, a $N$ endereços consecutivos a partir do ponteiro, que avança $N$ |
| 3 | `STREAM_READ`, $32 N$ bits | Na captura do registrador, as $N$ palavras já buscadas a partir do ponteiro estão nos bits, a palavra 0 nos bits 31 a 0. Na atualização o ponteiro avança $N$ e o hardware busca as $N$ palavras seguintes |

Entre dois deslocamentos o hospedeiro volta à instrução 1 e lê o status até `ocupado` cair. Enquanto o buffer de $N$ palavras é escoado (escrita) ou preenchido (leitura), o status fica `ocupado`, e um deslocamento enquanto `ocupado` seria perdido, o que o hospedeiro nunca faz. O ponteiro é carregado pelo subcomando `PONTEIRO` antes da primeira rajada, e a contagem de uma chamada é sempre múltiplo de $N$, o resto sendo tratado pelas operações de palavra.

O botão de reset da placa reinicia apenas o núcleo. O `HOLD` e o acumulador do CRC só voltam ao valor inicial com a perda do travamento do PLL.

## 4. Pré-requisitos

- Quartus Prime Lite no `PATH` (`quartus_stp`) e uma placa com USB-Blaster cujo projeto tenha a porta de debug.

## 5. Testes

`tests/test_sdram_debug.py` roda as funções de palavra contra um substituto do script, e `tests/test_flash_load.py` roda `capabilities`, `set_hold`, `crc32` e a rajada contra um modelo da placa que segue o contrato da seção 3. Na placa, a plataforma `de0-cv` do Insper-RISC-V roda a suíte de hardware real por este módulo.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).

## Compatibilidade explícita com Memory v0.6

`JtagLink(..., sdram_protocol="memory-v0.6")` seleciona os comandos implementados
pelo mestre SDRAM dessa versão: controle 0 para hold, 1 para CRC e 2 para seek.
O protocolo padrão continua sendo `capabilities`; não há fallback automático.

Como essa interface não possui INFO, o adaptador verifica hold pelo bit de
status e confere o CRC de uma palavra contra um cálculo independente no host,
sem escrever na SDRAM. O estado anterior de hold é restaurado após a sondagem.
Cada transição posterior de hold também é confirmada antes da transferência.
A sondagem pausa a CPU e pode reiniciar o programa quando libera o reset; ela
é usada como preparação do carregamento, não como consulta inofensiva durante
a execução de uma aplicação.

A moldura de rajada é diferente nessa versão, portanto o adaptador usa sessões
de até 1024 palavras com os comandos de palavra existentes. A imagem de banco
é validada antes da escrita, tem tamanho limitado pelo cabeçalho e recebe o
cabeçalho por último. O CRC da imagem completa é conferido na placa. Hardware
que não confirma hold ou CRC é recusado.
