"""Rule header_900: the file opens with the header block."""

import re
from typing import override

from capstone_rule import LocalRule, VhdlFile

_BAR = re.compile(r"^--\s?=+\s*$")
_COMMENT = re.compile(r"^\s*--")


def _closes(lines: list[str]) -> bool:
    """Tell whether the comment block that follows is a header.

    Parameters
    ----------
    lines : list of str
        The lines after the opening bar.

    Returns
    -------
    bool
        True when a closing bar follows at least one line of text, with
        nothing but comments in between.
    """
    body = 0
    for line in lines:
        if _BAR.match(line):
            return body > 0
        if not _COMMENT.match(line):
            return False
        body += bool(line.strip().removeprefix("--").strip())
    return False


class rule_header_900(LocalRule):
    """Require the header block at the top of the file.

    The block is a line of `=`, the description in Portuguese and a
    closing line of `=`, of any width (CONTRIBUTING, section 4.1).
    """

    group = "header"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report a file whose first lines are not the header.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            One violation on line 1 when the header is missing.
        """
        lines = vhdl_file.get_lines()[1:]
        if lines and _BAR.match(lines[0]) and _closes(lines[1:]):
            return []
        return [
            (
                1,
                "O arquivo deve abrir com o cabeçalho: uma linha de `=`, "
                "a descrição em português e uma linha de `=` de "
                "fechamento (CONTRIBUTING, seção 4.1)",
            )
        ]
