# `vhdl_style`

Confere que os arquivos VHDL de um repositório seguem o guia de estilo do projeto, o mesmo das seções de VHDL do `CONTRIBUTING.md` do `Core`. Os repositórios repetem esse guia, e cada um só descobre que um arquivo o desrespeita quando alguém revisa a mão. Este módulo lê os arquivos e lista cada desvio com o arquivo, a linha e a regra, então o estilo é conferido no CI e não na revisão.

## Regras

| Regra | O que confere |
| :--- | :--- |
| `header` | O arquivo abre com o bloco de cabeçalho: uma linha de `=` (de qualquer largura), a descrição e uma linha de fechamento |
| `libraries` | Do pacote IEEE, só `std_logic_1164` e `numeric_std` |
| `component` | Nenhuma declaração nem instanciação com `component`; a instância é direta, `u_x : entity work.x` |
| `port-map` | Toda associação de um `port map` é por nome (`i_porta => sinal`) |
| `ports` | Toda porta começa com `i_` (entrada), `o_` (saída e `buffer`) ou `io_` (`inout`) |
| `docstrings` | Todo `generic`, `port`, `constant`, `subtype`, `type`, `signal`, `alias` e `variable` tem um comentário na linha imediatamente acima; um comentário no fim da linha ou uma linha só de separador não vale |
| `naming` | Constantes em `UPPER_SNAKE_CASE`, tipos e subtipos em `snake_case` com o sufixo `_t`, rótulos de instância com o prefixo `u_` |

Comentários e literais de texto e de caractere não contam como código, então uma palavra-chave dentro deles não gera desvio. Os parâmetros de uma função ou de um procedimento não são declarações para a regra `docstrings`.

## O que fica de fora

A varredura é a mesma do `tree_check` (sem pastas ocultas, saída de build e submódulos) e também deixa de fora o que ninguém edita à mão.

| Arquivo | Como é reconhecido |
| :--- | :--- |
| Código de terceiros | Pasta `vendor/` |
| IP gerado pelo Quartus | Pasta `cyclone-v/` (sem distinção de maiúsculas) ou o uso da biblioteca `altera_mf` ou do texto `megafunction wizard` no arquivo |
| Outros | Os globs de `tree.vhdl_style.exclude` no `paths.yaml` do repositório, relativos à raiz |

```yaml
tree:
  vhdl_style:
    exclude: ["src/gerado/*.vhd"]
```

## Uso

```bash
uv run riscv-tools --root <repositório> check-vhdl-style
uv run riscv-tools --root <repositório> check-vhdl-style --only header,ports
uv run riscv-tools --root <repositório> check-tree --kind memory --only vhdl-style
```

Não precisa de `--config`. Cada desvio sai em `STYLE <arquivo>:<linha>: <regra> <mensagem>`, e o status é 1 com pelo menos um desvio, 2 numa regra desconhecida. A regra `vhdl-style` do `check-tree` roda a mesma conferência e só entra quando o `--only` a nomeia.

## Passo de CI

Cada repositório de VHDL chama o subcomando num passo do job `vhdl-syntax` (ou do `python-static-analysis`), depois de montar o ambiente, quando a imagem `ci-vhdl` traz a versão do Tools que o contém.

```yaml
      - name: VHDL style
        run: riscv-tools --root . check-vhdl-style
```

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_vhdl_style.py::test_a_conforming_file_has_no_violation` | Um arquivo que segue o guia passa em todas as regras. |
| `tests/test_vhdl_style.py::test_header_is_required` | Sem cabeçalho, o desvio sai na linha 1. |
| `tests/test_vhdl_style.py::test_header_needs_description_and_closing_line` | Cabeçalho sem descrição ou sem fechamento falha. |
| `tests/test_vhdl_style.py::test_header_has_no_minimum_width` | Um cabeçalho de 40 colunas passa, e os de 80 também. |
| `tests/test_vhdl_style.py::test_libraries_allow_only_the_two_packages` | Outro pacote do IEEE falha. |
| `tests/test_vhdl_style.py::test_component_is_forbidden_but_not_in_comments` | `component` falha, e o comentário que o cita não. |
| `tests/test_vhdl_style.py::test_port_map_must_associate_by_name` | Associação posicional num `port map` falha. |
| `tests/test_vhdl_style.py::test_ports_need_the_prefix_of_their_mode` | Cada modo exige o seu prefixo. |
| `tests/test_vhdl_style.py::test_docstrings_are_needed_above_each_declaration` | Falta de comentário acima, comentário no fim da linha e separador falham. |
| `tests/test_vhdl_style.py::test_docstrings_cover_generics_and_skip_subprogram_parameters` | Generics exigem comentário e parâmetros de função não. |
| `tests/test_vhdl_style.py::test_naming_of_constants_types_and_labels` | Constante, tipo e rótulo seguem a convenção. |
| `tests/test_vhdl_style.py::test_vendor_code_and_quartus_ips_are_left_out` | `vendor/` e IPs do Quartus não são conferidos. |
| `tests/test_vhdl_style.py::test_paths_yaml_can_leave_out_more_files` | Os globs do `paths.yaml` ficam de fora. |
| `tests/test_vhdl_style.py::test_literals_and_comments_do_not_count_as_code` | Palavra-chave em texto, caractere ou comentário é ignorada. |
| `tests/test_vhdl_style.py::test_an_unknown_rule_is_an_error` | Regra inexistente levanta erro. |
| `tests/test_vhdl_style.py::test_cmd_check_vhdl_style_exit_status` | O comando imprime OK, ou sai com 1 listando, ou com 2. |
| `tests/test_vhdl_style.py::test_the_subcommand_is_registered_without_a_config` | O subcomando roda sem `--config`. |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
