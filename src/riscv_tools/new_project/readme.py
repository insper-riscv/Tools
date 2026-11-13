"""The README written into the folder of a new project."""

from pathlib import Path

README_FILE = "README.md"

_PT = """\
# {title}

Projeto criado por `riscv-tools new-project`.

| Campo | Valor |
| :--- | :--- |
| Identificador | `{slug}` |
| Placa | `{board}` |
| Plataforma | `{repo}/{platform}` |

Comandos, na pasta deste projeto: `./rt project doctor`,
`./rt project build`, `./rt project flash <arquivo>.mif` e
`./rt project help`.
"""

_EN = """\
# {title}

Project created by `riscv-tools new-project`.

| Field | Value |
| :--- | :--- |
| Identifier | `{slug}` |
| Board | `{board}` |
| Platform | `{repo}/{platform}` |

Commands, in the folder of this project: `./rt project doctor`,
`./rt project build`, `./rt project flash <file>.mif` and
`./rt project help`.
"""


def write_readme(
    project: Path,
    language: str,
    fields: dict[str, str],
) -> Path:
    """Write the README of a project, with its name as typed.

    The name is placed in a Markdown heading, so a character that
    Markdown reads as markup is escaped.

    Parameters
    ----------
    project : Path
        The project folder.
    language : str
        `pt` or `en`.
    fields : dict of {str: str}
        `title`, `slug`, `board`, `repo` and `platform`.

    Returns
    -------
    Path
        The file that was written.
    """
    safe = dict(fields)
    safe["title"] = fields["title"].replace("_", "\\_")
    path = project / README_FILE
    text = (_PT if language == "pt" else _EN).format(**safe)
    path.write_text(text, encoding="utf-8")
    return path
