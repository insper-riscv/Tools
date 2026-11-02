# `tree_check`

Confere que a árvore de um repositório segue o layout que todos compartilham. Os repositórios do projeto trocam submódulos, documentos e arquivos de configuração, e cada um só falha quando alguém tropeça no que ficou fora do lugar: um `README` sem a metade em inglês, um arquivo VHDL numa pasta que o build não lê, uma pasta com espaço no nome que o Quartus parte em dois. Este módulo lê a árvore e falha na primeira mudança que a desvia do layout, então uma movimentação de arquivos é conferida antes de qualquer build.

## Regras

Cada regra olha um aspecto da árvore e vale para alguns tipos de repositório. O tipo decide quais regras rodam.

| Regra | O que confere | Tipos |
| :--- | :--- | :--- |
| `standard-files` | Os arquivos que todo repositório do tipo tem: licença, `README`, `CONTRIBUTING`, `AUTHORS`, `CITATION.cff`, `.gitignore` e `.github/workflows`; nos de VHDL também `Makefile`, `paths.yaml`, `pyproject.toml`, `uv.lock`, `src/` e `tests/python/`; nos que têm provas, `formal/run.sh` | todos |
| `language-pairs` | `README`, `CONTRIBUTING` e `AUTHORS` existem nas duas línguas, e todo `.md` de `docs/pt-br/` tem o espelho em `docs/en/` com o mesmo caminho | todos |
| `vhdl-location` | Nenhum `.vhd` fora de `src/` e `tests/vhdl/` | VHDL |
| `common-submodule` | O Common-Components está montado em `src/common` | `core`, `memory`, `peripherals` |
| `folder-names` | Nomes de pasta em minúsculas, dígitos, hífen, ponto e sublinhado, sem espaço nem acento | VHDL |

Os tipos são `common-components`, `core`, `memory`, `peripherals`, `top`, `tests`, `certification`, `infra` e `tools`. Os cinco primeiros são os de VHDL. Só o `common-components` não tem `formal/`.

A varredura deixa de fora as pastas ocultas, a saída de build (`build`, `sim_build`, `output_files`, `db`, `incremental_db`), o código de terceiros em `vendor/` e qualquer pasta que seja um repositório próprio, como um submódulo, cujo layout se confere no repositório dele.

## Configuração

Sem seção no `config.yaml`. O `paths.yaml` do repositório pode ter uma seção `tree` com as pastas que são identificadores da ISA ou de um periférico e por isso mantêm as maiúsculas.

```yaml
tree:
  identifier_folders: [I, M, Zicsr, Zicntr, Zihpm, Zifencei, Zicclsm, ISA]
```

## Adoção por etapas

Um repositório que ainda não terminou a reorganização escolhe com `--only` as regras que já cumpre, e a lista cresce a cada etapa. Uma regra que não vale para o tipo é um erro, não um passo vazio.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_tree_check.py::test_a_conforming_tree_has_no_problem` | Uma árvore que cumpre todas as regras passa. |
| `tests/test_tree_check.py::test_standard_files_reports_each_missing_file` | Cada arquivo padrão ausente é reportado pelo nome. |
| `tests/test_tree_check.py::test_common_components_needs_no_formal_folder` | O tipo sem provas não precisa de `formal/run.sh`. |
| `tests/test_tree_check.py::test_language_pairs_reports_a_missing_half` | Um `README` sem a metade em inglês é reportado. |
| `tests/test_tree_check.py::test_language_pairs_reports_a_document_without_its_mirror` | Um documento sem o espelho na outra língua é reportado nos dois sentidos. |
| `tests/test_tree_check.py::test_vhdl_location_reports_a_file_outside_src` | Um `.vhd` fora de `src/` e `tests/vhdl/` falha. |
| `tests/test_tree_check.py::test_vhdl_location_leaves_out_build_output_and_submodules` | Saída de build e pastas de submódulo não são conferidas. |
| `tests/test_tree_check.py::test_common_submodule_requires_the_mount_at_src_common` | O Common-Components precisa estar declarado em `src/common`. |
| `tests/test_tree_check.py::test_common_submodule_requires_the_right_repository` | O submódulo de `src/common` precisa ser o Common-Components. |
| `tests/test_tree_check.py::test_common_submodule_is_reported_without_gitmodules` | Sem `.gitmodules`, o submódulo não está montado. |
| `tests/test_tree_check.py::test_folder_names_reject_space_accent_and_capitals` | Espaço, acento e maiúscula em nome de pasta são reportados. |
| `tests/test_tree_check.py::test_folder_names_accept_the_identifiers_listed_in_paths_yaml` | Os identificadores listados no `paths.yaml` mantêm as maiúsculas. |
| `tests/test_tree_check.py::test_folder_names_leave_out_vendor_code` | O código de terceiros mantém os nomes de origem. |
| `tests/test_tree_check.py::test_rules_depend_on_the_kind` | As regras de VHDL não valem para os outros tipos. |
| `tests/test_tree_check.py::test_an_unknown_kind_or_rule_is_an_error` | Um tipo ou uma regra que não existe ou não vale falha. |
| `tests/test_tree_check.py::test_cmd_check_tree_exit_status` | O comando imprime OK, ou sai com 1 listando os problemas, ou com 2 numa regra desconhecida. |
| `tests/test_tree_check.py::test_the_subcommand_is_registered_without_a_config` | O subcomando roda sem `--config`. |

## Uso

```bash
uv run riscv-tools --root <repositório> check-tree --kind core
uv run riscv-tools --root <repositório> check-tree --kind core --only standard-files,language-pairs
```

Não precisa de `--config`. Status 1 e uma linha `TREE` por problema; feito para o CI de cada repositório, antes e depois de cada movimentação de arquivo.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
