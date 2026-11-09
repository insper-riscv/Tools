"""Rule process_900: the label of every process starts with `p_`."""

from typing import override

from capstone_rule import LocalRule, VhdlFile, scan

PREFIX = "p_"
_KINDS = frozenset(
    {"process_statement.process_label", "process_statement.end_process_label"}
)


class rule_process_900(LocalRule):
    """Require the label of each process to start with `p_`.

    The `process_600` of the VSG only accepts a suffix, so it cannot
    express the prefix of the project (CONTRIBUTING, section 3). A
    process with no label is reported by `process_016`, not here.
    """

    group = "process"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each process label that does not start with `p_`.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each label not allowed.
        """
        return [
            (
                tok.line,
                f"O rótulo de processo `{tok.value}` deve começar com "
                f"`{PREFIX}` (CONTRIBUTING, seção 3)",
            )
            for tok in scan(vhdl_file)
            if tok.kind in _KINDS and not tok.value.startswith(PREFIX)
        ]
