# Contribution Guide

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

This document defines the mandatory coding, structural organization, documentation, and verification rules for any contribution to the `Tools` repository.

## 1. C Standard (C23)

All C code in the project (test programs, runtime, and fixtures) is written under the **ISO/IEC 9899:2024 (C23)** standard and compiled with `-std=c23`, never with `-std=gnu23` or compiler extensions that bypass the standard.

| Rule | Specification |
| :--- | :--- |
| Language standard | C23 (`-std=c23`) across all `.c` and `.h` files |
| Warnings | `-Wall -Wextra -Wpedantic -Werror`; no warning is accepted |
| Fixed-width types | `<stdint.h>` (`uint32_t`, `int32_t`) instead of `int`/`long` when width matters |
| C23 keywords | Use `bool`, `true`, `false`, `nullptr`, `constexpr`, `static_assert` without a message, and `typeof`; do not include `<stdbool.h>` or define a custom `NULL` |
| Attributes | Use the standard `[[nodiscard]]`, `[[maybe_unused]]`, and `[[noreturn]]` syntax instead of `__attribute__` |
| Constants | `constexpr` or `enum` instead of numeric `#define` macros; binary literals (`0b1010`) and digit separators (`1'000'000`) are allowed |
| Freestanding environment | Bare-metal code compiled with `-ffreestanding` depends only on the headers guaranteed by the standard and on the runtime libc |
| Naming | Identifiers in **English** with `snake_case`, constants and macros in `UPPER_SNAKE_CASE`, types with the `_t` suffix; comments in **Portuguese** |
| Comments | Every function and global variable has a descriptive comment in Portuguese immediately above its declaration |

The reference standard is [ISO/IEC 9899:2024](https://www.iso.org/standard/82075.html). In academic work, cite it with the BibTeX entry below:

```bibtex
@misc{iso9899,
  title        = {Information technology, Programming languages, C},
  author       = {{ISO/IEC}},
  year         = {2024},
  note         = {ISO/IEC 9899:2024 (C23)},
  howpublished = {\url{https://www.iso.org/standard/82075.html}}
}
```

## 2. Python Standards

| Rule | Specification |
| :--- | :--- |
| Package manager | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install`, and `python -m pip` are prohibited |
| Tests | `pytest`; every new behavior comes with a test |
| Code documentation | NumPy-style docstrings on public modules, classes, and functions |
| Typing | Complete annotations, checked by Pyright in `strict` mode |
| Style and quality | `ruff` for lint and formatting; `deptry` for declared and used dependencies |
| Naming | Identifiers in **English** with `snake_case`; comments and docstrings in **Portuguese** |

## 3. Markdown Documentation Rules

Every `README`, `CONTRIBUTING`, and `AUTHORS` maintains mirrored versions in Portuguese (`*.md`) and English (`*.en.md`), following these rules:

1. **Language switcher and license footer:** every `README.md` and `README.en.md` includes the `🌐 [Português](...) · [English](...)` switcher at the top, and every `.md` file ends with the copyright footer linking to `LICENSE`.
2. **Numbered progressive sections:** all sections starting at `##` must be numbered (`## 1.`, `### 1.1.`, `## 2.`) in a logical reading order.
3. **Direct punctuation:**
   - **Em-dashes are prohibited** in prose and tables; use commas, parentheses, semicolons, or colons according to the actual syntactic relationship.
   - **Chained colons are prohibited** (more than one `:` in the same sentence or table cell).
4. **Behavior explanation:** never cite an internal file, module, or signal name as if the name itself explained what the system does; always describe the operation performed.
5. **Non-redundant tables and LaTeX:** structured data belongs in Markdown tables and mathematical/boolean equations in LaTeX blocks (`$$ ... $$` or `$ ... $`), without repeating in prose what the table or equation already states.
6. **No changelog or open TODOs in technical docs:** architecture and contract documents describe exclusively the current state, without historical bugfix notes or unimplemented work lists.
7. **Usage guides only instruct:** installation and run instructions say how to do it, without justifying the choice of method.

## 4. Mandatory Verification Before Opening a Pull Request

Any change to code, configuration, or documentation must pass all commands below without errors before submission:

```bash
uv run ruff check .  # Linting and style
uv run pyright       # Strict type checking
uv run deptry .      # Declared and used dependencies
uv run pytest        # Test suite
```

When adding, renaming, or removing any versioned file, immediately update:
- `docs/pt-br/` e `docs/en/`
- `README.md`, `README.en.md`, and the affected documentation

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](LICENSE).
