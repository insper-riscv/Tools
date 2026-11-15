# `ram_dump`

Salva o conteúdo inteiro de uma instância de RAM num `.mif` por JTAG. Usado nos testes `RV32_TEST_KIND: memory`, em que só o resultado PASS/FAIL não basta para provar que um teste fez a coisa certa (que ele escreveu os valores certos na memória, e não apenas chegou ao próprio sinal de sucesso): veja o [`mem_validator`](mem_validator.md), que compara o dump resultante com um golden JSON.

## 1. Região na SDRAM

Com `--region FLASH` ou `--region RAM` o comando lê um trecho de uma região que fica na SDRAM, na janela do chip dela ([`sdram_windows`](sdram_windows.md)), em vez da instância de RAM do FPGA.

| Opção | Efeito |
| :--- | :--- |
| `--range ENDEREÇO:TAMANHO` | Endereço de byte do SoC e tamanho em bytes do trecho, por exemplo `0x41FFF000:0x1000` |
| `--full` | Lê a região inteira, em rajada quando o bitstream tem uma ([`sdram_debug`](sdram_debug.md), seção 3) |
| `--platform` | `platform.yaml` (relativo a `--root`) que dá as janelas, no lugar de `memory.sdram_windows` |

O arquivo de saída com a extensão `.bin` recebe os bytes, e qualquer outra extensão recebe um `.mif` com uma linha por palavra, numerada a partir do início da região. A leitura vale com o núcleo rodando, porque a cache de dados é write-through e a SDRAM guarda o valor mais recente.

## 2. Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_mem_name` | Nome (`INSTANCE_NAME` do IP, por exemplo `RAM`) da instância da RAM; vale mais que `quartus.ram_mem_instance`. |
| `quartus.ram_mem_instance` | Índice de instância que o In-System Memory Content Editor do Quartus atribui ao tap de debug da RAM. `1` é o caso comum. |

## 3. Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com a instância de RAM que o design do projeto expõe.

## 4. Testes

`tests/test_flash_load.py` cobre a leitura de uma região e a saída em `.bin` e `.mif` contra um modelo da placa. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## 5. Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml dump-ram <output.mif>
```

Também é chamado internamente pelo [`orchestrator`](orchestrator.md) depois de cada teste do tipo `memory`, antes de passar o dump ao [`mem_validator`](mem_validator.md).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
