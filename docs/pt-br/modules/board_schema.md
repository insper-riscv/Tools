# `board_schema`

Lê e confere os arquivos do catálogo de placas: o `board.yaml` e o `pins.yaml` de cada placa, a família do dispositivo e o chip de memória. Os campos novos do `platform.yaml` (a placa, o backend das memórias externas, os relógios, o console e os papéis de entrada e saída) passam pelo mesmo leitor. Cada dado mora num arquivo só, e este módulo é o único que sabe o esquema de cada um.

## 1. Onde ficam os arquivos

O catálogo é achado a partir da raiz do projeto.

| Arquivo | Caminho | Esquema |
| :--- | :--- | :--- |
| Placa | `boards/<placa>/board.yaml` | Dispositivo, cadeia JTAG, capacidades, relógios, papéis de E/S, memórias e console |
| Pinos | `boards/<placa>/pins.yaml` | Pino, padrão de E/S, direção e selo de certeza de cada sinal |
| Família | `boards/families/<família>.yaml` | Unidade de lógica, PLL, bloco de RAM, Fmax medido por grau e calibração |
| Chip | `Memory/chips/<chip>.yaml`, ou `chips/<chip>.yaml` quando a raiz é o próprio Memory | Organização, tempos e teto de relógio |

O nome dentro do arquivo é o nome do arquivo (ou da pasta, na placa), e um arquivo que diz outro nome é recusado.

## 2. Leitura e tipos

Cada campo é lido com o tipo esperado (texto, inteiro, número, booleano, mapa ou lista), e toda chave que o esquema não define é um erro, de modo que um nome errado de campo não passa em silêncio. O leitor junta todos os problemas de um arquivo antes de falhar, cada um com o caminho pontilhado do campo (`board de0-cv.jtag.chain[0].idcode must be 8 hexadecimal digits`).

O catálogo reaproveita o mecanismo `extends` dos arquivos de configuração. Um chip diz `extends: <chip>` e herda o chip nomeado, que o leitor procura na mesma pasta; os campos do chip que estende vencem os do herdado, com a mesma regra de mistura recursiva que os `config.yaml` usam. Um ciclo de `extends` é recusado. A plataforma também lê o `extends` pelo mesmo leitor de configuração.

## 3. Campos aceitos pela placa

Além dos campos do esquema do documento de arquitetura, o `board.yaml` aceita os campos que o pacote de placas usa.

| Campo | Significado |
| :--- | :--- |
| `target_level` | Nível de suporte alvo, de `N0` a `N4` |
| `console.default` | Console padrão, `jtag` |
| `jtag.cable_name` | Nome que o `jtagconfig` dá ao cabo |
| `jtag.usb[]` | IDs USB `vid:pid` do cabo, com `state` e o selo `confirmed` |
| `jtag.samd21`, `jtag.external_pads` | Descrições livres do cabo emulado e dos pads externos |
| `jtag.chain[].hps` | Dispositivo da cadeia que é o HPS; exatamente um item da cadeia é o FPGA |
| `jtag.chain[].confirmed` | `manual`, `repo`, `inferred` ou `measured` |
| `memories.<tipo>.signals` | Prefixo dos sinais no `pins.yaml`, ou lista de prefixos |

Os sinais de `io.<papel>` seguem a gramática do `pins.yaml`: `LEDR[9:0]` são os bits 0 a 9, e `HEX[5:0][6:0]` são os dígitos 0 a 5 (primeiro intervalo, índice no nome) com os segmentos 0 a 6 (segundo intervalo).

## 4. Campos novos do `platform.yaml`

| Campo | Regra |
| :--- | :--- |
| `board`, `boards` | `auto` ou um nome de placa, e a lista de placas em que a plataforma é construída |
| `memory.<rom ou ram>.backend` | `emulado` ou `dispositivo`, obrigatório com `external: true` |
| `memory.<rom ou ram>.device` | Só com `dispositivo`, e do tipo da região (`nor`, `flash-interna`, `serial` para a ROM; `sdram`, `sram` para a RAM) |
| `memory.<rom ou ram>.latency` | `{first, next}`, só com `emulado` |
| `memory.rom.sector_bytes` | Potência de 2, só na FLASH `emulado` |
| `clocks.core`, `clocks.fetch`, `clocks.mem` | `{mhz, phase_ps}`; o `core` é obrigatório e o `mem` é obrigatório com um backend `dispositivo` |
| `console` | `jtag` (padrão) ou `pinos` |
| `io.<papel>` | `{count, need}` com `need` igual a `required` ou `optional` |
| `top` | Componente, ou lista de componentes, cujo fecho de `requires` reúne os `needs` do validador |

Os campos do mapa (regiões, periféricos, perfil) continuam sendo lidos e conferidos pelo módulo `memory_map`.

## 5. Conferência do catálogo

O comando `check-boards` lê todo o catálogo e confere cada arquivo contra o esquema e contra os outros. A placa nomeia uma família e chips que existem, e todo sinal que ela cita (relógio, reset, grupos de E/S, UART e prefixos das memórias) existe no `pins.yaml`. Um pino usado por dois sinais precisa estar em `conflicts`.

## 6. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_schema.py::test_a_chip_extends_another_by_name` | O chip que estende mantém o que não diz e sobrescreve o resto |
| `tests/test_board_schema.py::test_a_chip_extends_loop_is_refused` | Um ciclo de `extends` falha |
| `tests/test_board_schema.py::test_a_chip_file_must_carry_its_own_name` | O nome do arquivo e o do chip coincidem |
| `tests/test_board_schema.py::test_unknown_names_list_what_exists` | Placa, família e chip ausentes dizem o que existe |
| `tests/test_board_schema.py::test_the_catalog_reads_a_board_with_its_pins` | Placa, família e pinos carregam juntos |
| `tests/test_board_schema.py::test_chip_problems_are_all_reported` | Todos os campos errados do chip aparecem de uma vez |
| `tests/test_board_schema.py::test_an_sdram_chip_needs_its_organization` | Bancos e bits de endereço são obrigatórios na SDRAM |
| `tests/test_board_schema.py::test_family_types_are_checked` | Tipo errado e faixa de VCO invertida são recusados |
| `tests/test_board_schema.py::test_a_board_must_name_exactly_one_fpga` | A cadeia tem exatamente um FPGA |
| `tests/test_board_schema.py::test_a_board_accepts_the_fields_of_the_boards_package` | Os campos do pacote de placas são aceitos |
| `tests/test_board_schema.py::test_a_board_rejects_a_wrong_idcode_and_unknown_key` | IDCODE malformado e chave desconhecida |
| `tests/test_board_schema.py::test_pins_signals_and_conflicts` | O selo de certeza do pino é conferido e `conflicts` é aceito |
| `tests/test_board_schema.py::test_signal_groups_expand_as_the_format_says` | Expansão de barramentos e de barramentos de barramentos |
| `tests/test_board_schema.py::test_platform_fields_are_read_and_typed` | Os campos novos da plataforma carregam |
| `tests/test_board_schema.py::test_platform_field_problems` | Cada uso inválido dos campos novos é um problema tipado |
| `tests/test_board_schema.py::test_platform_extends_is_resolved_by_the_config_reader` | Uma variante de plataforma só diz o que muda |

## 7. Uso

```bash
uv run riscv-tools --root <Insper-RISC-V> check-boards
```

Não precisa de `--config`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
