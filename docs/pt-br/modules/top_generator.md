# `top_generator`

Gera o topo fino da placa, que só liga o PLL, o SoC, um backend por região e o anel de pinos.

## 1. Função

O topo gerado não tem lógica além do reset. Ele liga, nesta ordem, as portas da placa, o PLL (módulo Verilog, instanciado por componente), a instância da entidade `soc`, a boot memory, os papéis de E/S, o console e um backend por região externa, com o anel de pinos de três estados.

## 2. Conteúdo

| Parte | Origem |
| :--- | :--- |
| Generics `HPM_COUNTERS` e `HPM_WIDTH` | Presentes quando o perfil tem Zihpm, repassados ao SoC |
| Reset | Reset do usuário normalizado para ativo em `'1'`, reset do SoC liberado dois ciclos de `core` depois do PLL travar |
| Generics do SoC | Constantes do pacote do mapa (`generate.vhdl.package`), entre elas `periph_count`, `periph_bases` e `periph_masks` (as tabelas `PERIPH_*`, que o topo passa pela conversão `work.interconnect_pkg.addr_array_t`, porque o tipo delas é o do pacote do mapa), `strict_periph` e um `<periférico>_index` (`clint_index`, `plic_index`, `uart_jtag_index`, `flash_ctrl_index` e assim por diante) para cada periférico que a plataforma lista, lido do `<NOME>_INDEX`, de modo que o topo não fixa número de periférico; com temporizadores (`kind: timer`), `timer_indices => TIMER_INDICES` e `timer_irq_ids => TIMER_IRQ_IDS`, uma instância no SoC por linha; sem PLIC na plataforma, os generics de PLIC e CLINT levam os valores padrão do SoC, de modo que o topo nunca lê constantes que o pacote não tem; os generics de extensão de ISA não são passados, o SoC os lê do `config_pkg` da plataforma |
| Polaridade | Generics `switches_active_low`, `keys_active_low` e `display_active_low` do SoC; chaves e botões são portas `inout` ligadas direto aos pinos do GPIO |
| Backend `emulado` da FLASH | `flash_chip` (latências de `memory.rom.latency`), `flash` de duas portas, `flash_loader` e `flash_jtag_shell`; o carregador segura o SoC em reset enquanto escreve |
| Atualização de programa | Com o periférico `FLASH_CTRL`, o SoC leva o controlador (`has_flash_ctrl`) e o backend da FLASH acrescenta o `flash_cmd_port` na porta B do armazenamento, que o carregador toma com o núcleo parado, e devolve a região regravada ao SoC para derrubar as linhas das caches |
| Cortes de caminho crítico | O topo liga `registered_irqs`, `fast_icache_select` (com o relógio de busca definido) e a página do topo da RAM fora da cache de dados (`RAM_LAST_PAGE`), os mesmos cortes do topo escrito à mão |
| Backend `emulado` da RAM | `onchip_ram_port` sobre o bloco `ram`, com a latência pedida |
| Backend `dispositivo/sdram` | Um controlador só para as duas regiões (seção 2.1): `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` e um `tristate_buffer_1bit` por bit do dado em um `generate`; a ponte de dados existe quando a RAM está na SDRAM e a ponte de instruções quando a FLASH está, ou quando a RAM tem `fetch`; a largura de 16 ou 32 bits e os bits de linha, coluna e banco vêm do chip e de `memories.sdram.chips` |
| Backend `dispositivo/nor` | `nor_flash_ctrl` de 8 bits com leitura em página e os comandos da atualização de programa, e o anel de pinos da FLASH |
| Backend `dispositivo/sram` | `sram_ctrl` na porta de dados do SoC, com os pinos `ADDR` (20 bits), `CE#`, `OE#`, `WE#`, `LB#` e `UB#` ligados direto, um `tristate_buffer_1bit` por bit do `DQ` de 16 bits, o tamanho do pacote do chip e os tempos do `chip_timing_pkg`; a porta de instruções da RAM fica sem resposta, como na RAM emulada |

### 2.1. A SDRAM compartilhada

Com a FLASH e a RAM na SDRAM a memória é um chip só, e o topo instancia um `sdram_ctrl`, um `sdram_arbiter` e um conjunto de pinos `DRAM_*`. Os pedidos chegam por três mestres do árbitro.

| Mestre | Origem | Existe quando |
| :--- | :--- | :--- |
| A | Porta de dados do SoC, pela ponte de dados | A RAM é `sdram` |
| I | Face da FLASH e, com `fetch`, a face de busca da RAM, pela ponte de instruções | A FLASH é `sdram`, ou a RAM é `sdram` com `fetch` |
| B | Depuração pela JTAG | Sempre |

Com a FLASH e o `fetch` ligados, um `flash_arbiter` junta as duas origens antes da ponte de instruções, um pedido por vez e em rodízio. Sem o mestre I o topo o deixa sem pedidos. O endereço de cada origem passa pelo `offset` da região (seção 7.4 de [memory_map](memory_map.md)) antes de entrar na ponte, por uma constante nos bits altos ou por um somador de constante, e uma região sem `offset` mantém o endereço do SoC. As asserções de elaboração conferem que a região cabe no chip.

Com a FLASH na SDRAM o topo também liga a saída `o_core_hold` do `sdram_dbg_master`, leva o nível ao relógio do núcleo por dois flip-flops e o soma ao reset do SoC, para a JTAG escrever a FLASH com o núcleo preso. O reset do controlador depende só do travamento do PLL, e o botão de reset da placa reinicia apenas o núcleo, então o conteúdo da SDRAM sobrevive a ele. Essa plataforma não tem `FLASH_CTRL` nem a linha do PLIC dele, e o topo não instancia `flash_cmd_port`, `flash_loader` nem o armazenamento da FLASH emulada.

A memória de instruções é uma escolha da plataforma entre quatro opções que coexistem com a RAM de dados em qualquer uma das combinações.

| Opção | `instructions.type` | `on_bus` | Backend |
| :--- | :--- | :--- | :--- |
| a | `onchip` | `false` | Blocos do FPGA lidos direto da porta da CPU |
| b | `emulated` | `true` | `flash_chip` e `flash` com a latência pedida |
| c | `sdram` | `true` | Janela do chip de SDRAM desta seção |
| d | `flash` | `true` | `nor_flash_ctrl`, o chip NOR da placa |

## 3. O que o topo não liga

Um backend sem entidade (`flash-interna` e `serial`) não gera instância: o topo avisa e deixa a região parada. O SoC não exporta o papel de LEDs: os pinos de LED ficam no nível apagado, menos o primeiro, que acende com a bandeira de falha que o hospedeiro grava no display (nó Virtual JTAG de índice 2). O texto de cada backend fica em `templates/`, com os nomes e as portas reais das entidades do Memory.

### 3.1. Vídeo

Quando a plataforma pede vídeo, o `TopSpec` carrega o `VideoPlan` e `video_generics` escreve os generics de temporização, de largura de canal e de framebuffer ([board_video](board_video.md)). O topo liga ao periférico `video` (seção 3.2) os generics da entidade (`fb_width`, `fb_height`, `channel_bits`, `pixel_format`, `scale` e a temporização), o plano de relógios ganha a saída `pixel` do PLL e o sinal `clk_pixel`, e o mapa de generics do SoC não recebe os generics do plano.

### 3.2. Periféricos externos

Cada entrada de `peripherals` com um `kind` externo (seção 9.6 de [memory_map](memory_map.md)) vira uma instância da entidade do `Peripherals`, com o rótulo `u_<nome>`, ligada aos pinos do papel da placa e a um barramento externo do SoC. Sem periférico externo o topo não ganha nada, e um periférico omitido pela placa (`need: optional`) fica com a leitura e a interrupção zeradas.

O contrato com o SoC é o seguinte.

| Item | Conteúdo |
| :--- | :--- |
| Generics | `ext_indices => EXT_INDICES`, `ext_irq_ids => EXT_IRQ_IDS` (as tabelas do pacote do mapa) e `ext_addr_width`, a maior largura de endereço de palavra entre as entidades |
| Portas de saída | `o_ext_addr`, `o_ext_wdata`, `o_ext_byteena`, `o_ext_we` e `o_ext_re`, esta e a anterior com um bit por periférico |
| Portas de entrada | `i_ext_rdata` (32 bits por periférico) e `i_ext_irq` (um bit por periférico) |
| Posição | `<NOME>_EXT_POS`, do pacote do mapa, escolhe a fatia de cada periférico |

A instância liga `i_clk` ao relógio do núcleo e `i_rst` ao reset do SoC, e os generics de frequência recebem o relógio do núcleo em hertz. Os campos do kind (por exemplo `phy_addr`, `cs_count`, `three_wire`, `has_flow_control`, `sample_rate`) viram generics com o mesmo nome do campo, e só os campos escritos na plataforma entram no `generic map`. Os tipos dos campos e o literal de cada um estão na seção 9.7 de [memory_map](memory_map.md).

| Entidade | Pinos |
| :--- | :--- |
| `ps2_keyboard`, `ps2_mouse_top` | `clk` e `dat` direto nas portas `inout` |
| `sd_spi` | MOSI em `cmd`, MISO em `dat(0)`, CS em `dat(3)`, e os outros bits de `dat` em `'Z'` |
| `sd_native` | `cmd` e cada bit de `dat` saem por `'Z'` com a habilitação da entidade |
| `eth_rgmii_mac` | `i_tx_clk` recebe `clk_eth_tx` e `i_tx_clk_dly` recebe `clk_eth_tx_dly` (ou `clk_eth_tx` com `shifted_txc` falso); `GTX_CLK`, `TXD` e `TX_CTL` saem direto, `RXC`, `RXD` e `RX_CTL` entram direto, e o MDIO sai com habilitação |
| `lcd`, `usb_bridge`, `eth` (MDIO), `hdmi_tx` (I2C), `adxl345` (`mosi`) | Saída com habilitação: `'Z'` quando desabilitada, e um sinal de volta com a leitura do pino |
| `i2c_master` | Open drain: `'0'` quando a entidade pede baixo, senão `'Z'` |
| `audio` | O FPGA é o mestre dos relógios do codec, e as entradas `i_bclk`, `i_adclrck` e `i_daclrck` ficam em `'0'` |
| `hdmi_audio` | Quatro linhas de saída (`o_mclk`, `o_sclk`, `o_lrclk`, `o_i2s0`), com a entidade como mestre I2S |
| `uart` | `rx` e `tx` direto; sem o pino `cts` a entrada fica em `'0'`, e sem `rts` a saída fica aberta |
| `usb_bridge` | `dreq` e `dack` opcionais: sem eles `i_otg_dreq` fica em `'0'` e `o_otg_dack` aberto |
| `adc128s022`, `ltc2308`, `ir_receiver`, `tv`, `spi` | Direto; o `cs_n` do `spi` é fatiado na largura da porta da placa |
| `wifi` | O `gpio0` sai por `'Z'` com a habilitação da entidade, sem leitura de volta. Os pinos do SPI e da UART são opcionais: sem pino, uma saída fica aberta e uma entrada fica no nível de repouso (`cipo` e `rts` em `'0'`, `tx` em `'1'`) |
| `hdmi_tmds_tx` | `tmds` vai ao `o_tmds_d` (três pares, lado positivo) e `clk` ao `o_tmds_clk`; o lado negativo vem da atribuição de pino diferencial. Sem o pino `hpd` a entrada `i_hpd` fica em `'0'`, monitor ausente. A entidade não tem DDC, e o `scl` e o `sda` do conector são ligados por um periférico `i2c` à parte, na cópia do papel `i2c` que o campo `instance` aponta |
| `mipi` | O topo instancia o registrador DDR de entrada entre os pinos LVDS e a entidade: `clk` vai ao `i_mipi_clk` e ao relógio do registrador, e `d` ao dado dele, que entrega a cada lane o bit mais antigo (`i_mipi_early`) e o mais novo (`i_mipi_late`) do par. O generic `lanes` é a largura do pino `d` |

O `video` e o `hdmi_tx` recebem o `i_pixel_clk` do sinal `clk_pixel`, declarado quando o plano de relógios tem a saída `pixel`; sem ela (nenhuma fonte dá a frequência) a instância fica fora com um aviso. O `hdmi_tmds_tx` recebe também o `i_serial_clk` do sinal `clk_pixel_x5`, o relógio de cinco vezes o de pixel que o plano produz quando um periférico o pede; sem o `pixel_x5` a instância fica fora com um aviso. O `max10_adc_shell` liga `i_adc_clk_10` ao pino `clk10` (`ADC_CLK_10`), e o IP do núcleo entra no projeto pelo [board_generate](board_generate.md). Os generics de tempo do `ps2_keyboard` e do `ps2_mouse_top` (`filter_cycles`, `inhibit_cycles`, `timeout_cycles` e, no mouse, `init_timeout_cycles` e `packet_timeout_cycles`) contam ciclos e têm o padrão de um relógio de 50 MHz, então o topo os reescreve para o relógio do núcleo, arredondando para cima.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Conteúdo do topo da DE0-CV, latências, anel de pinos, polaridade e sintaxe aceita pelo GHDL |
| `tests/test_sdram_split_top.py` | Um controlador para a FLASH e a RAM nas divisões de 32 e 32, 48 e 16, 16 e 48 MiB, o `hold`, o reset, o `fetch` e as opções a, b, c e d da memória de instruções |
| `tests/test_board_video_generate.py` | Os generics de vídeo chegam ao `TopSpec` sem alterar o topo |
| `tests/test_external_top.py` | A instância e os pinos de cada kind externo, o open drain, o `'Z'` e o que fica fora do topo, os pinos de repouso do `wifi`, o registrador DDR e o `lanes` da `mipi`, a saída `hdmi_tmds` com o `hpd`, o relógio serial e o DDC à parte, e as restrições do `.sdc` dos três |
| `tests/test_eth_rgmii.py` | A instância do MAC RGMII, os dois relógios do PLL e o `.sdc` do Ethernet |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
