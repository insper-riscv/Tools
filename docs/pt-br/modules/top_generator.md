# `top_generator`

Gera o topo fino da placa, que só liga o PLL, o SoC, um backend por região e o anel de pinos.

## 1. Função

O topo gerado não tem lógica além do reset. Ele liga, nesta ordem, as portas da placa, o PLL (módulo Verilog, instanciado por componente), a instância da entidade `soc`, a boot memory, os papéis de E/S, o console e um backend por região externa, com o anel de pinos de três estados.

## 2. Conteúdo

| Parte | Origem |
| :--- | :--- |
| Generics `HPM_COUNTERS` e `HPM_WIDTH` | Presentes quando o perfil tem Zihpm, repassados ao SoC |
| Reset | Reset do usuário normalizado para ativo em `'1'`, reset do SoC liberado dois ciclos de `core` depois do PLL travar |
| Generics do SoC | Constantes do pacote do mapa (`generate.vhdl.package`), entre elas `periph_count`, `periph_bases` e `periph_masks` (as tabelas `PERIPH_*`), `strict_periph` e um `<periférico>_index` (`clint_index`, `plic_index`, `uart_jtag_index`, `flash_ctrl_index` e assim por diante) para cada periférico que a plataforma lista, lido do `<NOME>_INDEX`, de modo que o topo não fixa número de periférico; sem PLIC na plataforma, os generics de PLIC e CLINT levam os valores padrão do SoC, de modo que o topo nunca lê constantes que o pacote não tem; os generics de extensão de ISA não são passados, o SoC os lê do `config_pkg` da plataforma |
| Polaridade | Generics `switches_active_low`, `keys_active_low` e `display_active_low` do SoC; chaves e botões são portas `inout` ligadas direto aos pinos do GPIO |
| Backend `emulado` da FLASH | `flash_chip` (latências de `memory.rom.latency`), `flash` de duas portas, `flash_loader` e `flash_jtag_shell`; o carregador segura o SoC em reset enquanto escreve |
| Atualização de programa | Com o periférico `FLASH_CTRL`, o SoC leva o controlador (`has_flash_ctrl`) e o backend da FLASH acrescenta o `flash_cmd_port` na porta B do armazenamento, que o carregador toma com o núcleo parado, e devolve a região regravada ao SoC para derrubar as linhas das caches |
| Cortes de caminho crítico | O topo liga `registered_irqs`, `fast_icache_select` (com o relógio de busca definido) e a página do topo da RAM fora da cache de dados (`RAM_LAST_PAGE`), os mesmos cortes do topo escrito à mão |
| Backend `emulado` da RAM | `onchip_ram_port` sobre o bloco `ram`, com a latência pedida |
| Backend `dispositivo/sdram` | Duas pontes (dados e instruções), `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` e um `tristate_buffer_1bit` por bit do dado em um `generate`; a largura de 16 ou 32 bits e os bits de linha, coluna e banco vêm do chip e de `memories.sdram.chips` |
| Backend `dispositivo/nor` | `nor_flash_ctrl` de 8 bits com leitura em página e os comandos da atualização de programa, e o anel de pinos da FLASH |

## 3. O que o topo não liga

Um backend sem entidade (`sram`, `flash-interna` e `serial`) não gera instância: o topo avisa e deixa a região parada. O SoC não exporta o papel de LEDs: os pinos de LED ficam no nível apagado, menos o primeiro, que acende com a bandeira de falha que o hospedeiro grava no display (nó Virtual JTAG de índice 2). O texto de cada backend fica em `templates/`, com os nomes e as portas reais das entidades do Memory.

### 3.1. Vídeo

Quando a plataforma pede vídeo, o `TopSpec` carrega o `VideoPlan` e `video_generics` escreve os generics de temporização, de largura de canal e de framebuffer ([board_video](board_video.md)). O topo não instancia o periférico de vídeo, e o mapa de generics do SoC não os recebe.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Conteúdo do topo da DE0-CV, latências, anel de pinos, polaridade e sintaxe aceita pelo GHDL |
| `tests/test_board_video_generate.py` | Os generics de vídeo chegam ao `TopSpec` sem alterar o topo |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
