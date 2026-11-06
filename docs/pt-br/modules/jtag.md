# `jtag`

Identifica a conexão JTAG ativa e roda contra ela os scripts `.tcl` que acompanham este pacote. É a base compartilhada em que todo outro módulo que toca JTAG se apoia ([`mem_edit`](mem_edit.md), [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), [`htif`](htif.md), [`quartus_program`](quartus_program.md)).

## Identificando uma conexão: `JtagLink`

Uma conexão JTAG precisa de dois identificadores, e eles se comportam de forma diferente ao longo do tempo:

| Campo | O que é | Estabilidade |
| :--- | :--- | :--- |
| `hardware_name` | O nome do cabo `"USB-Blaster [<bus>-<port>]"` | Muda entre reboots e renumeração do hub, então é sempre detectado em tempo real por `detect_jtag_hardware()`, que escolhe o cabo cuja cadeia lista o IDCODE de `jtag_device` (a PC1 tem quatro cabos), nunca lido da configuração. A identificação da placa, com a porta USB como desempate, está em [`board`](board.md). |
| `device_name` | A string de identidade JTAG do chip alvo | Estável entre reboots; vem da configuração do próprio projeto (`quartus.jtag_device`). |
| `sdram_instance` | O índice da instância do Virtual JTAG da porta de depuração da SDRAM | Fixado no topo da plataforma (`sld_instance_index`); vem da configuração (`quartus.sdram_debug_instance`) e chega ao script `sdram_dbg.tcl` pela variável de ambiente `RV32_SDRAM_DEBUG_INSTANCE`. |

## Leitura do `jtagconfig`

`read_cables()` roda o `jtagconfig` uma só vez e devolve todos os cabos, cada um com o nome, os dispositivos da cadeia (posição, IDCODE e nome) e o erro que o `jtagconfig` imprimiu no lugar da cadeia. `parse_jtagconfig()` faz a mesma leitura sobre um texto, e é o que os testes usam com fixtures. `same_idcode()` compara dois IDCODEs sem os 4 bits de versão. Nenhum outro módulo nem repositório lê o `jtagconfig`; o módulo [`board`](board.md) e o runner do Tests partem desta leitura.

## Saúde da chain

O `jtag_chain_healthy()` roda o `jtagconfig` e devolve `False` se a saída contém "chain broken" (sem diferenciar maiúsculas) ou se o próprio `jtagconfig` nem consegue rodar (cabo desconectado, problema de driver); `True` caso contrário. Feito para ser consultado num laço, por exemplo enquanto se espera alguém desligar e ligar fisicamente uma placa travada (veja o [`orchestrator`](orchestrator.md)).

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.jtag_device` | A string de IDCODE JTAG da própria FPGA. Um projeto sem ela seleciona a placa pelo módulo [`board`](board.md). |
| `quartus.board` | Identificador da placa ou `auto`, o `board:` da plataforma. |
| `quartus.boards` | Lista de placas que o `auto` pode tomar. |
| `quartus.sdram_debug_instance` | O índice da instância do Virtual JTAG da porta de depuração da SDRAM. O padrão é 0; uma plataforma que também tem o carregador da FLASH dá outro índice à porta de depuração. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG.

## Testes

A leitura do `jtagconfig` e a escolha do cabo têm testes com fixtures em `tests/test_jtag_link.py` e `tests/test_board_*.py`. O acesso ao cabo em si não tem teste automatizado aqui; um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

Não é um subcomando próprio da CLI: todo outro módulo que toca JTAG recebe um `JtagLink` como argumento em vez de construir um, e chama `jtag.run`/`jtag.run_tcl` para de fato invocar um script `.tcl` contra ele.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
