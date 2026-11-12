# `board_check`

Confere o que uma plataforma exige contra o que as placas dela oferecem. A plataforma declara o que precisa (regiões, backends, relógios, console, papéis de E/S) e a placa declara o que tem. O módulo deriva os dois lados, compara, e cada diferença é uma mensagem de erro (`E`) ou de aviso (`W`) com um código de regra. Os arquivos que ele lê são os de [board_schema](board_schema.md).

## 1. Onde roda

A conferência roda dentro do `check-memory-map`, junto com a conferência do mapa, e não no `platform sync`. Uma plataforma que não escreve `board` nem `boards` não é conferida, de modo que as plataformas anteriores ao catálogo continuam passando. Com `board: auto` e sem `boards`, a placa só se conhece em tempo de execução e nada é conferido aqui.

Um erro faz o comando sair com status 1, e um aviso é só impresso. A opção `--accept-inferred-pins` libera o uso de um pino que o `pins.yaml` marca como `inferred`.

## 2. De onde vêm `requires` e `provides`

Os dois lados são calculados e nunca escritos. O `requires` reúne o que o `platform.yaml` pede e a união das chaves `needs` dos componentes do fecho do topo. O `provides` vem do `board.yaml`, do chip do catálogo e do `pins.yaml`.

A chave `needs` mora ao lado de `sources` e `requires` no `paths.yaml` do repositório dono do componente, com os tipos `block_ram`, `sdram`, `sram`, `nor`, `onchip_flash`, `serial_flash` e `vjtag`. O `sources` e este módulo percorrem o fecho com o mesmo código, então não existe segundo formato nem segundo grafo; o campo `top` da plataforma escolhe o ponto de partida.

## 3. Regras

| Regra | Nível | O que confere |
| :--- | :--- | :--- |
| V1 | E | A placa, a família e os chips existem e os arquivos seguem o esquema |
| V2 | E | Todo tipo de `needs` está na placa, e a soma das regiões de um dispositivo cabe nele |
| V3 | E | O dispositivo de um backend `dispositivo` existe na placa |
| V4 | E | O console `pinos` exige `console.uart` |
| V5 | E | Papel `required` ausente ou com menos unidades |
| V6 | W | Papel `optional` ausente ou com menos unidades; o periférico é omitido |
| V7 | E | Relógio acima da faixa do PLL da família ou do teto do chip |
| V8 | W | Relógio do núcleo acima do Fmax medido da família e do grau |
| V9 | E | Banca da FLASH fora do múltiplo do setor, contado a partir do início da região |
| V10 | E | Região maior que a capacidade do dispositivo |
| V15 | E | Mais saídas de PLL (relógios distintos mais o relógio da SDRAM) que a placa oferece |
| V16 | E | Pino `inferred` em uso sem `--accept-inferred-pins` |
| V17 | E | A cadeia JTAG lida do cabo não é a da placa |
| V11 | E ou W | Blocos de RAM que as memórias emuladas e as caches pedem, acima da capacidade (E) ou acima de 85 % dela (W) |
| V12 | E | Lógica estimada acima da capacidade, só em família com erro máximo de validação até 10 % |
| V13 | W | Lógica estimada entre 85 % e 100 % da capacidade |
| V18 | W | Família sem arquivo de calibração, ou capacidade `null` na placa, ou coeficiente `null` de um termo do perfil |
| V19 | E | Largura do barramento que o backend não sabe fatiar |
| V20 | E ou W | Pedido de vídeo que a placa não atende (modo ausente do catálogo, proporção que não bate com o tamanho, modo fora de `modes` sem `outside_manual`, mais bits por canal que a placa, framebuffer maior que a área visível, placa sem `io.video`), ou aviso de um modo fora do manual marcado com `outside_manual` |
| V21 | E | Relógio de pixel do modo que o PLL da placa não gera junto com os relógios da plataforma |
| V22 | E | Framebuffer que não cabe nos blocos de memória livres |

As regras V11 a V13 rodam o estimador de [fit_estimate](fit_estimate.md) sobre o perfil, as caches, os periféricos e as memórias da plataforma, com a tabela de calibração da família da placa. A região emulada conta uma potência de dois de bytes, porque a largura do endereço decide os blocos. Sem o campo `profile` na plataforma, ou sem a tabela, nada é estimado. A V14 (pinos e PLLs) fica com o relatório do Quartus. As regras V20 a V22, do vídeo, estão em [board_video](board_video.md).

### 3.1. Detalhes

- Na V9 o setor vem do chip de uma FLASH NOR `dispositivo`, ou do `sector_bytes` de uma FLASH `emulado`.
- Na V15 uma saída de PLL é um par de frequência e fase, e o número de PLLs necessário é o teto da divisão pelas saídas de um PLL da família.
- Na V16 os pinos em uso são o do relógio de referência, o do reset, os dos papéis pedidos, os da UART quando o console é `pinos` e os que começam pelos prefixos das memórias em uso.
- Na V17 a verificação é a função `check_chain`, que recebe os IDCODEs lidos do cabo; quem os lê é o comando de identificação pela JTAG.
- Na V19 as larguras aceitas são 8 e 16 para a NOR, 16 e 32 para a SRAM e 16 e 32 para a SDRAM (a largura do chip vezes o número de chips).

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_check.py::test_the_base_platform_passes_without_a_message` | A plataforma de base não gera mensagem |
| `tests/test_board_check.py::test_a_platform_without_a_board_is_not_checked` | Sem `board` nada é conferido |
| `tests/test_board_check.py::test_v1_unknown_board` | V1, placa desconhecida |
| `tests/test_board_check.py::test_v1_unknown_family` | V1, família desconhecida |
| `tests/test_board_check.py::test_v1_unknown_chip` | V1, chip desconhecido |
| `tests/test_board_check.py::test_v1_a_malformed_board_is_reported` | V1, placa fora do esquema |
| `tests/test_board_check.py::test_v2_size_across_regions` | V2, soma das regiões acima do dispositivo |
| `tests/test_board_check.py::test_v2_needs_of_the_closure` | V2, `needs` do fecho que a placa não oferece |
| `tests/test_board_check.py::test_v2_top_that_cannot_be_resolved` | V2, topo que nenhum manifesto declara |
| `tests/test_board_check.py::test_v3_device_the_board_lacks` | V3 |
| `tests/test_board_check.py::test_v4_console_on_pins_without_a_uart` | V4 |
| `tests/test_board_check.py::test_v5_required_role_missing_or_short` | V5 |
| `tests/test_board_check.py::test_v6_optional_role_missing_or_short` | V6 |
| `tests/test_board_check.py::test_v7_clock_over_the_chip_limit` | V7, teto do chip |
| `tests/test_board_check.py::test_v7_clock_over_the_pll_range` | V7, faixa do PLL |
| `tests/test_board_check.py::test_v8_core_above_the_measured_fmax` | V8 |
| `tests/test_board_check.py::test_v9_flash_bank_not_aligned_to_the_sector` | V9, setor da NOR |
| `tests/test_board_check.py::test_v9_emulated_sector` | V9, setor emulado |
| `tests/test_board_check.py::test_v10_region_above_the_device` | V10 |
| `tests/test_board_check.py::test_v15_more_clocks_than_pll_outputs` | V15 |
| `tests/test_board_check.py::test_v16_inferred_pin_in_use` | V16, com e sem a opção |
| `tests/test_board_check.py::test_v17_chain_that_is_not_the_boards` | V17 |
| `tests/test_board_check.py::test_v18_family_without_calibration` | V18, família |
| `tests/test_board_check.py::test_v18_capacity_that_is_not_known` | V18, capacidade `null` |
| `tests/test_board_check.py::test_v19_bus_width_the_backend_cannot_slice` | V19, três larguras |
| `tests/test_board_video.py` | V20 a V22 e a conferência do catálogo de modos |
| `tests/test_board_fit.py` | V11 a V13 com tabela fictícia, V18 de coeficiente `null`, tabela inválida (V1) e o relatório do `capacity.json` |
| `tests/test_board_check.py::test_the_catalog_check_finds_what_a_board_cites_wrongly` | Sinal citado que não existe e pino repetido |
| `tests/test_board_check.py::test_the_catalog_check_passes_a_consistent_catalog` | Catálogo consistente passa |
| `tests/test_board_check.py::test_the_subcommands_exit_with_the_findings` | `check-memory-map` e `check-boards` saem com status 1 |
| `tests/test_manifest_needs.py::test_needs_of_the_closure_are_the_union` | Só os componentes do fecho contribuem |
| `tests/test_manifest_needs.py::test_an_unknown_need_is_a_manifest_problem` | Um tipo de `needs` desconhecido é recusado |

## 5. Uso

```bash
uv run riscv-tools --root <Insper-RISC-V> check-memory-map --platform src/cyclone-v/de0-cv/platform.yaml
uv run riscv-tools --root <Insper-RISC-V> check-memory-map --platform <plataforma> --accept-inferred-pins
```

Não precisa de `--config`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
