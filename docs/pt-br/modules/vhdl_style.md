# `vhdl_style`

Faz o [VSG](https://vhdl-style-guide.readthedocs.io) conferir o estilo dos arquivos VHDL de um repositório, com a configuração e as regras locais do projeto. O guia de estilo é o das seções de VHDL do `CONTRIBUTING.md` do `Core`, repetido nos repositórios, e cada um só descobria que um arquivo o desrespeita quando alguém revisava à mão. O VSG é a única ferramenta de estilo: ele traz as regras de formato, de nome e de comprimento, e as regras locais acrescentam o que o VSG não conhece.

## 1. O que o módulo guarda

| Dado | Conteúdo |
| :--- | :--- |
| `vsg.yaml` | Configuração do VSG para todo o projeto, cada desvio do padrão justificado em comentário |
| `vsg-board.yaml` | Camada para os topos de placa em `cyclone-v/`, que desliga as regras de nome |
| `local_rules/` | As seis regras locais, um arquivo por regra, mais o `capstone_rule.py` que elas compartilham |
| `vendor_primitives.yaml` | Lista das primitivas de fabricante que a `component_900` aceita por `component`, cada uma com biblioteca e justificativa |

## 2. Regras locais

Cada regra tem o identificador `<grupo>_900` e a mensagem em português, com a seção do `CONTRIBUTING.md` que ela cobra. Nenhuma corrige o arquivo.

| Regra | O que confere |
| :--- | :--- |
| `header_900` | O arquivo abre com o cabeçalho: uma linha de `=` (de qualquer largura), a descrição e uma linha de fechamento |
| `library_900` | Do pacote IEEE, só `std_logic_1164` e `numeric_std` |
| `component_900` | Nenhuma declaração nem instância com `component`, salvo as primitivas de fabricante de `vendor_primitives.yaml`; a instância é direta, `u_x : entity work.x` |
| `port_map_900` | Toda associação de um `port map` é por nome (`i_porta => sinal`) |
| `process_900` | O rótulo de todo processo (e o do `end process`) começa com `p_`; o processo sem rótulo é acusado pela `process_016` do VSG |
| `docstring_900` | Todo `generic`, `port`, `constant`, `subtype`, `type`, `signal`, `alias` e `variable` tem um comentário na linha imediatamente acima; um comentário no fim da linha ou uma linha só de separador não vale |

A `component_900` não tem exceção para código nosso nem para IP gerado (PLL), cujo arquivo o repositório deixa de fora em `tree.vhdl_style.exclude` do `paths.yaml`. A única exceção são as primitivas de fabricante de `vendor_primitives.yaml`, hoje `altsyncram` e `sld_virtual_jtag`: o Quartus Lite as expõe só como `component` do pacote `altera_mf_components`, sem unidade primária de entidade, e o `quartus_map` 25.1 rejeita `entity altera_mf.altsyncram` com o erro 10481. A exceção vale só no arquivo em que a biblioteca da primitiva está visível, por `library altera_mf;` ou por `use altera_mf.altera_mf_components.all;`. Ela vale para a declaração, para `u_x : component nome` e para `u_x : nome`; qualquer outro nome continua acusado. Para incluir uma primitiva, acrescente nome, biblioteca e justificativa ao `vendor_primitives.yaml`. A `instantiation_034` do VSG, que não conhece a lista, fica desativada no `vsg.yaml`. Os parâmetros de uma função ou de um procedimento não são declarações para a `docstring_900`. Um `--fix` do VSG que separa `signal a, b : t;` em duas linhas deixa a segunda sem comentário, e a `docstring_900` a acusa.

Os prefixos de porta, as constantes em `UPPER_SNAKE_CASE`, os tipos com `_t`, os rótulos de instância com `u_` e os de generate com `gen_` são regras do próprio VSG (`port_600` a `port_602`, `constant_004`, `type_600`, `subtype_600`, `instantiation_601` e `generate_017`), configuradas no `vsg.yaml`; todas aplicam o prefixo configurado. A `process_600` do VSG só aceita sufixo (`_proc`) e ignora a opção `prefixes`, então fica desativada e o prefixo `p_` é conferido pela `process_900`.

## 3. Arquivos conferidos

`riscv-tools vhdl-files` lista `src/**/*.vhd` e `tests/vhdl/*.vhd`, sem o código de terceiros, os submódulos e o que o `paths.yaml` exclui.

| Arquivo | Como é reconhecido |
| :--- | :--- |
| Código de terceiros | Pasta `vendor/` |
| Submódulo | Caminho no `.gitmodules` ou pasta com `.git`, como o `src/common` |
| Outros | Os globs de `tree.vhdl_style.exclude` no `paths.yaml`, relativos à raiz |

```yaml
tree:
  vhdl_style:
    exclude: ["src/gerado/*.vhd"]
```

Os topos de placa em `cyclone-v/` (sem distinção de maiúsculas) ficam na lista, mas à parte: `vhdl-files --board` os lista, e o VSG os confere com o `vsg-board.yaml` por cima do `vsg.yaml`. Os nomes de pino e de sinal vêm do `.qsf` do Quartus e não seguem as regras de nome, mas cabeçalho, bibliotecas, `component`, `port map` e docstrings valem como nos outros arquivos.

## 4. Subcomandos

Nenhum precisa de `--config`.

| Subcomando | O que faz |
| :--- | :--- |
| `vsg-config` | Imprime o caminho do `vsg.yaml`; com `--board`, o do `vsg-board.yaml` |
| `vsg-rules` | Imprime o caminho da pasta das regras locais |
| `vhdl-files` | Lista os arquivos conferidos, um por linha; com `--board`, os topos de placa |
| `check-vhdl-style` | Atalho que roda o VSG com a configuração e as regras do projeto sobre esses arquivos |

O `check-vhdl-style` aplica as regras que o CI exige hoje, as cinco locais mais os prefixos de porta, as constantes, os tipos e os rótulos de instância. Com `--full` aplica todas as regras do `vsg.yaml`, inclusive indentação, alinhamento, caixa e comprimento. Sai com status 1 quando o VSG acusa algum desvio.

## 5. Uso

```bash
uv run riscv-tools --root <repositório> check-vhdl-style
uv run riscv-tools --root <repositório> check-vhdl-style --full
uv run riscv-tools --root <repositório> check-tree --kind memory --only vhdl-style
```

O VSG também roda direto, e `--fix` corrige formato:

```bash
cd <repositório>
vsg -c "$(riscv-tools vsg-config)" -lr "$(riscv-tools vsg-rules)" -ap -f $(riscv-tools vhdl-files)
vsg -c "$(riscv-tools vsg-config)" "$(riscv-tools vsg-config --board)" -lr "$(riscv-tools vsg-rules)" -ap -f $(riscv-tools vhdl-files --board)
```

Quem quiser um desvio local cria um `vsg.local.yaml` na raiz e o passa depois do `vsg.yaml`, em `-c`. A regra `vhdl-style` do `check-tree` roda a mesma conferência e só entra quando o `--only` a nomeia.

## 6. Passo de CI

Cada repositório de VHDL chama o subcomando num passo do job `vhdl-syntax`, depois de montar o ambiente, quando a imagem `ci-vhdl` traz a versão do Tools que o contém.

```yaml
      - name: VHDL style
        run: riscv-tools --root . check-vhdl-style
```

## 7. Escrever uma regra local

1. Um arquivo `<grupo>_900.py` em `local_rules/`, com uma classe `rule_<grupo>_900` que herda de `LocalRule` e implementa `find`, devolvendo pares `(linha, mensagem)`.
2. A mensagem em português cita a seção do `CONTRIBUTING.md` violada.
3. O arquivo importa só o `capstone_rule`, nunca o `riscv_tools`, porque o VSG pode rodar num ambiente à parte.
4. A regra entra em `GATE_RULES` no `runner.py` quando o CI passa a exigi-la, e ganha fixtures que passam e que reprovam em `tests/test_vhdl_style.py`.

## 8. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_vhdl_style.py::test_a_conforming_file_has_no_violation` | Um arquivo que segue o guia passa em todas as regras. |
| `tests/test_vhdl_style.py::test_header_is_required` | Sem cabeçalho, o desvio sai na linha 1. |
| `tests/test_vhdl_style.py::test_header_needs_description_and_closing_line` | Cabeçalho sem descrição ou sem fechamento falha. |
| `tests/test_vhdl_style.py::test_header_has_no_minimum_width` | Cabeçalhos de 40 e de 100 colunas passam. |
| `tests/test_vhdl_style.py::test_libraries_allow_only_the_two_packages` | Outro pacote do IEEE falha. |
| `tests/test_vhdl_style.py::test_component_is_forbidden_but_not_in_comments` | `component` falha, e o comentário que o cita não. |
| `tests/test_vhdl_style.py::test_component_has_no_exception_for_generated_wrappers` | O invólucro de PLL também falha. |
| `tests/test_vhdl_style.py::test_vendor_primitive_component_is_accepted` | `altsyncram` e `sld_virtual_jtag` por `component` passam com `library altera_mf`. |
| `tests/test_vhdl_style.py::test_vendor_primitive_instance_without_keyword_is_accepted` | `u_x : altsyncram` passa com `use altera_mf...` visível. |
| `tests/test_vhdl_style.py::test_vendor_primitive_component_declaration_is_accepted` | A declaração de uma primitiva da lista passa. |
| `tests/test_vhdl_style.py::test_vendor_primitive_needs_the_library` | Sem `altera_mf` visível a primitiva é acusada. |
| `tests/test_vhdl_style.py::test_component_outside_the_list_is_reported` | `meu_bloco` e `pll_0002` falham mesmo com a biblioteca. |
| `tests/test_vhdl_style.py::test_process_label_with_the_prefix_passes` | `p_x` e `p_x_proc` passam. |
| `tests/test_vhdl_style.py::test_process_label_without_the_prefix_fails` | `x` e `proc_p` falham, no rótulo e no `end process`. |
| `tests/test_vhdl_style.py::test_process_without_a_label_fails` | O processo sem rótulo é acusado pela `process_016`. |
| `tests/test_vhdl_style.py::test_the_other_prefix_rules_apply_their_prefix` | Portas, instâncias e generates aplicam o prefixo configurado. |
| `tests/test_vhdl_style.py::test_aligned_others_arrow_is_not_reported` | A seta alinhada depois de `others` não é acusada (`element_association_100` desativada). |
| `tests/test_vhdl_style.py::test_component_instance_is_forbidden` | A instância `u_x : component x` falha. |
| `tests/test_vhdl_style.py::test_port_map_must_associate_by_name` | Associação posicional num `port map` falha. |
| `tests/test_vhdl_style.py::test_docstrings_are_needed_above_each_declaration` | Falta de comentário, comentário no fim da linha e separador falham. |
| `tests/test_vhdl_style.py::test_docstrings_cover_generics_and_ports` | Generics e portas exigem comentário. |
| `tests/test_vhdl_style.py::test_docstrings_skip_subprogram_parameters` | Parâmetros de função não são declarações. |
| `tests/test_vhdl_style.py::test_real_memory_signals_before_the_fix_pass` | Os sinais reais do Memory, com um comentário para cinco nomes, passam. |
| `tests/test_vhdl_style.py::test_real_memory_signals_after_the_fix_fail` | Os quatro nomes que o `--fix` separou perdem o comentário e falham. |
| `tests/test_vhdl_style.py::test_real_insper_signals_after_the_fix_fail` | Os sinais reais do Insper-RISC-V depois do `--fix` falham. |
| `tests/test_vhdl_style.py::test_ports_and_names_come_from_the_vsg_rules` | Prefixo, constante, tipo e rótulo seguem as regras do VSG. |
| `tests/test_vhdl_style.py::test_vendor_code_is_left_out` | `vendor/` não entra na lista. |
| `tests/test_vhdl_style.py::test_quartus_megafunction_files_are_listed` | Arquivo com `altera_mf` entra na lista. |
| `tests/test_vhdl_style.py::test_instance_by_component_name_is_forbidden` | A instância `u_x : nome` sem `entity` falha. |
| `tests/test_vhdl_style.py::test_paths_yaml_can_leave_out_more_files` | Os globs do `paths.yaml` ficam de fora. |
| `tests/test_vhdl_style.py::test_the_scope_is_src_and_the_tests_folder` | Só `src/**` e `tests/vhdl/*.vhd` entram. |
| `tests/test_vhdl_style.py::test_submodules_are_left_out` | Os arquivos de um submódulo não entram. |
| `tests/test_vhdl_style.py::test_board_files_are_listed_apart` | Os topos de `cyclone-v/` só saem com `--board`. |
| `tests/test_vhdl_style.py::test_board_files_follow_the_rules_but_not_the_naming` | Topo de placa mantém os nomes de pino e ainda exige cabeçalho. |
| `tests/test_vhdl_style.py::test_the_gate_accepts_what_only_the_full_check_rejects` | Linha longa passa no padrão e falha no `--full`. |
| `tests/test_vhdl_style.py::test_the_packaged_data_exist` | Configuração, camada, lista de primitivas e as seis regras são arquivos do pacote. |
| `tests/test_vhdl_style.py::test_local_rule_messages_are_in_portuguese` | A mensagem cita o `CONTRIBUTING`. |
| `tests/test_vhdl_style.py::test_cmd_check_vhdl_style_exit_status` | O comando imprime OK, ou sai com 1 listando. |
| `tests/test_vhdl_style.py::test_the_vsg_subcommands_print_paths_and_files` | Os subcomandos imprimem caminhos e arquivos. |
| `tests/test_vhdl_style.py::test_the_subcommands_are_registered_without_a_config` | Os subcomandos rodam sem `--config`. |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
