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
  mailbox: {base: 0x2FFFC, size: 4}
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
- Antes de ler as cópias, o próprio mapa é validado: regiões e palavras reservadas não se sobrepõem, as reservadas ficam dentro de uma região RAM, `boot.entry` está numa região executável, `boot.wait_restart` está na primeira região, e a base de cada periférico bate com o id.

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

## Uso

```bash
uv run riscv-tools --root <projeto> check-memory-map --platform platforms/internal-mem.yaml
```

Não precisa de `--config`. Status 1 e uma linha `MISMATCH` por divergência quando uma cópia diverge; feito para o CI.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
