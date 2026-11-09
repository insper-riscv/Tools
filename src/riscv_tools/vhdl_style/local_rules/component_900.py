"""Rule component_900: no `component`, only direct instantiation."""

from typing import override

from capstone_rule import LocalRule, VhdlFile, scan

_KINDS = frozenset(
    {
        "component_declaration.component_keyword",
        "instantiated_unit.component_keyword",
    }
)


class rule_component_900(LocalRule):
    """Forbid `component`: the instance is `u_x : entity work.x`.

    The rule has no exception, so it also reports the wrappers of
    megafunctions and PLLs that Quartus generates, as long as the file
    is in the list that `riscv-tools vhdl-files` gives.
    """

    group = "component"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each component declaration and component instance.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each use of `component`.
        """
        return [
            (
                tok.line,
                "Não use `component`; instancie a entidade direto, "
                "`u_x : entity work.x` (CONTRIBUTING, seção 1)",
            )
            for tok in scan(vhdl_file)
            if tok.kind in _KINDS
        ]
