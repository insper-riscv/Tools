"""The how-to for the tests and for a program of one's own."""

from pathlib import Path
from typing import Any

from riscv_tools.memory_map import evaluate
from riscv_tools.project.manifest import Manifest

TESTS_URL = "https://github.com/insper-riscv/Tests.git"
HEADER_FILE = "rv32_platform.h"

_PT = """\
Rodar os testes e compilar um programa seu
(rode estes comandos na pasta do projeto, com ./rt)

1. Baixe o repositório Tests ao lado do Insper-RISC-V:
     git clone --recurse-submodules {url} Tests

2. Aponte o Tests para a plataforma {name}. Ela precisa estar num commit
   do Insper-RISC-V; depois o submódulo do Tests passa a usá-lo:
     git -C {repo} add {platform} paths.yaml scripts/generate_sources.py
     git -C {repo} commit -m "feat: plataforma {name}"
     git -C Tests/Insper-RISC-V fetch ../../{repo} HEAD
     git -C Tests/Insper-RISC-V checkout FETCH_HEAD
     git -C Tests/Insper-RISC-V submodule update --init --recursive

3. Gere a configuração derivada e o cabeçalho do mapa:
     ./rt --root Tests platform sync --prefix Insper-RISC-V \\
       --source Insper-RISC-V/{platform}/config.yaml \\
       --output tools/riscv_build/config.platform-{name}.yaml
     cp -r Tests/tools/riscv_build/include-sdram \\
       Tests/tools/riscv_build/include-{name}
   e ajuste os endereços de Tests/tools/riscv_build/include-{name}/{header}
   para os desta plataforma:
{sed}
   Crie Tests/tools/riscv_build/config.{name}.yaml:
     extends: config.platform-{name}.yaml
     paths:
       include_dir: tools/riscv_build/include-{name}
       build_dir: build-{name}
       c_dir: c
       asm_dir: asm

4. Compile e rode os testes que já existem:
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       generate-header
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       compile --emit mif --only arithmetic-add,multiply
     ./rt project flash Tests/build-{name}/real/arithmetic-add.mif
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       run --skip-reconfigure --skip-recompile --only multiply

   O flash recompila a FPGA e embute um programa; o run troca os
   seguintes pela JTAG, sem recompilar.

5. Compile um programa seu: crie Tests/c/meu-programa/src.c
     #include <stdint.h>
     #include "rv32_test.h"
     int main(void) {{
         volatile uint32_t *p = (volatile uint32_t *)0x40000100;
         p[0] = 42;
         if (p[0] == 42) {{ RV32_PASS(); }}
         RV32_FAIL(1);
     }}
   e compile e rode como no passo 4, com --only meu-programa. A pasta
   c/<nome> com um src.c basta; não há nada a registrar.
"""

_EN = """\
Run the tests and compile a program of your own
(run these commands in the project folder, with ./rt)

1. Download the Tests repository next to Insper-RISC-V:
     git clone --recurse-submodules {url} Tests

2. Point Tests at the platform {name}. It must be in a commit of
   Insper-RISC-V; then the submodule of Tests uses that commit:
     git -C {repo} add {platform} paths.yaml scripts/generate_sources.py
     git -C {repo} commit -m "feat: platform {name}"
     git -C Tests/Insper-RISC-V fetch ../../{repo} HEAD
     git -C Tests/Insper-RISC-V checkout FETCH_HEAD
     git -C Tests/Insper-RISC-V submodule update --init --recursive

3. Write the derived configuration and the header of the map:
     ./rt --root Tests platform sync --prefix Insper-RISC-V \\
       --source Insper-RISC-V/{platform}/config.yaml \\
       --output tools/riscv_build/config.platform-{name}.yaml
     cp -r Tests/tools/riscv_build/include-sdram \\
       Tests/tools/riscv_build/include-{name}
   and set the addresses in
   Tests/tools/riscv_build/include-{name}/{header} to this platform's:
{sed}
   Create Tests/tools/riscv_build/config.{name}.yaml:
     extends: config.platform-{name}.yaml
     paths:
       include_dir: tools/riscv_build/include-{name}
       build_dir: build-{name}
       c_dir: c
       asm_dir: asm

4. Compile and run the tests that already exist:
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       generate-header
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       compile --emit mif --only arithmetic-add,multiply
     ./rt project flash Tests/build-{name}/real/arithmetic-add.mif
     ./rt --root Tests --config Tests/tools/riscv_build/config.{name}.yaml \\
       run --skip-reconfigure --skip-recompile --only multiply

   The flash recompiles the FPGA and embeds one program; the run swaps
   the following ones over JTAG, without recompiling.

5. Compile a program of your own: create Tests/c/my-program/src.c
     #include <stdint.h>
     #include "rv32_test.h"
     int main(void) {{
         volatile uint32_t *p = (volatile uint32_t *)0x40000100;
         p[0] = 42;
         if (p[0] == 42) {{ RV32_PASS(); }}
         RV32_FAIL(1);
     }}
   and compile and run it as in step 4, with --only my-program. A
   c/<name> folder with a src.c is enough; there is nothing to register.
"""


def _hex(value: int) -> str:
    """Write an address the way the header does.

    Parameters
    ----------
    value : int
        The address.

    Returns
    -------
    str
        Eight hexadecimal digits after `0x`.
    """
    return f"0x{value:08X}"


def header_values(platform: dict[str, Any]) -> dict[str, str]:
    """Work out the header constants that follow from the map.

    Parameters
    ----------
    platform : dict of {str: Any}
        The `platform.yaml`, parsed.

    Returns
    -------
    dict of {str: str}
        The value of each constant, for those the platform defines.
    """
    values: dict[str, str] = {}
    for region in platform["regions"]:
        if region.get("kind") == "ram":
            end = int(evaluate(region["base"])) + int(evaluate(region["size"]))
            values["RV32_RAM_END"] = _hex(end)
    reserved = platform["reserved"]
    values["RV32_STDOUT_BASE"] = _hex(
        int(evaluate(reserved["stdout"]["base"]))
    )
    values["RV32_TOHOST"] = _hex(int(evaluate(reserved["tohost"]["base"])))
    for bank in platform.get("flash", {}).get("banks", []):
        key = f"RV32_BANK_{bank['name']}"
        values[f"{key}_BASE"] = _hex(int(evaluate(bank["base"])))
        values[f"{key}_SIZE"] = _hex(int(evaluate(bank["size"])))
    return values


def header_sed(values: dict[str, str], header: str) -> str:
    """Write the `sed` command that sets the header constants.

    Parameters
    ----------
    values : dict of {str: str}
        The value of each constant.
    header : str
        Name of the header file.

    Returns
    -------
    str
        An indented shell command.
    """
    lines = [
        f"       -e 's/^(#define {name} +)0x[0-9A-Fa-f]+/\\1{value}/' \\"
        for name, value in values.items()
    ]
    return "\n".join(["     sed -i -E \\", *lines, f"       {header}"])


def render_tests_help(
    language: str, manifest: Manifest, platform: dict[str, Any]
) -> str:
    """Write the how-to for the tests and for a program of one's own.

    Parameters
    ----------
    language : str
        `pt` or `en`.
    manifest : Manifest
        The project.
    platform : dict of {str: Any}
        The `platform.yaml` of the project, parsed.

    Returns
    -------
    str
        The text.
    """
    path = Path("Tests/tools/riscv_build") / f"include-{manifest.name}"
    return (_PT if language == "pt" else _EN).format(
        url=TESTS_URL,
        name=manifest.name,
        repo=manifest.repo,
        platform=manifest.platform,
        header=HEADER_FILE,
        sed=header_sed(header_values(platform), str(path / HEADER_FILE)),
    )
