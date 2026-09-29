# `jtag`

Identifica a conexão JTAG ativa e roda contra ela os scripts `.tcl` que acompanham este pacote. É a base compartilhada em que todo outro módulo que toca JTAG se apoia ([`mem_edit`](mem_edit.md), [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), [`mailbox`](mailbox.md), [`quartus_program`](quartus_program.md)).

## Identificando uma conexão: `JtagLink`

Uma conexão JTAG precisa de dois identificadores, e eles se comportam de forma diferente ao longo do tempo:

| Campo | O que é | Estabilidade |
| :--- | :--- | :--- |
| `hardware_name` | O nome do cabo `"USB-Blaster [<bus>-<port>]"` | Muda entre reboots e renumeração do hub, então é sempre detectado em tempo real por `detect_jtag_hardware()`, nunca lido da configuração. |
| `device_name` | A string de identidade JTAG do chip alvo | Estável entre reboots; vem da configuração do próprio projeto (`quartus.jtag_device`). |

## Saúde da chain

O `jtag_chain_healthy()` roda o `jtagconfig` e devolve `False` se a saída contém "chain broken" (sem diferenciar maiúsculas) ou se o próprio `jtagconfig` nem consegue rodar (cabo desconectado, problema de driver); `True` caso contrário. Feito para ser consultado num laço, por exemplo enquanto se espera alguém desligar e ligar fisicamente uma placa travada (veja o [`orchestrator`](orchestrator.md)).

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.jtag_device` | A string de IDCODE JTAG da própria FPGA. Sem padrão; todo projeto precisa defini-la explicitamente. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

Não é um subcomando próprio da CLI: todo outro módulo que toca JTAG recebe um `JtagLink` como argumento em vez de construir um, e chama `jtag.run`/`jtag.run_tcl` para de fato invocar um script `.tcl` contra ele.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
