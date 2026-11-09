"""Rule component_900: no `component`, only direct instantiation."""

from typing import override

from capstone_rule import LocalRule, VhdlFile, scan

_KINDS = frozenset(
    {
        "component_declaration.component_keyword",
        "instantiated_unit.component_keyword",
        "instantiated_unit.component_name",
    }
)


class rule_component_900(LocalRule):
    """Forbid `component`: the instance is `u_x : entity work.x`.

    The rule has no exception, so it also reports the wrappers of
    megafunctions and PLLs that Quartus generates. It reports the
    instance written with the name of a component and no `entity`
    (`u_x : name port map`), which is how the megafunctions of the
    `altera_mf_components` package are used; the instance of an entity
    never has that form.
    """

    group = "component"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each component declaration and instance.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each use of `component`.
        """
        lines = sorted(
            {tok.line for tok in scan(vhdl_file) if tok.kind in _KINDS}
        )
        return [
            (
                line,
                "Não use `component`; instancie a entidade direto, "
                "`u_x : entity work.x` (CONTRIBUTING, seção 1)",
            )
            for line in lines
        ]
