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
| `entity-coverage` | Toda entidade de RTL de `src/` tem uma entrada em `tests/python/tests.json` com ela (ou o testbench `<nome>_tb`) como `toplevel` e o arquivo dela em `sources`; toda entidade da tabela `formal` tem a prova em `formal/` | VHDL |
| `manifest` | A seção `provides` do `paths.yaml` lista cada `.vhd` de `src/` uma única vez, só arquivos que existem e dependências sem ciclo; sem a seção, a regra não confere nada | VHDL |
| `provides-required` | O `paths.yaml` declara a seção `provides`; um repositório de VHDL que a perde (por um merge ou uma reescrita do arquivo) falha em vez de desligar em silêncio a regra `manifest` e o `riscv-tools sources`. A chave `tree.require_provides` troca o padrão do tipo | todos (exige nos de VHDL) |

A regra `vhdl-style` é opcional e só roda quando o `--only` a nomeia, porque o CI tem um passo próprio para o estilo.

| Regra | O que confere | Tipos |
| :--- | :--- | :--- |
| `vhdl-style` | Os arquivos VHDL seguem o guia de estilo, como o `check-vhdl-style` confere (ver [vhdl_style](vhdl_style.md)) | VHDL |

A regra `purity` também é opcional e só roda quando o `--only` a nomeia, porque cada repositório a liga quando os nomes de fornecedor dele já estão nas pastas de fornecedor.

| Regra | O que confere | Tipos |
| :--- | :--- | :--- |
| `purity` | Nenhum nome de placa, de família FPGA, de dispositivo ou de primitiva de fornecedor em arquivo fora das pastas de fornecedor (ver [Pureza](#pureza)) | VHDL |

A regra de cobertura deixa de fora os modelos de simulação (pastas `sim` e `tests`), o código de `vendor/` e os IPs do Quartus. A prova de uma entidade é `formal/<nome>.sv`, `formal/<nome>_props.sv` ou `formal/<nome>/props.sv`, ou os arquivos que a tabela `formal` nomeia para ela. Uma exceção dispensa só o teste de entidade, nunca a prova.

Os tipos são `common-components`, `core`, `memory`, `peripherals`, `top`, `tests`, `certification`, `infra` e `tools`. Os cinco primeiros são os de VHDL. Só o `common-components` não tem `formal/`.

A varredura deixa de fora as pastas ocultas, a saída de build (`build`, `sim_build`, `output_files`, `db`, `incremental_db`), o código de terceiros em `vendor/` e qualquer pasta que seja um repositório próprio, como um submódulo, cujo layout se confere no repositório dele. Um submódulo é reconhecido pelo caminho declarado no `.gitmodules` da raiz, de modo que uma cópia sem `.git` (um `rsync`, por exemplo) também o deixa de fora, e por uma entrada `.git` dentro da pasta. Todas as regras que listam arquivos usam essa mesma varredura: os `.vhd` de `src/common` pertencem ao manifesto do Common-Components e não entram nas regras `manifest`, `entity-coverage`, `vhdl-location`, `folder-names` e `vhdl-style` do repositório que o monta.

## Configuração

Sem seção no `config.yaml`. O `paths.yaml` do repositório pode ter uma seção `tree` com as pastas que são identificadores da ISA ou de um periférico e por isso mantêm as maiúsculas.

```yaml
tree:
  identifier_folders: [I, M, Zicsr, Zicntr, Zihpm, Zifencei, Zicclsm, ISA]
```

A regra de cobertura lê a subseção `coverage`. A tabela `formal` é uma lista de entidades ou um mapa da entidade para os arquivos da prova. As exceções (por exemplo, um invólucro que só instancia um IP) levam sempre a justificativa, e uma exceção sem texto ou para uma entidade que não existe é um problema.

```yaml
tree:
  coverage:
    formal:
      sdram_arbiter: []
      axi_master_bridge: [formal/axi_master/props.sv]
    exceptions:
      boot_memory_shell: instancia só o IP, coberto pela síntese e pela placa
```

A regra `manifest` lê a seção `provides` da raiz do `paths.yaml`. Cada componente lista em `sources` os arquivos na ordem de análise do GHDL e em `requires` os componentes de que precisa: um nome sem prefixo é do mesmo repositório e `<repositório>/<componente>` é de outro. O nome do repositório vem da chave `repository` da raiz, ou da pasta quando ela falta. Um componente sem `sources` e com `requires` só agrupa outros (o topo de uma placa gerada usa isso para dar a lista de fontes do projeto). O componente pode ter ainda `needs`, a lista dos tipos de recurso de placa de que depende; um tipo fora do conjunto conhecido é um problema do manifesto.

```yaml
repository: Core
provides:
  Zicntr:
    requires: [constants]
    sources: [src/Zicntr/counter64.vhd, src/Zicntr/tick_divider.vhd]
```

A regra `provides-required` exige a seção nos cinco tipos de VHDL. Um repositório que não deve tê-la escreve `require_provides: false` na seção `tree`, e um tipo que não é de VHDL pede a seção com `require_provides: true`. Qualquer outro valor é um problema.

```yaml
tree:
  require_provides: true
```

## Pureza

A parte portável de um repositório (o SoC, o núcleo, as memórias) conversa com os vizinhos por contratos de interface e não cita placa, família nem primitiva de fornecedor. Esses nomes ficam nas pastas de fornecedor (`altera/`) e nos dados de placa (`boards/`). A regra `purity` lê, na mesma varredura das outras regras, os arquivos de fora dessas pastas e reporta cada termo achado, com a primeira linha e a contagem:

```text
TREE purity src/ROM/Cyclone-V/flash.vhd:2: primitives:altsyncram* (4x) outside the vendor folders
```

Os termos são dado. O arquivo `src/riscv_tools/tree_check/purity.yaml` traz os padrões, em cinco grupos: `primitives` (`altsyncram`, `altpll`, `altera_*`, `sld_virtual_jtag`, `intended_device_family`), `families`, `boards`, `devices` e `idcodes`. A comparação ignora maiúsculas, tem limite de palavra à esquerda, aceita hífen, sublinhado, espaço ou nada onde o termo tem `-` ou espaço, e não aceita letra logo depois do termo, a não ser que ele termine em `*`. A mesma lista diz as pastas de fornecedor (`altera`, `boards`, em qualquer profundidade, sem diferença de maiúsculas) e as extensões lidas (`.vhd`, `.vhdl`, `.v`, `.sv`, `.vh`).

O `paths.yaml` do repositório acrescenta a esses dados na subseção `purity` da seção `tree`: `terms` (grupo e termos), `vendor_folders`, `suffixes` e `exceptions`. Uma exceção é um caminho, uma pasta ou um padrão (`fnmatch`) com a justificativa. Uma exceção sem justificativa e uma que não dispensa arquivo nenhum são problemas.

```yaml
tree:
  purity:
    terms:
      boards: [nova-placa]
    vendor_folders: [intel]
    exceptions:
      src/legado/top.vhd: invólucro mantido até o pacote de placa existir
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
| `tests/test_submodule_exclusion.py::test_manifest_ignores_files_of_a_submodule` | A regra `manifest` não cobra os arquivos de um submódulo montado. |
| `tests/test_submodule_exclusion.py::test_manifest_ignores_a_submodule_without_git` | Uma cópia sem `.git` também deixa o submódulo do `.gitmodules` de fora. |
| `tests/test_submodule_exclusion.py::test_coverage_and_location_ignore_a_submodule` | `entity-coverage` e `vhdl-location` pulam os arquivos do submódulo. |
| `tests/test_submodule_exclusion.py::test_a_folder_that_is_not_a_submodule_is_still_checked` | Só os caminhos do `.gitmodules` ficam de fora. |
| `tests/test_tree_check.py::test_folder_names_reject_space_accent_and_capitals` | Espaço, acento e maiúscula em nome de pasta são reportados. |
| `tests/test_tree_check.py::test_folder_names_accept_the_identifiers_listed_in_paths_yaml` | Os identificadores listados no `paths.yaml` mantêm as maiúsculas. |
| `tests/test_tree_check.py::test_folder_names_leave_out_vendor_code` | O código de terceiros mantém os nomes de origem. |
| `tests/test_tree_check.py::test_rules_depend_on_the_kind` | As regras de VHDL não valem para os outros tipos. |
| `tests/test_tree_check.py::test_an_unknown_kind_or_rule_is_an_error` | Um tipo ou uma regra que não existe ou não vale falha. |
| `tests/test_tree_check.py::test_cmd_check_tree_exit_status` | O comando imprime OK, ou sai com 1 listando os problemas, ou com 2 numa regra desconhecida. |
| `tests/test_tree_check.py::test_the_subcommand_is_registered_without_a_config` | O subcomando roda sem `--config`. |
| `tests/test_entity_coverage.py::test_coverage_runs_by_default_and_style_is_opt_in` | `entity-coverage` e `manifest` rodam por padrão nos tipos de VHDL, e `vhdl-style` só com o `--only`. |
| `tests/test_entity_coverage.py::test_an_entity_with_its_test_passes` | Um teste com a entidade como `toplevel` e o arquivo dela em `sources` a cobre. |
| `tests/test_entity_coverage.py::test_a_testbench_named_after_the_entity_covers_it` | O `toplevel` `<nome>_tb` conta como a entidade. |
| `tests/test_entity_coverage.py::test_an_entity_without_a_test_is_reported` | Um teste de sistema que só lista o arquivo não cobre a entidade. |
| `tests/test_entity_coverage.py::test_a_test_must_list_the_file_of_the_entity` | O `toplevel` sem o arquivo em `sources` falha. |
| `tests/test_entity_coverage.py::test_models_ips_and_vendor_are_not_rtl` | Modelos de simulação, IPs e `vendor/` não pedem teste. |
| `tests/test_entity_coverage.py::test_an_exception_needs_a_justification` | A exceção exige justificativa e uma exceção velha falha. |
| `tests/test_entity_coverage.py::test_a_named_proof_needs_its_file` | Cada entidade da tabela `formal` exige o arquivo da prova. |
| `tests/test_entity_coverage.py::test_a_proof_may_follow_the_other_names_or_be_named` | `<nome>_props.sv`, `<nome>/props.sv` e um arquivo nomeado na tabela valem como prova. |
| `tests/test_entity_coverage.py::test_an_exception_excuses_the_test_but_not_the_proof` | Uma exceção dispensa o teste de entidade e mantém a exigência da prova. |
| `tests/test_manifest_sources.py::test_without_provides_the_rule_is_silent` | Sem a seção `provides`, a regra `manifest` não confere nada. |
| `tests/test_manifest_sources.py::test_a_complete_manifest_passes` | Cada arquivo listado uma vez e existente passa. |
| `tests/test_manifest_sources.py::test_unlisted_missing_duplicate_and_unknown` | Arquivo inexistente, listado duas vezes, sem componente, requisito desconhecido e ciclo são reportados. |
| `tests/test_manifest_sources.py::test_a_malformed_manifest_is_reported` | Um componente sem `sources` e sem `requires` é reportado. |
| `tests/test_manifest_sources.py::test_a_component_may_only_group_others` | Um componente sem `sources` e com `requires` só agrupa e passa. |
| `tests/test_provides_required.py::test_a_vhdl_repository_without_provides_fails` | Um repositório de VHDL sem a seção `provides` falha. |
| `tests/test_provides_required.py::test_a_missing_paths_yaml_fails_too` | Sem o `paths.yaml` também não há seção. |
| `tests/test_provides_required.py::test_a_repository_with_provides_passes` | Declarar a seção cumpre a regra em todos os tipos. |
| `tests/test_provides_required.py::test_a_malformed_section_is_left_to_the_manifest_rule` | Uma seção malformada é problema da regra `manifest`, não da ausência. |
| `tests/test_provides_required.py::test_the_tree_section_can_opt_out` | `require_provides: false` dispensa a seção num tipo de VHDL. |
| `tests/test_provides_required.py::test_the_tree_section_can_ask_for_other_kinds` | `require_provides: true` exige a seção num tipo que não é de VHDL. |
| `tests/test_provides_required.py::test_a_value_that_is_not_a_boolean_is_reported` | Só `true` ou `false` vale. |
| `tests/test_provides_required.py::test_the_default_run_includes_the_rule` | O `check-tree` sem `--only` já pega a perda. |
| `tests/test_entity_coverage.py::test_vhdl_style_runs_through_check_tree` | Nomear `vhdl-style` no `--only` reporta os desvios do guia. |
| `tests/test_tree_purity.py::test_a_portable_tree_passes` | Um arquivo que não cita placa, família nem primitiva passa. |
| `tests/test_tree_purity.py::test_a_vendor_primitive_outside_a_vendor_folder_fails` | Cada primitiva dos dados é reportada com arquivo e linha. |
| `tests/test_tree_purity.py::test_a_board_name_fails_in_any_spelling` | Maiúscula, hífen, sublinhado e a falta de separador são a mesma placa. |
| `tests/test_tree_purity.py::test_a_family_a_device_and_an_idcode_fail` | Família, dispositivo e IDCODE da JTAG também são nomes de placa. |
| `tests/test_tree_purity.py::test_a_vendor_folder_is_exempt_at_any_depth` | `altera/` e `boards/` podem citar fornecedor, família e placa, em qualquer profundidade. |
| `tests/test_tree_purity.py::test_a_word_that_only_looks_like_a_term_passes` | O limite de palavra deixa passar `alteração` e `altera o valor`. |
| `tests/test_tree_purity.py::test_only_the_listed_suffixes_are_read` | Documentos e arquivos de placa não são fontes de RTL. |
| `tests/test_tree_purity.py::test_the_first_line_and_the_count_are_reported` | Vários acertos do mesmo termo num arquivo viram um problema só. |
| `tests/test_tree_purity.py::test_an_exception_excuses_a_file_a_folder_or_a_pattern` | Caminho, pasta e padrão cobrem os arquivos que casam. |
| `tests/test_tree_purity.py::test_an_exception_needs_a_justification_and_a_file` | Exceção sem justificativa ou sem arquivo a dispensar é problema. |
| `tests/test_tree_purity.py::test_the_repository_adds_terms_folders_and_suffixes` | O `paths.yaml` acrescenta aos dados sem substituí-los. |
| `tests/test_tree_purity.py::test_the_terms_come_from_the_data_file` | Trocar o `purity.yaml` troca o veredito: nada está no código. |
| `tests/test_tree_purity.py::test_a_submodule_is_left_to_its_own_repository` | Pastas do `.gitmodules` ficam de fora. |
| `tests/test_tree_purity.py::test_the_rule_is_opt_in_and_for_the_vhdl_kinds` | A rodada padrão não a inclui e os tipos sem VHDL a recusam. |
| `tests/test_tree_purity.py::test_cmd_check_tree_runs_the_rule` | O comando sai com 1 e uma linha `TREE purity`, ou com 0 quando limpo. |

## Uso

```bash
uv run riscv-tools --root <repositório> check-tree --kind core
uv run riscv-tools --root <repositório> check-tree --kind core --only standard-files,language-pairs
uv run riscv-tools --root <repositório> check-tree --kind core --only purity
```

Não precisa de `--config`. Status 1 e uma linha `TREE` por problema; feito para o CI de cada repositório, antes e depois de cada movimentação de arquivo.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
