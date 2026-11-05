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

Duas regras são opcionais e só rodam quando o `--only` as nomeia, para que cada repositório as adote quando as cumprir.

| Regra | O que confere | Tipos |
| :--- | :--- | :--- |
| `vhdl-style` | Os arquivos VHDL seguem o guia de estilo, como o `check-vhdl-style` confere (ver [vhdl_style](vhdl_style.md)) | VHDL |
| `entity-coverage` | Toda entidade de RTL de `src/` tem uma entrada em `tests/python/tests.json` com ela (ou o testbench `<nome>_tb`) como `toplevel` e o arquivo dela em `sources`; toda entidade da lista `formal` tem `formal/<nome>.sv` | VHDL |

A regra de cobertura deixa de fora os modelos de simulação (pastas `sim` e `tests`), o código de `vendor/` e os IPs do Quartus.

Os tipos são `common-components`, `core`, `memory`, `peripherals`, `top`, `tests`, `certification`, `infra` e `tools`. Os cinco primeiros são os de VHDL. Só o `common-components` não tem `formal/`.

A varredura deixa de fora as pastas ocultas, a saída de build (`build`, `sim_build`, `output_files`, `db`, `incremental_db`), o código de terceiros em `vendor/` e qualquer pasta que seja um repositório próprio, como um submódulo, cujo layout se confere no repositório dele.

## Configuração

Sem seção no `config.yaml`. O `paths.yaml` do repositório pode ter uma seção `tree` com as pastas que são identificadores da ISA ou de um periférico e por isso mantêm as maiúsculas.

```yaml
tree:
  identifier_folders: [I, M, Zicsr, Zicntr, Zihpm, Zifencei, Zicclsm, ISA]
```

A regra de cobertura lê a subseção `coverage`. As exceções (por exemplo, um invólucro que só instancia um IP) levam sempre a justificativa, e uma exceção sem texto ou para uma entidade que não existe é um problema.

```yaml
tree:
  coverage:
    formal: [sdram_arbiter, axi_master_bridge]
    exceptions:
      boot_rom_shell: instancia só o IP, coberto pela síntese e pela placa
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
| `tests/test_entity_coverage.py::test_the_new_rules_are_opt_in` | `vhdl-style` e `entity-coverage` existem para os tipos de VHDL e não rodam sem o `--only`. |
| `tests/test_entity_coverage.py::test_an_entity_with_its_test_passes` | Um teste com a entidade como `toplevel` e o arquivo dela em `sources` a cobre. |
| `tests/test_entity_coverage.py::test_a_testbench_named_after_the_entity_covers_it` | O `toplevel` `<nome>_tb` conta como a entidade. |
| `tests/test_entity_coverage.py::test_an_entity_without_a_test_is_reported` | Um teste de sistema que só lista o arquivo não cobre a entidade. |
| `tests/test_entity_coverage.py::test_a_test_must_list_the_file_of_the_entity` | O `toplevel` sem o arquivo em `sources` falha. |
| `tests/test_entity_coverage.py::test_models_ips_and_vendor_are_not_rtl` | Modelos de simulação, IPs e `vendor/` não pedem teste. |
| `tests/test_entity_coverage.py::test_an_exception_needs_a_justification` | A exceção exige justificativa e uma exceção velha falha. |
| `tests/test_entity_coverage.py::test_a_named_proof_needs_its_file` | Cada entidade da lista `formal` exige `formal/<nome>.sv`. |
| `tests/test_entity_coverage.py::test_vhdl_style_runs_through_check_tree` | Nomear `vhdl-style` no `--only` reporta os desvios do guia. |

## Uso

```bash
uv run riscv-tools --root <repositório> check-tree --kind core
uv run riscv-tools --root <repositório> check-tree --kind core --only standard-files,language-pairs
```

Não precisa de `--config`. Status 1 e uma linha `TREE` por problema; feito para o CI de cada repositório, antes e depois de cada movimentação de arquivo.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
