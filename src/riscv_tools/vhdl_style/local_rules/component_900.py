"""Rule component_900: no `component`, only direct instantiation."""

from pathlib import Path
from typing import override

import yaml
from capstone_rule import LocalRule, Tok, VhdlFile, is_code, scan

_INSTANCE_KEYWORD = "instantiated_unit.component_keyword"
_INSTANCE_NAME = "instantiated_unit.component_name"
_NAME_OF = {
    "component_declaration.component_keyword": (
        "component_declaration.identifier"
    ),
    _INSTANCE_KEYWORD: _INSTANCE_NAME,
}
_LIBRARY_KINDS = frozenset(
    {"logical_name_list.logical_name", "use_clause.library_name"}
)
VENDOR_PRIMITIVES = (
    Path(__file__).resolve().parent.parent / "vendor_primitives.yaml"
)
_MESSAGE = (
    "Não use `component`; instancie a entidade direto, "
    "`u_x : entity work.x` (CONTRIBUTING, seção 1)"
)


def _vendor_libraries() -> dict[str, str]:
    """Read the vendor primitives that `component` may name.

    Returns
    -------
    dict of str to str
        The library of each primitive, keyed by its lower-case name.
    """
    data = yaml.safe_load(VENDOR_PRIMITIVES.read_text("utf-8"))
    return {
        str(item["name"]).lower(): str(item["library"]).lower()
        for item in data["primitives"]
    }


def _use_at(code: list[Tok], index: int) -> tuple[int, str] | None:
    """Give the component a code token refers to, when it opens a use.

    Parameters
    ----------
    code : list of Tok
        The code tokens of the file.
    index : int
        The position of the token.

    Returns
    -------
    tuple of int and str or None
        The line and the lower-case name, or None when the token does
        not open a declaration or an instance.
    """
    tok = code[index]
    if tok.kind in _NAME_OF:
        wanted = _NAME_OF[tok.kind]
        name = next((n.value for n in code[index:] if n.kind == wanted), "")
        return (tok.line, name)
    if tok.kind == _INSTANCE_NAME and code[index - 1].kind != (
        _INSTANCE_KEYWORD
    ):
        return (tok.line, tok.value)
    return None


def _uses(tokens: list[Tok]) -> list[tuple[int, str]]:
    """List each `component` use of the file with the name it refers to.

    Parameters
    ----------
    tokens : list of Tok
        The tokens of the file.

    Returns
    -------
    list of tuple of int and str
        The line and the lower-case component name of each declaration
        or instance.
    """
    code = [tok for tok in tokens if is_code(tok)]
    found = (_use_at(code, index) for index in range(len(code)))
    return [use for use in found if use is not None]


class rule_component_900(LocalRule):
    """Forbid `component`: the instance is `u_x : entity work.x`.

    The rule has no exception for generated IP (PLLs), which the
    repository leaves out of the check in `paths.yaml`. The only
    exception is a vendor primitive listed in `vendor_primitives.yaml`
    (`altsyncram`, `sld_virtual_jtag`), which the Quartus Lite exposes
    only as a component of `altera_mf_components`, and only in a file
    that makes the library of the primitive visible. The rule reports
    the instance written with the name of a component and no `entity`
    (`u_x : name port map`) when the name is not in the list; the
    instance of an entity never has that form.
    """

    group = "component"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each component declaration and instance not allowed.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each use of `component`.
        """
        tokens = scan(vhdl_file)
        visible = {tok.value for tok in tokens if tok.kind in _LIBRARY_KINDS}
        vendor = _vendor_libraries()
        lines = sorted(
            {
                line
                for line, name in _uses(tokens)
                if vendor.get(name) not in visible
            }
        )
        return [(line, _MESSAGE) for line in lines]
