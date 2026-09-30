# `path_check`

Confere que todo caminho de arquivo que a configuração de um projeto referencia existe. Mover um arquivo VHDL entre repositórios quebra toda lista que o cita: a lista de fontes da simulação, o `tests.json` dos testes, as linhas `VHDL_FILE` do projeto Quartus. Cada uma só quebra quando algo a executa. Este módulo lê essas listas e falha quando um caminho listado não existe, então uma mudança é conferida antes de qualquer build.

## Configuração

Sem seção no `config.yaml`: um manifesto lista as referências, passado com `--manifest`.

```yaml
references:
  - name: sim sources
    file: Tests/tools/riscv_build/config.yaml   # relativo a --root
    yaml: sim.vhdl_sources                      # caminho com pontos; `*` percorre os valores de um mapeamento ou uma lista
    base: Tests                                 # relativo a quê são os caminhos (padrão: o diretório do arquivo)
  - name: quartus project
    file: tests/FPGA/core/quartus/core_fpga_test.qsf
    pattern: 'VHDL_FILE (\S+)'                  # grupo 1 de cada casamento
  - name: directories
    paths: [src, tests/FPGA]                    # literais, relativos a --root
```

- `base` é `@file` (o diretório do arquivo que referencia) por padrão, ou um diretório relativo a `--root`.
- Um valor com variável de ambiente (`$QUARTUS_ROOTDIR/...`) é ignorado: depende da máquina.
- Uma referência que não produz nenhum caminho falha, então uma lista renomeada ou reformatada é notada; `optional: true` a permite.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_path_check.py::test_collect_reads_a_yaml_list_relative_to_base_and_skips_env_vars` | Uma lista YAML resolve contra `base`; valores com `$VARIAVEL` são ignorados. |
| `tests/test_path_check.py::test_collect_walks_a_wildcard_over_a_mapping` | `*` percorre os valores de um mapeamento (o `*.sources` do `tests.json`). |
| `tests/test_path_check.py::test_collect_defaults_base_to_the_files_directory` | Sem `base`, os caminhos são relativos ao arquivo que os referencia. |
| `tests/test_path_check.py::test_check_passes_when_every_path_exists` | Referências YAML, JSON, `.qsf` e literais passam quando os arquivos existem. |
| `tests/test_path_check.py::test_check_reports_a_path_that_was_moved` | Um arquivo movido é reportado uma vez por lista que o cita. |
| `tests/test_path_check.py::test_check_fails_when_a_reference_yields_nothing` | Uma lista renomeada ou reformatada falha em vez de passar vazia. |
| `tests/test_path_check.py::test_check_allows_an_optional_reference_to_yield_nothing` | `optional: true` aceita uma referência vazia. |
| `tests/test_path_check.py::test_check_reports_an_unreadable_file_and_a_bad_entry` | Um arquivo ausente e uma entrada malformada são reportados. |
| `tests/test_path_check.py::test_cmd_check_paths_exit_status` | O comando imprime OK, ou sai com 1 listando os problemas. |

## Uso

```bash
uv run riscv-tools --root <projeto> check-paths --manifest paths.yaml
```

Não precisa de `--config`. Status 1 e uma linha `PATH` por problema; feito para o CI, antes e depois de cada movimentação de arquivo.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
