"""Rule port_map_900: every association of a port map is by name."""

from typing import override

from capstone_rule import LocalRule, Tok, VhdlFile, is_code, scan

_MESSAGE = "Associe a porta pelo nome, `i_x => sinal` (CONTRIBUTING, seção 1)"


def _associations(tokens: list[Tok]) -> list[list[Tok]]:
    """Split the `port map` of the file into its associations.

    Parameters
    ----------
    tokens : list of Tok
        The tokens of the file.

    Returns
    -------
    list of list of Tok
        The code tokens of each association of each `port map`.
    """
    groups: list[list[Tok]] = []
    current: list[list[Tok]] | None = None
    for tok in tokens:
        if tok.kind == "port_map_aspect.open_parenthesis":
            current = [[]]
        elif current is None:
            continue
        elif tok.kind == "port_map_aspect.close_parenthesis":
            groups.extend(current)
            current = None
        elif tok.kind == "association_list.comma":
            current.append([])
        elif is_code(tok):
            current[-1].append(tok)
    return groups


class rule_port_map_900(LocalRule):
    """Require the `port map` associations to be by name.

    Each association is `i_porta => sinal`; the positional form
    `sinal` is forbidden (CONTRIBUTING, section 1).
    """

    group = "port_map"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each positional association of a `port map`.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each positional association.
        """
        return [
            (association[0].line, _MESSAGE)
            for association in _associations(scan(vhdl_file))
            if association
            and all(
                tok.kind != "association_element.assignment"
                for tok in association
            )
        ]
