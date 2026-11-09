"""Rule library_900: only two packages of the IEEE library."""

from typing import override

from capstone_rule import LocalRule, VhdlFile, scan

ALLOWED = frozenset({"std_logic_1164", "numeric_std"})


class rule_library_900(LocalRule):
    """Allow only `std_logic_1164` and `numeric_std` from IEEE.

    The packages `std_logic_arith`, `std_logic_unsigned` and
    `std_logic_signed` are not part of the standard (CONTRIBUTING,
    section 1).
    """

    group = "library"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each `use ieee.<package>` of another package.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each package not allowed.
        """
        found: list[tuple[int, str]] = []
        in_ieee = False
        for tok in scan(vhdl_file):
            if tok.kind == "use_clause.library_name":
                in_ieee = tok.value == "ieee"
            elif tok.kind == "use_clause.package_name" and in_ieee:
                if tok.value not in ALLOWED:
                    found.append(
                        (
                            tok.line,
                            f"O pacote ieee.{tok.value} não é permitido; "
                            "use só std_logic_1164 e numeric_std "
                            "(CONTRIBUTING, seção 1)",
                        )
                    )
                in_ieee = False
        return found
