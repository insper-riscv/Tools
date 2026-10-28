# `profiles`

Lists every valid core profile of a specification. A profile is a set of optional extensions on top of the base ISA, and writing the list by hand lets an impossible combination slip in: M together with Zmmul, or a core with neither Zicsr nor Zicclsm. The specification declares the extensions and the rules between them, and this module generates the combinations that obey every rule.

## Specification

No `config.yaml` section: a YAML file is passed with `--spec`.

```yaml
base: rv32i                       # name of the profile with no extension
extensions:                       # the order is the order of the name's tokens
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:               # at most one extension of each group
  - [M, Zmmul]
requires_any:                     # at least one extension of each group
  - [Zicsr, Zicclsm]
```

| Extension field | Effect |
| :--- | :--- |
| `generic` | Name of the core generic that turns the extension on |
| `base_letter` | Letter that goes into the base name (`rv32i` with `m` becomes `rv32im`) |
| `absent_token` | The extension is on by default: its name stays out of the profile name while it is present, and the token is added when it is missing |

An extension with neither `base_letter` nor `absent_token` adds `_<name in lowercase>` to the profile name. A rule that names an extension that is not listed, or a repeated name, fails when the specification is read.

## Usage

```bash
uv run riscv-tools profiles --spec profiles/matrix.yaml                    # one name per line
uv run riscv-tools profiles --spec profiles/matrix.yaml --format generics  # name and GHDL -g flags
uv run riscv-tools profiles --spec profiles/matrix.yaml --format json      # name, extensions and generics
```

Profiles come out ordered by their number of extensions and, on a tie, by the order of the extensions in the specification.

## Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_profiles.py::test_core_spec_has_eighteen_profiles` | Twelve profiles with Zicclsm and six without it, all with distinct names |
| `tests/test_profiles.py::test_no_profile_breaks_a_rule` | No profile has M and Zmmul together, or lacks both Zicsr and Zicclsm |
| `tests/test_profiles.py::test_names_keep_the_twelve_profiles_and_mark_a_missing_zicclsm` | The names of the twelve original profiles stay, and a missing Zicclsm becomes `nozicclsm` |
| `tests/test_profiles.py::test_generics_follow_the_extensions` | Each generic is `true` only when the extension is in the profile |
| `tests/test_profiles.py::test_cli_prints_ghdl_generics` | The `generics` output has one line per profile with the `-g` flags |
