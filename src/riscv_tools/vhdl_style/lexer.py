"""Strip comments and literals from VHDL text, keeping the line count.

The style rules look at code, so a keyword inside a comment or a string
must not count. `strip_code` blanks both and leaves every line where it
was, so an offset in the stripped text maps back to the same line of
the original file.
"""

import bisect
import re

_CHAR_LITERAL_BEFORE = re.compile(r"[\w)\]']")


def _blank_string(line: str, start: int) -> int:
    """Find where the string that opens at `start` ends.

    Parameters
    ----------
    line : str
        The line of code.
    start : int
        The index of the opening quote.

    Returns
    -------
    int
        The index just after the closing quote, or the line length for
        a string that never closes.
    """
    end = line.find('"', start + 1)
    return len(line) if end < 0 else end + 1


def _is_char_literal(line: str, index: int) -> bool:
    """Tell a character literal such as `'0'` from an attribute tick.

    Parameters
    ----------
    line : str
        The line of code.
    index : int
        The index of a single quote.

    Returns
    -------
    bool
        True when the quote opens a three character literal.
    """
    if index + 2 >= len(line) or line[index + 2] != "'":
        return False
    return index == 0 or not _CHAR_LITERAL_BEFORE.match(line[index - 1])


def _strip_line(line: str) -> str:
    """Remove the comment of a line and blank its literals.

    Parameters
    ----------
    line : str
        One line of VHDL.

    Returns
    -------
    str
        The line with the comment cut and each literal replaced by
        spaces of the same length.
    """
    out: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char == "-" and line.startswith("--", index):
            break
        if char == '"':
            end = _blank_string(line, index)
            out.append(" " * (end - index))
            index = end
        elif char == "'" and _is_char_literal(line, index):
            out.append("   ")
            index += 3
        else:
            out.append(char)
            index += 1
    return "".join(out)


def strip_code(lines: list[str]) -> list[str]:
    """Strip the comments and literals of every line.

    Parameters
    ----------
    lines : list of str
        The lines of a VHDL file.

    Returns
    -------
    list of str
        The code of each line, with the same number of lines.
    """
    return [_strip_line(line) for line in lines]


class LineIndex:
    """Map an offset in the joined code back to its line number."""

    def __init__(self, code: list[str]) -> None:
        """Index the line starts of the joined code.

        Parameters
        ----------
        code : list of str
            The stripped lines.
        """
        self.text = "\n".join(code)
        self._starts = [0]
        for line in code[:-1]:
            self._starts.append(self._starts[-1] + len(line) + 1)

    def line_of(self, offset: int) -> int:
        """Return the 1-based line that holds an offset.

        Parameters
        ----------
        offset : int
            An index into `text`.

        Returns
        -------
        int
            The line number, counting from 1.
        """
        return bisect.bisect_right(self._starts, offset)
