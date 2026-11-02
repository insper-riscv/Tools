# `profiles`

Lista todos os perfis válidos de um core a partir de uma especificação. Um perfil é um conjunto de extensões opcionais sobre a ISA base, e escrever a lista à mão deixa passar uma combinação impossível: M junto com Zmmul, ou um core sem Zicsr e sem Zicclsm. A especificação declara as extensões e as regras entre elas, e este módulo gera as combinações que obedecem a todas.

## Especificação

Sem seção no `config.yaml`: um arquivo YAML é passado com `--spec`.

```yaml
bases:                            # nome do perfil sem nenhuma extensão
  - {name: rv32i, generics: {num_regs: 32}}
  - {name: rv32e, generics: {num_regs: 16}}
extensions:                       # a ordem é a ordem dos tokens do nome
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:               # no máximo uma extensão de cada grupo
  - [M, Zmmul]
requires_any:                     # pelo menos uma extensão de cada grupo
  - [Zicsr, Zicclsm]
```

| Campo da extensão | Efeito |
| :--- | :--- |
| `generic` | Nome do generic do core que liga a extensão |
| `base_letter` | Letra que entra no nome da base (`rv32i` com `m` vira `rv32im`) |
| `absent_token` | A extensão vale por padrão: o nome dela não aparece enquanto ela está presente, e o token entra quando ela falta |

Cada base se combina com todos os conjuntos válidos de extensões, e os generics da base entram no perfil antes dos das extensões. Uma especificação de uma base só pode escrever `base: rv32i` no lugar de `bases`. Os perfis saem base por base, na ordem da especificação.

Uma extensão sem `base_letter` nem `absent_token` acrescenta `_<nome em minúsculas>` ao nome do perfil. Uma regra que cita uma extensão que não está na lista, ou um nome repetido, falha ao ler a especificação.

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
| `tests/test_profiles.py::test_core_spec_has_eighteen_profiles` | Doze perfis com Zicclsm e seis sem ele, todos com nomes distintos |
| `tests/test_profiles.py::test_no_profile_breaks_a_rule` | Nenhum perfil tem M e Zmmul juntos, nem fica sem Zicsr e sem Zicclsm |
| `tests/test_profiles.py::test_names_keep_the_twelve_profiles_and_mark_a_missing_zicclsm` | Os nomes dos doze perfis originais se mantêm e a falta do Zicclsm vira `nozicclsm` |
| `tests/test_profiles.py::test_generics_follow_the_extensions` | Cada generic recebe `true` só quando a extensão está no perfil |
| `tests/test_profiles.py::test_cli_prints_ghdl_generics` | A saída `generics` traz uma linha por perfil com as flags `-g` |
| `tests/test_profiles.py::test_two_bases_give_a_hundred_and_twenty_profiles` | Duas bases tomam sessenta combinações cada, todas com nomes distintos |
| `tests/test_profiles.py::test_the_rv32e_names_follow_the_rv32i_names` | Só o nome da base muda de `rv32i` para `rv32e` |
| `tests/test_profiles.py::test_the_base_sets_num_regs` | O generic da base vem primeiro no perfil |
| `tests/test_profiles.py::test_the_profiles_come_base_by_base` | Os perfis da primeira base vêm antes dos da segunda |
| `tests/test_profiles.py::test_cli_prints_the_register_count_flag` | A saída `generics` traz `-gnum_regs` com o número |
| `tests/test_profiles.py::test_base_and_bases_together_fail` | Uma especificação dá `base` ou `bases`, nunca os dois |
| `tests/test_profiles.py::test_a_repeated_base_fails` | Um nome de base repetido falha |
