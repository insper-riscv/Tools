# `mem_edit`

Primitivas genéricas do In-System Memory Content Editor, compartilhadas por [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md) e [`htif`](htif.md). Só mecanismo, sem política: cada um desses módulos decide qual instância, endereço ou conteúdo usar; este módulo só sabe ler e escrever uma instância de memória por JTAG.

## Funções

| Função | O que faz |
| :--- | :--- |
| `write_full` | Sobrescreve a profundidade inteira de uma instância de memória a partir de um `.mif`. |
| `write_full_multi` | O mesmo, mas escreve o mesmo `.mif` em várias instâncias numa só chamada (um design com mais de uma cópia física do mesmo conteúdo, mantidas em sincronia). |
| `write_word` | Sobrescreve uma única palavra num dado offset. |
| `read_words` | Lê de volta um intervalo de palavras. |
| `dump` | Salva o conteúdo inteiro de uma instância num `.mif`. |
| `instances` | Lista as instâncias da placa programada (índice, profundidade, largura e nome), consultando a placa uma vez por cabo e guardando a lista. |
| `invalidate` | Esquece as listas guardadas; roda sempre que a placa é programada de novo, porque os índices podem mudar. |
| `rom_instances` | Devolve os índices da ROM: converte `quartus.rom_mem_names` ou, sem nomes, usa `quartus.rom_mem_instances`. |
| `ram_instance` | Devolve o índice da RAM: converte `quartus.ram_mem_name` ou, sem nome, usa `quartus.ram_mem_instance`. |

## Resolução por nome

O índice de uma instância muda quando o design ganha ou perde uma memória com `ENABLE_RUNTIME_MOD`, e o `INSTANCE_NAME` do IP continua o mesmo; por isso o `config.yaml` nomeia as memórias e o host acha os índices na placa.

| Situação | Resultado |
| :--- | :--- |
| Nome e índice no mesmo `config.yaml` | O nome vale mais. |
| Só índices | Valem como antes, sem consultar a placa. |
| Nome ausente na placa | Erro que lista os nomes e os índices encontrados. |
| Nome da RAM que serve a mais de uma instância | Erro, porque a RAM não se distingue. |

O editor guarda só os quatro primeiros caracteres de um `INSTANCE_NAME`: `FLASH` aparece como `FLAS`. Um nome listado com quatro caracteres vale para todo nome pedido que começa por ele, então `FLASH` e `FLASH_MEM` apontam para as instâncias listadas como `FLAS`, e a ROM escreve a mesma imagem em todas. Para a RAM, o nome precisa diferir dos outros já nos quatro primeiros caracteres.

## Configuração

Recebe um `JtagLink` (veja [`jtag`](jtag.md)), um índice de instância e caminhos/endereços como argumentos diretos; as chaves `quartus.rom_mem_names`, `quartus.ram_mem_name`, `quartus.rom_mem_instances` e `quartus.ram_mem_instance` são lidas por `rom_instances` e `ram_instance`. Quem o chama decide qual índice de instância e profundidade se aplicam ao próprio caso de uso.

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com as instâncias do In-System Memory Content Editor que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

Não é um subcomando próprio da CLI: é o mecanismo que [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md) e [`htif`](htif.md) chamam para de fato conversar com uma instância de memória por JTAG.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
