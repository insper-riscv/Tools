# Contribution Guide

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

This document defines the mandatory coding, structural organization, documentation, and verification rules for any contribution to the `Tools` repository.

## 1. Python Standards

The code follows [PEP 8](https://peps.python.org/pep-0008) (style) and [PEP 257](https://peps.python.org/pep-0257) (docstrings); `ruff` checks both (rules `E`, `W`, `N`, and `D`).

### 1.1. Code Style (PEP 8)

> **Deviation from PEP 8.** PEP 8 asks for comments in English, and this project writes them in **Portuguese**. Every other PEP 8 recommendation on comments still applies, namely complete sentences, kept up to date, and never restating what the code already says. Identifiers stay in English.

| Rule | Specification |
| :--- | :--- |
| Indentation | 4 spaces per level; tabs prohibited |
| Encoding | UTF-8, with no encoding declaration in the file |
| Line length | At most 79 characters for code; 72 for docstrings and comments; limits set in `pyproject.toml` |
| Naming | `snake_case` for functions, methods, variables, and modules; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants; `_` prefix for internal names |
| Imports | At the top of the file, one per line, in three groups separated by a blank line (standard library, third party, project), each group sorted alphabetically; absolute imports only (relative imports prohibited); `import *` prohibited |
| Blank lines | Two between module-level definitions; one between methods |
| Whitespace | One space around operators and after commas; none before a call's `(`, inside brackets, or at the end of a line |
| Comparisons | `is` and `is not` for `None`; `if seq:` instead of `if len(seq):`; never `== True` or `== False` |
| Exceptions | `except` always names the specific exception; bare `except:` prohibited |
| Comments | **In Portuguese** (deviation from PEP 8); complete sentences, capitalized, on their own line or after two spaces at the end of code, starting with `# `; they explain why, not what the code does |
| Language | Identifiers in **English**; comments in **Portuguese** |

### 1.2. Docstrings (PEP 257)

| Rule | Specification |
| :--- | :--- |
| Scope | Every public module, class, function, and method has a docstring |
| Delimiter | Triple double quotes (`"""`), including one-line docstrings |
| Summary | First line on the same line as the opening quotes, in the imperative mood, ending with a period |
| One-line docstring | Closing quotes on the same line, no blank line before or after the text |
| Multi-line docstring | Summary, blank line, detailed description; closing quotes alone on the last line |
| Classes | Docstring on the class, not on `__init__`; blank line after the docstring |
| Sections | NumPy style (`Parameters`, `Returns`, `Raises`, `Examples`), with the type repeating the annotation |
| Language | Portuguese |

```python
def fetch_user(user_id: str, include_roles: bool = False) -> User:
    """Busca um usuário pelo identificador.

    Parameters
    ----------
    user_id : str
        Identificador único do usuário.
    include_roles : bool, optional
        Inclui a lista de papéis na resposta, por padrão False.

    Returns
    -------
    User
        Dados do usuário.
    """
```

### 1.3. Tooling and Process

| Rule | Specification |
| :--- | :--- |
| Package manager | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install`, and `python -m pip` are prohibited |
| Tests | `pytest`; every new behavior comes with a test |
| Typing | Complete annotations, checked by Pyright and Pyrefly, both in `strict` mode |
| Style and quality | `ruff` for lint and formatting; `pylint` with a minimum score of 10; `deptry` for declared and used dependencies |
| Complexity and duplication | `complexipy` with a maximum of 10 per function; `codeclone` for duplicated code |
| Security | `semgrep` for static analysis; `uv audit` for dependency vulnerabilities |

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

Any change to code, configuration, or documentation must pass all commands below without errors before submission. Suppressions (`# noqa`, `# type: ignore`, `# nosec`) are prohibited; fix the root cause.

```bash
uv run ruff check .                  # Linting and style
uv run ruff format . --check         # Formatting
uvx pycodestyle --max-line-length=79 --max-doc-length=72 --ignore=E203,W503 src tests  # PEP 8 style (E203 and W503 contradict PEP 8 itself)
uvx pydocstyle --convention=pep257 src tests  # PEP 257 docstrings
uv run pylint .                      # Static analysis, minimum score 10
uv run pyright                       # Strict type checking
uvx pyrefly check                    # Second strict type checker
uv run deptry .                      # Declared and used dependencies
uvx complexipy .                     # Cognitive complexity of at most 10 per function
uvx codeclone . --fail-on-new        # New duplicated code
uvx semgrep scan --config p/python --error .  # Security analysis
uv audit                             # Dependency vulnerabilities
uv run pytest                        # Test suite
```

When adding, renaming, or removing any versioned file, immediately update:
- `docs/pt-br/` e `docs/en/`
- `README.md`, `README.en.md`, and the affected documentation

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](LICENSE).
