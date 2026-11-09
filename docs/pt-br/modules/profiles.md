# `profiles`

Lista todos os perfis válidos de um core a partir de uma especificação. Um perfil é um conjunto de extensões opcionais sobre a ISA base, e escrever a lista à mão deixa passar uma combinação impossível: M junto com Zmmul, ou um contador de desempenho (Zihpm) sem os CSRs (Zicsr). A especificação declara as extensões e as regras entre elas, e este módulo gera as combinações que obedecem a todas.

## Especificação

Sem seção no `config.yaml`: um arquivo YAML é passado com `--spec`. Dois formatos declaram os mesmos perfis. O formato com letra dá à base nenhuma letra e declara I e E como extensões.

```yaml
base: rv32                        # nome do perfil sem nenhuma letra
extensions:                       # a ordem é a ordem dos tokens do nome
  - {name: I,        base_letter: i}
  - {name: E,        generic: has_e, base_letter: e}
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:               # no máximo uma extensão de cada grupo
  - [I, E]
  - [M, Zmmul]
requires_any:                     # pelo menos uma extensão de cada grupo
  - [I, E]
```

O formato com lista de bases põe o banco de registradores nos generics de cada base.

```yaml
bases:                            # nome do perfil sem nenhuma extensão
  - {name: rv32i, generics: {has_e: false}}
  - {name: rv32e, generics: {has_e: true}}
extensions:
  - {name: Zicsr,    generic: has_zicsr}
  - {name: M,        generic: has_m, base_letter: m}
```

Os dois formatos dão os mesmos nomes de perfil (`rv32i`, `rv32im`, `rv32e`, `rv32em_zicsr`, ...) e os mesmos generics para cada um.

| Campo da extensão | Efeito |
| :--- | :--- |
| `generic` | Nome do generic do core que liga a extensão; opcional quando a extensão tem `base_letter` |
| `base_letter` | Letra que entra no nome da base (`rv32` com `i` vira `rv32i`, e com `m` depois dela `rv32im`) |
| `absent_token` | A extensão vale por padrão: o nome dela não aparece enquanto ela está presente, e o token entra quando ela falta |
| `implies` | Generics que a extensão também liga |

As letras do nome seguem a ordem das extensões. Cada base se combina com todos os conjuntos válidos de extensões, e os generics da base entram no perfil antes dos das extensões. Uma especificação de uma base só pode escrever `base: rv32i` no lugar de `bases`. Os perfis saem base por base, na ordem da especificação.

Uma extensão sem `base_letter` nem `absent_token` acrescenta `_<nome em minúsculas>` ao nome do perfil. Uma regra que cita uma extensão que não está na lista, um nome repetido ou uma extensão sem `generic` nem `base_letter` falha ao ler a especificação. Um nome que as regras excluem, como `rv32` quando `requires_any` exige I ou E, não é um perfil.

## Uso

```bash
uv run riscv-tools profiles --spec profiles/matrix.yaml                    # um nome por linha
uv run riscv-tools profiles --spec profiles/matrix.yaml --format generics  # nome e flags -g do GHDL
uv run riscv-tools profiles --spec profiles/matrix.yaml --format json      # nome, extensões e generics
```

Dentro de cada base, os perfis saem ordenados pelo número de extensões e, em empate, pela ordem delas na especificação.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_profiles.py::test_core_spec_has_thirty_six_profiles` | Uma base com seis extensões dá trinta e seis perfis com nomes distintos |
| `tests/test_profiles.py::test_no_profile_breaks_a_rule` | Nenhum perfil tem M e Zmmul juntos, nem Zicsr e Zicntr |
| `tests/test_profiles.py::test_zicntr_turns_zicsr_on` | O Zicntr liga o generic do Zicsr sem citá-lo no nome |
| `tests/test_profiles.py::test_an_absent_token_still_marks_a_missing_extension` | Uma extensão ausente com `absent_token` acrescenta o token ao nome |
| `tests/test_profiles.py::test_two_bases_give_a_hundred_and_twenty_profiles` | Duas bases tomam sessenta combinações cada, todas com nomes distintos |
| `tests/test_profiles.py::test_the_rv32e_names_follow_the_rv32i_names` | Só o nome da base muda de `rv32i` para `rv32e` |
| `tests/test_profiles.py::test_the_profiles_come_base_by_base` | Os perfis da primeira base vêm antes dos da segunda |
| `tests/test_profiles.py::test_base_and_bases_together_fail` | Uma especificação dá `base` ou `bases`, nunca os dois |
| `tests/test_profiles.py::test_a_repeated_base_fails` | Um nome de base repetido falha |
| `tests/test_profiles.py::test_the_letter_format_gives_the_names_of_the_bases_format` | O formato com letra dá os mesmos 120 nomes e generics do formato com lista de bases |
| `tests/test_profiles.py::test_the_letter_format_prints_the_same_generics_lines` | A saída `generics` traz as mesmas flags nos dois formatos |
| `tests/test_profiles.py::test_the_letter_format_prints_the_same_json_names` | A saída `json` lista os mesmos nomes e generics nos dois formatos |
| `tests/test_profiles.py::test_every_letter_profile_has_exactly_one_of_i_and_e` | Todo perfil tem exatamente um entre I e E, e `has_e` acompanha o E |
| `tests/test_profiles.py::test_without_the_requirement_a_profile_may_lack_both_letters` | Sem `requires_any` existe o perfil `rv32`, sem nenhuma das duas letras |
| `tests/test_profiles.py::test_without_the_exclusion_a_profile_may_have_both_letters` | Sem a exclusão existe o perfil `rv32ie`, com as duas letras |
| `tests/test_profiles.py::test_an_extension_with_a_letter_may_omit_the_generic` | A extensão I não acrescenta generic ao perfil |
| `tests/test_profiles.py::test_an_extension_without_generic_or_letter_fails` | Uma extensão sem `generic` nem `base_letter` falha |
| `tests/test_config_from_platform.py::test_the_letter_format_picks_the_base` | A letra da base acompanha a letra do nome no formato com letra |
| `tests/test_config_from_platform.py::test_the_letter_format_rejects_a_name_with_no_letter` | Um nome sem `i` nem `e` não é um perfil |
