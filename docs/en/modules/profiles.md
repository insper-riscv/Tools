# `profiles`

Lists every valid core profile of a specification. A profile is a set of optional extensions on top of the base ISA, and writing the list by hand lets an impossible combination slip in: M together with Zmmul, or a performance counter (Zihpm) without the CSRs (Zicsr). The specification declares the extensions and the rules between them, and this module generates the combinations that obey every rule.

## Specification

No `config.yaml` section: a YAML file is passed with `--spec`. Two formats declare the same profiles. The letter format gives the base no letter and declares I and E as extensions.

```yaml
base: rv32                        # name of the profile with no letter
extensions:                       # the order is the order of the name's tokens
  - {name: I,        base_letter: i}
  - {name: E,        generic: has_e, base_letter: e}
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:               # at most one extension of each group
  - [I, E]
  - [M, Zmmul]
requires_any:                     # at least one extension of each group
  - [I, E]
```

The base list format puts the register file in the generics of each base.

```yaml
bases:                            # name of the profile with no extension
  - {name: rv32i, generics: {has_e: false}}
  - {name: rv32e, generics: {has_e: true}}
extensions:
  - {name: Zicsr,    generic: has_zicsr}
  - {name: M,        generic: has_m, base_letter: m}
```

Both formats name the same profiles (`rv32i`, `rv32im`, `rv32e`, `rv32em_zicsr`, ...) and give each the same generics.

| Extension field | Effect |
| :--- | :--- |
| `generic` | Name of the core generic that turns the extension on; optional when the extension has a `base_letter` |
| `base_letter` | Letter that goes into the base name (`rv32` with `i` becomes `rv32i`, and with `m` after it `rv32im`) |
| `absent_token` | The extension is on by default: its name stays out of the profile name while it is present, and the token is added when it is missing |
| `implies` | Generics that the extension also turns on |

The letters of the name follow the order of the extensions. Each base is combined with every valid set of extensions, and the generics of the base go into the profile before those of the extensions. A specification with a single base may write `base: rv32i` instead of `bases`. The profiles come base by base, in the order of the specification.

An extension with neither `base_letter` nor `absent_token` adds `_<name in lowercase>` to the profile name. A rule that names an extension that is not listed, a repeated name, or an extension with neither `generic` nor `base_letter` fails when the specification is read. A name that the rules leave out, such as `rv32` when `requires_any` demands I or E, is not a profile.

## Usage

```bash
uv run riscv-tools profiles --spec profiles/matrix.yaml                    # one name per line
uv run riscv-tools profiles --spec profiles/matrix.yaml --format generics  # name and GHDL -g flags
uv run riscv-tools profiles --spec profiles/matrix.yaml --format json      # name, extensions and generics
```

Within each base, profiles come out ordered by their number of extensions and, on a tie, by the order of the extensions in the specification.

## Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_profiles.py::test_core_spec_has_thirty_six_profiles` | A base with six extensions gives thirty-six profiles with distinct names |
| `tests/test_profiles.py::test_no_profile_breaks_a_rule` | No profile has M and Zmmul together, or Zicsr and Zicntr |
| `tests/test_profiles.py::test_zicntr_turns_zicsr_on` | Zicntr turns the Zicsr generic on without citing it in the name |
| `tests/test_profiles.py::test_an_absent_token_still_marks_a_missing_extension` | A missing extension with `absent_token` adds its token to the name |
| `tests/test_profiles.py::test_two_bases_give_a_hundred_and_twenty_profiles` | Two bases take sixty combinations each, all with distinct names |
| `tests/test_profiles.py::test_the_rv32e_names_follow_the_rv32i_names` | Only the base name changes from `rv32i` to `rv32e` |
| `tests/test_profiles.py::test_the_profiles_come_base_by_base` | The profiles of the first base come before those of the second |
| `tests/test_profiles.py::test_base_and_bases_together_fail` | A specification gives `base` or `bases`, not both |
| `tests/test_profiles.py::test_a_repeated_base_fails` | A repeated base name fails |
| `tests/test_profiles.py::test_the_letter_format_gives_the_names_of_the_bases_format` | The letter format gives the same 120 names and generics as the base list format |
| `tests/test_profiles.py::test_the_letter_format_prints_the_same_generics_lines` | The `generics` output carries the same flags in both formats |
| `tests/test_profiles.py::test_the_letter_format_prints_the_same_json_names` | The `json` output lists the same names and generics in both formats |
| `tests/test_profiles.py::test_every_letter_profile_has_exactly_one_of_i_and_e` | Each profile has exactly one of I and E, and `has_e` follows E |
| `tests/test_profiles.py::test_without_the_requirement_a_profile_may_lack_both_letters` | Without `requires_any` the profile `rv32` with neither letter exists |
| `tests/test_profiles.py::test_without_the_exclusion_a_profile_may_have_both_letters` | Without the exclusion the profile `rv32ie` with both letters exists |
| `tests/test_profiles.py::test_an_extension_with_a_letter_may_omit_the_generic` | The extension I adds no generic to the profile |
| `tests/test_profiles.py::test_an_extension_without_generic_or_letter_fails` | An extension with neither `generic` nor `base_letter` fails |
| `tests/test_config_from_platform.py::test_the_letter_format_picks_the_base_and_has_e` | The base letter and `HAS_E` follow the letter of the name in the letter format |
| `tests/test_config_from_platform.py::test_the_letter_format_rejects_a_name_with_no_letter` | A name with neither `i` nor `e` is not a profile |
