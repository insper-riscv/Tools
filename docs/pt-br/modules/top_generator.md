# `top_generator`

Gera o topo fino da placa, que só liga o PLL, o SoC, um backend por região e o anel de pinos.

## 1. Função

O topo gerado não tem lógica além do reset. Ele liga, nesta ordem, as portas da placa, o PLL (módulo Verilog, instanciado por componente), a instância da entidade `soc`, a boot memory, os papéis de E/S, o console e um backend por região externa, com o anel de pinos de três estados.

## 2. Conteúdo

| Parte | Origem |
| :--- | :--- |
| Generics `HPM_COUNTERS` e `HPM_WIDTH` | Presentes quando o perfil tem Zihpm, repassados ao SoC |
| Reset | Reset do usuário normalizado para ativo em `'1'`, reset do SoC liberado dois ciclos de `core` depois do PLL travar |
| Generics do SoC | Constantes do pacote do mapa (`generate.vhdl.package`); sem PLIC na plataforma, os generics de PLIC e CLINT levam os valores padrão do SoC, de modo que o topo nunca lê constantes que o pacote não tem |
| Polaridade | Generics `switches_active_low`, `keys_active_low` e `display_active_low` do SoC; chaves e botões são portas `inout` ligadas direto aos pinos do GPIO |
| Backend `emulado` da FLASH | `flash_chip` (latências de `memory.rom.latency`), `flash` de duas portas, `flash_loader` e `flash_jtag_shell`; o carregador segura o SoC em reset enquanto escreve |
| Backend `emulado` da RAM | `onchip_ram_port` sobre o bloco `ram`, com a latência pedida |
| Backend `dispositivo/sdram` | Duas pontes (dados e instruções), `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` e um `tristate_buffer_1bit` por bit do dado em um `generate` |

## 3. O que o topo não liga

Um backend sem entidade (`nor`, `sram`, SDRAM de largura diferente de 16 bits) não gera instância: o topo avisa e deixa a região parada. O SoC não exporta o papel de LEDs, e os pinos de LED ficam no nível apagado. O texto de cada backend fica em `templates/`, com os nomes e as portas reais das entidades do Memory.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Conteúdo do topo da DE0-CV, latências, anel de pinos, polaridade e sintaxe aceita pelo GHDL |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
