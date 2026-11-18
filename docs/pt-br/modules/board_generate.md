# `board_generate`

Compõe os geradores no projeto Quartus de uma plataforma numa placa (`riscv-tools board generate`).

## 1. Função

Chama cada gerador e junta o texto, sem escrever conteúdo próprio. A pasta de saída é de construção e não é versionada.

## 2. Arquivos gerados

| Arquivo | Gerador |
| :--- | :--- |
| `<plataforma>_<placa>_top.vhd` | `top_generator` |
| `<plataforma>_<placa>_pll.v` | `pll_generator` |
| `<plataforma>_<placa>.sdc` | `sdc_generator` |
| `<plataforma>_<placa>.qpf` e `.qsf` | `quartus_project`, com os pinos de `pin_assignments` |
| `chip_<chip>_pkg.vhd` | `chip_package`, um por chip da placa |
| `generate_ip.sh` | `vendor_ip`, só com o ADC do MAX 10; o `.qsf` ganha a linha `QIP_FILE` do núcleo que ele gera |
| `init.mif` e `boot_memory_init.mif` | Cópia do arquivo de mesmo nome ao lado do `platform.yaml`, quando existe; as IPs da FLASH e da BOOT_MEMORY os leem da pasta do projeto, e sem a cópia o Quartus avisa (127003) e a memória entra zerada no bitstream |

O mapa de memória (pacote VHDL, linker, `.specs` e cabeçalhos) não é gerado aqui: o comando chama o mesmo código do `generate-memory-map` para a plataforma e escreve os arquivos nos caminhos de `generate`. O projeto fica em `<saída>/<plataforma>-<placa>/`. O comando de compilação é o `program` (ver [quartus_program](quartus_program.md)).

O `generate_ip.sh` chama o `ip/generate.sh` do `Peripherals` (Platform Designer do Quartus Prime Lite) e escreve `max10_adc_core/synthesis/max10_adc_core.qip` na pasta do projeto; ele roda antes da compilação. O arquivo só existe quando a plataforma tem um `adc` com `chip: max10` e as fontes trazem o `max10_adc_ip.vhd`.

Quando a plataforma pede vídeo (`io.video`), a geração resolve o modo pelo [board_video](board_video.md) e recusa um pedido impossível com a mensagem da regra V20. O plano resolvido fica em `Generated.video`, e a conferência de V21 e V22 roda junto com a do cabimento.

O módulo `project` (`build`) é o único caminho da geração: o `board generate`, o `program` (com a chave `quartus.generate` da configuração) e o orquestrador de testes na placa, antes de reconfigurá-la, escrevem o projeto e o mapa de memória por ele, e nunca por um segundo código.

## 3. Uso

```bash
uv run riscv-tools --root <espaço de trabalho> board generate \
    --platform <plataforma>.yaml --board de0-cv --out build \
    --target de0_cv_map --target soc --target Memory/flash_chip
```

| Opção | Efeito |
| :--- | :--- |
| `--board` (global) | Placa; sem ela vale o campo `board` ou a única entrada de `boards` |
| `--boards-dir`, `--chips-dir` | Padrões `<raiz>/boards` e `<raiz>/Memory/chips` |
| `--target` | Componente cujo fecho de fontes entra no `.qsf`; repetível; sem ele vale o campo `top` do `platform.yaml` |
| `--seed` | Semente do `.qsf`, padrão 5 |
| `--accept-inferred-pins` | Aceita construir com pino `inferred` |
| `--check` | Não escreve nada; sai com status 1 quando o projeto ou um arquivo do mapa de memória no disco difere do que seria gerado |
| `--hand-qsf`, `--hand-sdc`, `--hand-pll`, `--ignore-source` | Imprimem o relatório de [board_equivalence](board_equivalence.md) contra os arquivos escritos à mão |

A lista de fontes parte do clone do repositório que contém a plataforma, a pasta mais próxima acima do `platform.yaml` que tem um `paths.yaml`. Num projeto consumidor, como o Tests, a plataforma está num submódulo, e os repositórios que os componentes pedem são submódulos dele, e não da raiz do consumidor. Os arquivos do mapa de memória também são escritos nesse clone.

Os avisos (fase do `DRAM_CLK` não medida, papel opcional ausente, backend sem entidade) saem em `stderr`. Sai com status 2 quando uma entrada é inválida, e com status 1 quando o relatório de equivalência acha uma perda.

O projeto ganha o `capacity.json` (estimativa de lógica e de blocos de RAM, com os avisos) quando a família tem tabela de calibração; o perfil que passa de 100 % de um recurso recusa a geração com status 2 (regras V11 e V12 de [board_check](board_check.md)).

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Arquivos das seis placas (as de `altpll` com um escritor de teste), `.qsf`, determinismo e escrita |
| `tests/test_board_generate_cli.py` | O comando escreve a pasta, imprime o relatório e sai com 2 numa entrada inválida |
| `tests/test_generator_uniqueness.py` | Cada tipo de texto gerado tem um só módulo escritor |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
