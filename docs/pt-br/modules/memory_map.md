# `memory_map`

Confere que todas as cópias escritas à mão do mapa de memória de uma plataforma concordam. O mapa (bases e tamanhos das regiões, as palavras que a boot ROM reserva no topo da RAM, os pontos de entrada do boot, as janelas dos periféricos) é necessário em muitos arquivos: flags do linker, boot ROM, runtime C, VHDL, IPs do Quartus, o `config.yaml` do projeto. Cada cópia só é notada quando diverge na placa. Um arquivo YAML, a plataforma, é a fonte da verdade; este módulo lê cada cópia e reporta toda divergência.

## Configuração

Sem seção no `config.yaml`: o arquivo da plataforma se descreve sozinho e é passado com `--platform`.

```yaml
regions:                      # o mapa em si
  - {name: BOOT_ROM, base: 0x0,    size: 2K,   kind: rom, exec: true}
  - {name: FLASH,    base: 0x800,  size: 30K,  kind: rom, exec: true}
  - {name: RAM,      base: 0x8000, size: 160K, kind: ram}
reserved:                     # palavras no topo da RAM (dentro de uma região ram)
  stdout:  {base: 0x2FBE0, size: 1K+8}
  tohost:  {base: 0x2FFF0, size: 16}
boot: {entry: 0x800, wait_restart: 0x100}
peripherals:                  # base = 0x80000000 | id << 28
  - {name: GPIO, base: 0xA0000000, id: 2}
checks:                       # onde mora cada cópia
  - name: config ram base
    file: tools/riscv_build/config.yaml      # relativo a --root
    yaml: memory.ram_base                     # caminho com pontos, ou:
    expect: RAM.base
  - name: specs ram size
    file: rv32im-fpga.specs
    pattern: '--defsym=__ram_size=(\S+)'      # um grupo de captura
    expect: RAM.size - (RAM.end - stdout.base)
```

- **Símbolos** em `expect`: `<REGIÃO>.base|size|end|words`, `<reservado>.base|size|end`, `boot.entry|wait_restart`, `<PERIFÉRICO>.base|id`.
- **Números** aceitam hexadecimal, decimal, VHDL (`16#800#`), sufixos (`30K`, `0x800u`) e `+ - * /` (divisão exata), além de `log2()` (exato) e `clog2()` (arredonda para cima, para larguras de endereço).
- Um check cujo padrão não casa nada **falha** ("a cópia mudou de lugar"); `optional: true` ignora um arquivo ausente. Um padrão com vários casamentos precisa concordar em todos.
- Antes de ler as cópias, o próprio mapa é validado: regiões e palavras reservadas não se sobrepõem, as reservadas ficam dentro de uma região RAM, `boot.entry` está numa região executável, `boot.wait_restart` está na primeira região, e a base de cada periférico bate com o id, e toda região termina em `0x80000000` ou antes (os 2 GiB inferiores são da BOOT_ROM, da ROM e da RAM, e os superiores, dos periféricos).

## Gerar os arquivos do mapa

O mesmo YAML pode dizer, na seção `generate`, quais arquivos saem dele, de modo que nenhuma cópia do mapa precise ser escrita à mão.

| Chave | Arquivo gerado | Conteúdo |
| :--- | :--- | :--- |
| `specs` | Arquivo de specs do GCC | As flags do linker: `__flash`, `__flash_size`, `__ram`, `__ram_size` e `rv32_wait_restart`. A RAM do linker termina onde começa a palavra reservada `ram_limit` |
| `boot_ld` | Linker script da boot ROM | A memória `boot_rom` na primeira região e o `RESET_RESERVED` de `boot.wait_restart` |
| `runtime` | Cabeçalho do runtime (`.h`, também incluído por `.S`) | `RV32_RAM_END` (fim da RAM `ram`), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` e `RV32_STDOUT_BASE`, das faixas `reserved` que o mapa tem; o runtime em C e em assembly (`_exit.c`, `stdio.c`, `boot_rom.S`, `spike_exit.S`) usa esses nomes no lugar de endereços escritos à mão |
| `vhdl` | Pacote VHDL | As constantes `BOOT_ROM_BITS`, `BOOT_ROM_SIZE_BYTES`, `ROM_BASE_KIB`, `ROM_END_KIB`, `ROM_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES`, `RAM_LAST_PAGE`, `EXT_BASE_KIB` e `PERIPH_BASE_KIB`, as flags `ROM_EXTERNAL` e `RAM_EXTERNAL` e, de cada periférico, `<NOME>_BASE` e `<NOME>_ID` |

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout}
  boot_ld: {path: runtime/boot_rom.ld}
  runtime: {path: runtime/memory_map.h, ram: RAM}
  vhdl:
    path: rtl/map_pkg.vhd
    package: map_pkg
    rom: FLASH
    ram: RAM
```

`ext_base` e `periph_base` são opcionais e valem `0x80000000`, a janela dos periféricos. `ROM_STORAGE_BYTES` e `RAM_STORAGE_BYTES` são a menor potência de dois que cobre o fim da ROM e o tamanho da RAM, e `RAM_LAST_PAGE` são os bits 31:12 da última página de 4 KiB da RAM.

Os limites do pacote VHDL são os genéricos do `core`, em KiB, então um endereço que não é múltiplo de 1 KiB é um erro. O mapa é validado antes de gerar, e um mapa inconsistente não gera nada.

```bash
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml --check
```

Com `--check` nada é escrito, e o comando sai com status 1 se um arquivo faltar ou estiver diferente do que o mapa geraria. Não precisa de `--config`.

## Ler a configuração do mapa

Um `config.yaml` do projeto declara `memory_map: <caminho do platform.yaml>`, e o carregador de configuração troca as chaves que o mapa fixa pelas dele: `memory.boot_rom_base`, `boot_rom_words`, `rom_base`, `rom_words`, `ram_base`, `ram_words`, `tohost_addr`, `fromhost_addr` `sim.env.TOHOST_ADDR` e `sim.env.STDOUT_ADDR` (o testbench lê o endereço do ambiente) e, para as memórias que a seção `config.addr_widths` do mapa lista, `sim.parameters.<memória>_addr_width`. O que o mapa fixa vale mais que o que o arquivo ou os seus `extends` dizem, então nenhum endereço nem tamanho é escrito duas vezes.

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_rom, rom, ram]
```

O `platform sync` grava os valores já trocados, de modo que Tests e Certification não precisam do `platform.yaml`.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_memory_map.py::test_evaluate_number_notations` | Hex, VHDL, `K`, sufixo `u` e aritmética. |
| `tests/test_memory_map.py::test_evaluate_symbols_and_log2` | Símbolos em expressões, `log2`/`clog2`, e `log2` rejeitando não potências de dois. |
| `tests/test_memory_map.py::test_evaluate_rejects_unknown_symbol_inexact_division_and_code` | Símbolo desconhecido, divisão inexata e código arbitrário são rejeitados. |
| `tests/test_memory_map.py::test_symbols_flattens_regions_reserved_boot_and_peripherals` | A tabela de símbolos. |
| `tests/test_memory_map.py::test_the_reference_platform_is_consistent` | Um mapa consistente não tem problemas. |
| `tests/test_memory_map.py::test_validate_platform_reports_an_inconsistent_map` | Sobreposições, reservado fora da RAM, entradas de boot e ids de periférico errados. |
| `tests/test_memory_map.py::test_check_passes_when_every_copy_agrees` | Cinco cópias em cinco formatos concordam. |
| `tests/test_memory_map.py::test_check_fails_when_one_copy_diverges` | Alterar qualquer cópia faz falhar exatamente o seu check. |
| `tests/test_memory_map.py::test_check_reports_every_divergent_match_of_one_pattern` | Cada casamento divergente é reportado. |
| `tests/test_memory_map.py::test_check_fails_when_a_copy_no_longer_matches_the_pattern` | Uma cópia reformatada é notada. |
| `tests/test_memory_map.py::test_check_fails_on_a_missing_file_unless_optional` | Arquivo ausente falha, salvo `optional`. |
| `tests/test_memory_map.py::test_check_stops_at_an_inconsistent_map` | Nenhuma cópia é lida se o próprio mapa é inconsistente. |
| `tests/test_memory_map.py::test_load_platform_rejects_a_non_mapping` | Um arquivo que não é mapeamento é rejeitado. |
| `tests/test_memory_map.py::test_cmd_check_memory_map_exit_status` | O comando imprime OK, ou sai com 1 listando as divergências. |
| `tests/test_generate_memory_map.py` | Specs, linker script e pacote VHDL saem do mapa; `--check` pega arquivo ausente ou editado; endereço fora de KiB, região acima da janela dos periféricos e mapa inconsistente são rejeitados; o comando escreve e confere. |
| `tests/test_config_from_platform.py` | As chaves de `memory`, o ambiente do `tohost` e do `stdout` e as larguras de endereço saem do mapa, e o mapa vale mais que o arquivo e os seus `extends`. |

## Uso

```bash
uv run riscv-tools --root <projeto> check-memory-map --platform platforms/internal-mem.yaml
```

Não precisa de `--config`. Status 1 e uma linha `MISMATCH` por divergência quando uma cópia diverge; feito para o CI.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
