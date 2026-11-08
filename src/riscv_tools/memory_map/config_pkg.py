"""Write the `config_pkg`, the VHDL package of constants of a platform.

The package is the single mirror, in VHDL, of what the platform YAML
chooses: the base ISA (`IS_64`, `IS_BASE_E`), the width of the
physical address (`ADDR_BITS`), one `HAS_*` constant for each
extension, cache and peripheral, the memory map in bytes and the checks
of the combination.
It is a package of constants, one file for each platform, because the
Quartus Lite refuses a generic package.

The unit has the name `config_pkg`, the same as the default package of
the Common-Components, so the generated file takes the place of the
default one in the list of sources (see `riscv_tools.sources`). It is
written next to the package of the map (`generate.vhdl`), which keeps
the constants that are not in it, under `generate.config_pkg`:

```yaml
generate:
  config_pkg:
    path: rtl/config_pkg.vhd
```

`riscv-tools generate-config-pkg` writes the package of a platform or
of a variant of it (`--set IS_64=true --set ADDR_BITS=40`), for the
formal proof and for the matrix of profiles of the Core.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from riscv_tools.memory_map import memory as memory_choice
from riscv_tools.memory_map.core import (
    address_bits,
    periph_id_shift,
    periph_window,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.problems import platform_problems
from riscv_tools.memory_map.profile import (
    RV32_XLEN,
    RV64_XLEN,
    SWITCHES,
    resolve,
)
from riscv_tools.memory_map.symbol_table import symbol_table

PACKAGE = "config_pkg"
XLEN_OF = {False: RV32_XLEN, True: RV64_XLEN}
REGISTER_BITS = {"i": 5, "e": 4}
NAME_WIDTH = 18
SLOT_COUNT = 8

# Constante do pacote de cada periférico e o nome dele em `peripherals`.
PERIPHERALS = {
    "HAS_UART": "UART",
    "HAS_UART_PINS": "UART_PINS",
    "HAS_UART_JTAG": "UART_JTAG",
    "HAS_TIMER": "TIMER",
    "HAS_GPIO": "GPIO",
    "HAS_DISPLAY": "DISPLAY",
    "HAS_SWITCHES": "SWITCHES",
    "HAS_KEYS": "KEYS",
    "HAS_CLINT": "CLINT",
    "HAS_PLIC": "PLIC",
    "HAS_FLASH_CTRL": "FLASH_CTRL",
}
# As extensões na ordem do texto da ISA: M, as Z alfabéticas, a S.
ISA_ORDER = (
    ("HAS_M", "m"),
    ("HAS_ZICCLSM", "_zicclsm"),
    ("HAS_ZICNTR", "_zicntr"),
    ("HAS_ZICOND", "_zicond"),
    ("HAS_ZICSR", "_zicsr"),
    ("HAS_ZIFENCEI", "_zifencei"),
    ("HAS_ZIHINTNTL", "_zihintntl"),
    ("HAS_ZIHINTPAUSE", "_zihintpause"),
    ("HAS_ZIHPM", "_zihpm"),
    ("HAS_ZIMOP", "_zimop"),
    ("HAS_ZMMUL", "_zmmul"),
    ("HAS_SSCOFPMF", "_sscofpmf"),
)
_HEADER = """\
-- =====================================================================
-- Pacote de configuração da plataforma
-- =====================================================================
-- Constantes da plataforma, geradas por `riscv-tools` a partir de
-- {source}.
-- Não edite à mão: mude o YAML da plataforma e gere de novo.{variant}
--
-- A unidade tem o nome do pacote padrão do Common-Components, e esta
-- versão ocupa o lugar dele na lista de fontes. Os limites do mapa
-- estão em bytes, no tipo map_addr_t, e as funções isa_string e
-- check_isa descrevem e conferem a combinação de extensões.
-- =====================================================================

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package {package} is

{declarations}
\t-- Texto da ISA da configuração, como rv32im_zicsr.
\tfunction isa_string return string;
\t-- Confere as dependências entre as constantes; falha na elaboração
\t-- se a combinação é inválida e devolve verdadeiro se é válida.
\tfunction check_isa return boolean;

end package {package};

package body {package} is

\tfunction isa_string return string is
\t\t-- Tamanho do espaço para montar o texto da ISA.
\t\tconstant ISA_STRING_MAX : natural := 160;
\t\t-- Texto montado, preenchido a partir da primeira posição.
\t\tvariable text : string(1 to ISA_STRING_MAX) := (others => ' ');
\t\t-- Quantidade de caracteres já escritos em text.
\t\tvariable used : natural := 0;
\t\t-- Acrescenta um trecho ao fim do texto.
\t\tprocedure add (piece : string) is
\t\tbegin
\t\t\tfor index in piece'range loop
\t\t\t\tused := used + 1;
\t\t\t\ttext(used) := piece(index);
\t\t\tend loop;
\t\tend procedure add;
\tbegin
\t\tif IS_64 then
\t\t\tadd("rv64");
\t\telse
\t\t\tadd("rv32");
\t\tend if;
\t\tif IS_BASE_E then
\t\t\tadd("e");
\t\telse
\t\t\tadd("i");
\t\tend if;
{isa_steps}\t\treturn text(1 to used);
\tend function isa_string;

\tfunction check_isa return boolean is
\tbegin
\t\tassert ADDR_BITS >= ADDR_BITS_MIN and ADDR_BITS <= ADDR_BITS_MAX
\t\t\treport "ADDR_BITS fora da faixa de 16 a 64"
\t\t\tseverity failure;
\t\tassert IS_64 or ADDR_BITS <= ADDR_BITS_MAX_RV32
\t\t\treport "ADDR_BITS acima de 32 exige IS_64"
\t\t\tseverity failure;
\t\tassert HAS_ZICSR or not HAS_ANY_COUNTER
\t\t\treport "Zicntr e Zihpm exigem Zicsr"
\t\t\tseverity failure;
\t\tassert HAS_ZICSR or not HAS_INTERRUPTS
\t\t\treport "Interrupts exige Zicsr"
\t\t\tseverity failure;
\t\tassert HAS_ZICSR or not HAS_ACCESS_FAULTS
\t\t\treport "AccessFaults exige Zicsr"
\t\t\tseverity failure;
\t\tassert HAS_SSCOF or not HAS_SSCOFPMF
\t\t\treport "Sscofpmf exige Zihpm e Interrupts"
\t\t\tseverity failure;
\t\tassert ROM_BASE < ROM_END
\t\t\treport "ROM_BASE deve ser menor que ROM_END"
\t\t\tseverity failure;
\t\tassert RAM_BASE < RAM_END
\t\t\treport "RAM_BASE deve ser menor que RAM_END"
\t\t\tseverity failure;
\t\tassert ROM_END <= RAM_BASE or RAM_END <= ROM_BASE
\t\t\treport "A ROM e a RAM se sobrepoem"
\t\t\tseverity failure;
\t\tassert ROM_END <= ADDR_SPACE_BYTES and RAM_END <= ADDR_SPACE_BYTES
\t\t\treport "A ROM ou a RAM passa de 2**ADDR_BITS bytes"
\t\t\tseverity failure;
\t\tassert ROM_END <= PERIPH_BASE and RAM_END <= PERIPH_BASE
\t\t\treport "A ROM ou a RAM passa da janela de perifericos"
\t\t\tseverity failure;
\t\treturn true;
\tend function check_isa;

end package body {package};
"""


@dataclass(frozen=True)
class Config:
    """The choices of one platform that the `config_pkg` mirrors.

    Parameters
    ----------
    is_64 : bool
        The base is RV64.
    is_base_e : bool
        The base is E (16 registers).
    address_bits : int
        The width of the physical address.
    flags : dict of {str: bool}
        Every `HAS_*` constant, in the order of the package: the
        extensions, the caches and the peripherals.
    rom_external : bool
        The ROM sits outside the chip.
    ram_external : bool
        The RAM sits outside the chip.
    boot_bits : int
        The exponent of the size of the BOOT_MEMORY.
    cache_window_bits : int
        The width of the window of the tag of the caches.
    addresses : dict of {str: int}
        `ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE` and
        `PERIPH_BASE`, in bytes.
    slots : int
        The mask of the peripheral windows that have a peripheral.
    """

    is_64: bool
    is_base_e: bool
    address_bits: int
    flags: dict[str, bool]
    rom_external: bool
    ram_external: bool
    boot_bits: int
    cache_window_bits: int
    addresses: dict[str, int]
    slots: int


def _override_value(item: str, name: str, text: str) -> bool | int:
    """Read the value of one `--set` pair.

    Parameters
    ----------
    item : str
        The pair as written, for the messages.
    name : str
        The constant, in upper case.
    text : str
        The value, in lower case.

    Returns
    -------
    bool or int
        An integer for `ADDR_BITS`, else a boolean.

    Raises
    ------
    ValueError
        If the value is not of the type of the constant.
    """
    if name == "ADDR_BITS":
        if not text.isdecimal():
            raise ValueError(f"--set {item!r}: an integer is needed")
        return int(text)
    if text not in ("true", "false"):
        raise ValueError(f"--set {item!r}: true or false is needed")
    return text == "true"


def parse_overrides(items: list[str]) -> dict[str, bool | int]:
    """Read the `--set NAME=VALUE` pairs of a variant.

    Parameters
    ----------
    items : list of str
        The pairs: `ADDR_BITS` takes an integer and every other name a
        boolean (`true` or `false`).

    Returns
    -------
    dict of {str: bool or int}
        The value of each name.

    Raises
    ------
    ValueError
        If a pair is malformed or a value is not of the type of its
        name.
    """
    found: dict[str, bool | int] = {}
    for item in items:
        name, sep, text = item.partition("=")
        name, text = name.strip().upper(), text.strip().lower()
        if not sep or not name:
            raise ValueError(f"--set {item!r} must be NAME=VALUE")
        found[name] = _override_value(item, name, text)
    return found


def _vhdl_spec(platform: dict[str, Any]) -> dict[str, Any]:
    """Read the `generate.vhdl` section, which names the ROM and RAM."""
    wanted = platform_dict(platform, "generate")
    return cast(dict[str, Any], wanted.get("vhdl") or {})


def _rom_ram(platform: dict[str, Any]) -> tuple[str, str]:
    """Find the regions that are the ROM and the RAM.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `generate.vhdl` or `config` names them.

    Returns
    -------
    tuple of (str, str)
        The name of the ROM region and of the RAM region.

    Raises
    ------
    ValueError
        If the platform names neither.
    """
    spec = _vhdl_spec(platform)
    config = platform_dict(platform, "config")
    rom = spec.get("rom") or config.get("rom")
    ram = spec.get("ram") or config.get("ram")
    if not rom or not ram:
        raise ValueError(
            "the config_pkg needs the ROM and the RAM: name them in "
            "`generate.vhdl` or `config` as `rom` and `ram`"
        )
    return str(rom), str(ram)


def _flags(
    platform: dict[str, Any], generics: dict[str, bool | int]
) -> dict[str, bool]:
    """Collect the `HAS_*` constants of the extensions and the rest.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}
        The generics of the profile.

    Returns
    -------
    dict of {str: bool}
        The extensions of `SWITCHES`, then `HAS_ICACHE` and
        `HAS_DCACHE`, then one constant for each name of `PERIPHERALS`.
        `HAS_UART_JTAG` and `HAS_UART_PINS` also follow `console` when
        the platform lists a `UART`.
    """
    choice = memory_choice.resolve(platform)
    names = {str(p["name"]) for p in platform_list(platform, "peripherals")}
    console = platform.get("console")
    flags = {key.upper(): bool(generics.get(key)) for key in SWITCHES}
    flags["HAS_ICACHE"] = choice is not None and choice.has_icache
    flags["HAS_DCACHE"] = choice is not None and choice.has_dcache
    flags |= {flag: name in names for flag, name in PERIPHERALS.items()}
    if "UART" in names:
        flags["HAS_UART_JTAG"] |= console == "jtag"
        flags["HAS_UART_PINS"] |= console == "pins"
    return flags


def _apply(
    flags: dict[str, bool], overrides: dict[str, bool | int]
) -> dict[str, bool]:
    """Replace the flags that a variant sets.

    Parameters
    ----------
    flags : dict of {str: bool}
        The flags of the platform.
    overrides : dict of {str: bool or int}
        The variant: `IS_64`, `IS_BASE_E` and `ADDR_BITS` are read by
        the caller, the other names must be flags.

    Returns
    -------
    dict of {str: bool}
        The flags with the variant applied.

    Raises
    ------
    ValueError
        If a name is neither a flag nor one of the three above.
    """
    own = {"IS_64", "IS_BASE_E", "ADDR_BITS"}
    unknown = sorted(set(overrides) - own - set(flags))
    if unknown:
        raise ValueError(
            f"--set {', '.join(unknown)}: not a constant of the "
            "config_pkg that a variant can change"
        )
    return flags | {
        key: bool(value) for key, value in overrides.items() if key in flags
    }


def _addresses(
    platform: dict[str, Any], table: dict[str, int]
) -> dict[str, int]:
    """Read the bases and ends of the memory map, in bytes.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    table : dict of {str: int}
        The symbols of the map.

    Returns
    -------
    dict of {str: int}
        `ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE` and
        `PERIPH_BASE`; the last two follow `generate.vhdl` when it fixes
        `ext_base` and `periph_base`, else the peripheral window.
    """
    rom, ram = _rom_ram(platform)
    spec = _vhdl_spec(platform)
    window = evaluate(spec.get("periph_base", periph_window(platform)))
    return {
        "ROM_BASE": table[f"{rom}.base"],
        "ROM_END": table[f"{rom}.end"],
        "RAM_BASE": table[f"{ram}.base"],
        "RAM_END": table[f"{ram}.end"],
        "EXT_BASE": evaluate(spec.get("ext_base", window)),
        "PERIPH_BASE": window,
    }


def _relocated(platform: dict[str, Any], bits: int) -> dict[str, Any]:
    """Give the platform another address width and move its peripherals.

    The bases of the peripherals follow the window of the width, so the
    variant of a platform keeps the convention V-A4 checks.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    bits : int
        The width of the physical address of the variant.

    Returns
    -------
    dict of {str: Any}
        A copy with `address_bits` and the bases of the peripherals
        replaced.

    Raises
    ------
    ValueError
        If `bits` is not an integer from 16 to 64.
    """
    moved = {**platform, "address_bits": bits}
    window = periph_window(moved)
    shift = periph_id_shift(address_bits(moved))
    moved["peripherals"] = [
        {**periph, "base": window | (int(periph["id"]) << shift)}
        for periph in platform_list(platform, "peripherals")
    ]
    return moved


def build_config(
    platform: dict[str, Any],
    platform_file: Path,
    overrides: dict[str, bool | int] | None = None,
) -> Config:
    """Read the choices of a platform, or of a variant of it.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_file : Path
        The platform YAML, which locates the profile specification.
    overrides : dict of {str: bool or int}, optional
        The variant (see `parse_overrides`), checked as a platform of
        its own: V-A1 to V-A6 hold for its `ADDR_BITS` and `IS_64`, and
        its peripherals move to the window of that width.

    Returns
    -------
    Config
        The choices.

    Raises
    ------
    ValueError
        If the variant names an unknown constant or the platform (with
        the variant applied) is inconsistent.
    """
    overrides = overrides or {}
    if "ADDR_BITS" in overrides:
        platform = _relocated(platform, int(overrides["ADDR_BITS"]))
    base, generics, xlen = resolve(platform, platform_file)
    generics = generics | {
        key: bool(overrides[key.upper()])
        for key in SWITCHES
        if key.upper() in overrides
    }
    xlen = (
        RV64_XLEN if overrides.get("IS_64", xlen == RV64_XLEN) else RV32_XLEN
    )
    problems = platform_problems(platform, generics, xlen)
    if problems:
        raise ValueError("; ".join(str(p) for p in problems))
    table = symbol_table(platform)
    flags = _apply(_flags(platform, generics), overrides)
    boot = platform_list(platform, "regions")[0]["name"]
    choice = memory_choice.resolve(platform)
    rom_external, ram_external = memory_choice.externals(
        _vhdl_spec(platform), choice
    )
    slots = 0
    for periph in platform_list(platform, "peripherals"):
        slots |= 1 << int(periph["id"])
    return Config(
        is_64=xlen == RV64_XLEN,
        is_base_e=bool(overrides.get("IS_BASE_E", base == "e")),
        address_bits=address_bits(platform),
        flags=flags,
        rom_external=bool(rom_external),
        ram_external=bool(ram_external),
        boot_bits=(table[f"{boot}.size"] - 1).bit_length(),
        cache_window_bits=memory_choice.cache_window_bits(platform),
        addresses=_addresses(platform, table),
        slots=slots,
    )


def _constant(name: str, kind: str, value: str, comment: str) -> str:
    """Write one commented constant."""
    return (
        f"\t-- {comment}\n"
        f"\tconstant {name:<{NAME_WIDTH}} : {kind} := {value};\n"
    )


def _boolean(name: str, value: bool | str, comment: str) -> str:
    """Write one commented boolean constant."""
    text = str(value).lower() if isinstance(value, bool) else value
    return _constant(name, "boolean", text, comment)


def _address(value: int, bits: int) -> str:
    """Write a byte address as a `map_addr_t` literal.

    Parameters
    ----------
    value : int
        The address in bytes, at most `2**bits`.
    bits : int
        The width of the physical address.

    Returns
    -------
    str
        The expression: a hexadecimal literal wide enough for `bits + 1`
        bits, resized to the length of `map_addr_t`.
    """
    digits = (bits + 4) // 4
    return f"resize(unsigned'(x\"{value:0{digits}X}\"), map_addr_t'length)"


def _base_block(config: Config) -> str:
    """Write the base ISA, the widths and the types of the package."""
    bits = config.address_bits
    xlen = XLEN_OF[config.is_64]
    base = "e" if config.is_base_e else "i"
    return (
        _boolean(
            "IS_64",
            config.is_64,
            "Base de 64 bits (RV64) quando verdadeiro, 32 bits (RV32) "
            "quando falso.",
        )
        + _boolean(
            "IS_BASE_E",
            config.is_base_e,
            "Base E (16 registradores) quando verdadeiro, base I (32) "
            "quando falso.",
        )
        + _constant(
            "ADDR_BITS",
            "natural",
            str(bits),
            "Largura do endereço físico em bits, de 16 a 64 (acima de 32 "
            "só com IS_64).",
        )
        + _constant(
            "ADDR_BITS_MIN",
            "natural",
            "16",
            "Menor largura de endereço físico aceita.",
        )
        + _constant(
            "ADDR_BITS_MAX",
            "natural",
            "64",
            "Maior largura de endereço físico aceita.",
        )
        + _constant(
            "ADDR_BITS_MAX_RV32",
            "natural",
            "32",
            "Maior largura de endereço físico aceita sem IS_64.",
        )
        + _constant(
            "XLEN",
            "natural",
            str(xlen),
            "Largura da palavra de dados, do PC lógico e dos registradores.",
        )
        + _constant(
            "NUM_REGS",
            "natural",
            "16" if base == "e" else "32",
            "Número de registradores de uso geral.",
        )
        + _constant(
            "REG_BITS",
            "natural",
            str(REGISTER_BITS[base]),
            "Bits do índice de registrador.",
        )
        + "\t-- Palavra de dados de XLEN bits.\n"
        "\tsubtype word_t is std_logic_vector((XLEN - 1) downto 0);\n"
        "\t-- Índice de registrador.\n"
        "\tsubtype reg_t is std_logic_vector((REG_BITS - 1) downto 0);\n"
        "\t-- Endereço físico de ADDR_BITS bits.\n"
        "\tsubtype addr_t is std_logic_vector((ADDR_BITS - 1) downto 0);\n"
        "\t-- Endereço de mapa com um bit a mais, para representar o fim "
        "exclusivo 2**ADDR_BITS.\n"
        "\tsubtype map_addr_t is unsigned(ADDR_BITS downto 0);\n"
        + _constant(
            "ADDR_SPACE_BYTES",
            "map_addr_t",
            "shift_left(to_unsigned(1, map_addr_t'length), ADDR_BITS)",
            "Tamanho do espaço de endereços, 2**ADDR_BITS bytes.",
        )
    )


def _flag_block(config: Config) -> str:
    """Write the `HAS_*` constants and the composed ones."""
    text = "\n"
    for name, value in config.flags.items():
        if name in PERIPHERALS:
            continue
        what = name.removeprefix("HAS_").replace("_", " ").capitalize()
        text += _boolean(name, value, f"Presença de {what} na plataforma.")
    text += "\n" + _boolean(
        "HAS_MULDIV",
        "HAS_M or HAS_ZMMUL",
        "Há multiplicação de inteiros, com M ou com Zmmul.",
    )
    text += _boolean(
        "HAS_ANY_COUNTER",
        "HAS_ZICNTR or HAS_ZIHPM",
        "Há contadores de desempenho, com Zicntr ou com Zihpm.",
    )
    text += _boolean(
        "HAS_SSCOF",
        "HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS",
        "O estouro de contador gera interrupção: Sscofpmf com Zihpm e "
        "interrupções.",
    )
    return text


def _memory_block(config: Config) -> str:
    """Write the externals, the cache window and the memory map."""
    bits = config.address_bits
    text = "\n" + _boolean(
        "ROM_EXTERNAL", config.rom_external, "A ROM fica fora do núcleo."
    )
    text += _boolean(
        "RAM_EXTERNAL", config.ram_external, "A RAM fica fora do núcleo."
    )
    text += _constant(
        "BOOT_MEMORY_BITS",
        "natural",
        str(config.boot_bits),
        "Expoente do tamanho da BOOT_MEMORY, em bytes (2**BOOT_MEMORY_BITS).",
    )
    text += _constant(
        "CACHE_WINDOW_BITS",
        "natural",
        str(config.cache_window_bits),
        "Largura da janela de endereços das caches, em bits: a tag guarda "
        "os bits abaixo dela.",
    )
    comments = {
        "ROM_BASE": "Base da ROM, em bytes.",
        "ROM_END": "Fim exclusivo da ROM, em bytes.",
        "RAM_BASE": "Base da RAM, em bytes.",
        "RAM_END": "Fim exclusivo da RAM, em bytes.",
        "EXT_BASE": "Base da janela externa, em bytes.",
        "PERIPH_BASE": "Base da janela de periféricos, em bytes.",
    }
    text += "\n"
    for name, value in config.addresses.items():
        text += _constant(
            name, "map_addr_t", _address(value, bits), comments[name]
        )
    return text


def _peripheral_block(config: Config) -> str:
    """Write the slots and the `HAS_*` constant of each peripheral."""
    text = (
        "\n\t-- Janelas de periférico que têm periférico (bit n para o "
        "índice n).\n"
        "\tsubtype periph_slots_t is std_logic_vector("
        f"{SLOT_COUNT - 1} downto 0);\n"
    )
    text += _constant(
        "PERIPH_SLOTS",
        "periph_slots_t",
        f'"{config.slots:0{SLOT_COUNT}b}"',
        "Janelas de periférico ocupadas na plataforma.",
    )
    for flag, name in PERIPHERALS.items():
        text += _boolean(
            flag,
            config.flags[flag],
            f"O periférico {name} está presente na plataforma.",
        )
    return text


def render_config_pkg(
    config: Config,
    source: str,
    overrides: dict[str, bool | int] | None = None,
) -> str:
    """Render the `config_pkg` of a platform.

    Parameters
    ----------
    config : Config
        The choices (see `build_config`).
    source : str
        The platform file, for the header.
    overrides : dict of {str: bool or int}, optional
        The variant, named in the header.

    Returns
    -------
    str
        The file: the header, the package of constants with
        `isa_string` and `check_isa`, and the package body.
    """
    variant = "".join(
        f"\n-- Variante: {key}={str(value).lower()}."
        for key, value in (overrides or {}).items()
    )
    steps = "".join(
        f'\t\tif {flag} then\n\t\t\tadd("{piece}");\n\t\tend if;\n'
        for flag, piece in ISA_ORDER
    )
    return _HEADER.format(
        source=source,
        variant=variant,
        package=PACKAGE,
        isa_steps=steps,
        declarations=_base_block(config)
        + _flag_block(config)
        + _memory_block(config)
        + _peripheral_block(config),
    )


def source_name(platform_file: Path, root: Path) -> str:
    """Name the platform file for the header of a generated file.

    Parameters
    ----------
    platform_file : Path
        The platform YAML.
    root : Path
        The project root.

    Returns
    -------
    str
        The path relative to the root, or the file name when the
        platform is outside it.
    """
    try:
        return str(platform_file.relative_to(root))
    except ValueError:
        return platform_file.name


def render_variant(
    platform: dict[str, Any],
    platform_file: Path,
    root: Path,
    overrides: dict[str, bool | int] | None = None,
) -> str:
    """Render the `config_pkg` of a platform or of a variant of it.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_file : Path
        The platform YAML.
    root : Path
        The project root, for the header.
    overrides : dict of {str: bool or int}, optional
        The variant (see `parse_overrides`).

    Returns
    -------
    str
        The file.

    Raises
    ------
    ValueError
        If the platform or the variant is inconsistent.
    """
    config = build_config(platform, platform_file, overrides)
    return render_config_pkg(
        config, source_name(platform_file, root), overrides
    )
