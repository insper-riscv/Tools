# Contribution Guide

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

This document defines the mandatory coding, structural organization, documentation, and verification rules for any contribution to the `Tools` repository.

## 1. Python Standards

| Rule | Specification |
| :--- | :--- |
| Package manager | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install`, and `python -m pip` are prohibited |
| Tests | `pytest`; every new behavior comes with a test |
| Code documentation | NumPy-style docstrings on public modules, classes, and functions |
| Typing | Complete annotations, checked by Pyright in `strict` mode |
| Style and quality | `ruff` for lint and formatting; `deptry` for declared and used dependencies |
| Naming | Identifiers in **English** with `snake_case`; comments and docstrings in **Portuguese** |

## 2. Module Organization

Every module of the package (the table in `README.en.md` lists them all) owns exactly one job. When adding or
changing code:

- New functionality that doesn't fit an existing module's
  responsibility gets its **own new module**; don't bolt it onto the
  nearest unrelated one just because it's convenient to import from
  there.
- Logic needed by **two or more** modules gets factored into its own
  module (or a small private helper shared via an explicit import),
  not copy-pasted into each caller. Duplication between modules is how
  a fix applied to one copy silently leaves the other one broken, with
  nothing at either call site hinting that a second copy even exists.
- If you're unsure whether something is a new responsibility or fits
  an existing one, prefer the smaller, more specific module: merging
  two modules later is easy; un-tangling a module that grew several
  unrelated jobs is not.

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
