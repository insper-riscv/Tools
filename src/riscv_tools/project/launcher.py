"""The script that runs `riscv-tools` with the host's Quartus."""

import stat
from pathlib import Path

LAUNCHER_FILE = "rt"
QUARTUS_ROOT = "/opt/altera_lite"
QUARTUS_BIN = "25.1std/quartus/bin"
IMAGE = "ghcr.io/insper-riscv/dev_tools:latest"

_SCRIPT = f"""\
#!/bin/sh
# Roda o riscv-tools na imagem dev_tools com o Quartus e o servidor JTAG
# do computador. Uso: ./rt project build
set -eu
QUARTUS_ROOT="${{QUARTUS_ROOT:-{QUARTUS_ROOT}}}"
IMAGE="${{RISCV_TOOLS_IMAGE:-{IMAGE}}}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# O jtagconfig do computador inicia o jtagd, que o contêiner alcança pela
# rede do computador; sem ele o contêiner não enxerga o USB-Blaster.
if [ -x "$QUARTUS_ROOT/{QUARTUS_BIN}/jtagconfig" ]; then
    "$QUARTUS_ROOT/{QUARTUS_BIN}/jtagconfig" >/dev/null 2>&1 || true
fi
# A trava da placa é um arquivo em /tmp com o nome do computador; o
# contêiner usa o /tmp e o nome do computador para pegar a mesma trava de
# quem usa a placa por fora (a CI e os outros usuários).
RISCV_TOOLS_HOST="${{RISCV_TOOLS_HOST:-$(hostname -s)}}"
export QUARTUS_ROOT RISCV_TOOLS_HOST
exec docker run --rm --network host \\
    --user "$(id -u):$(id -g)" -e HOME=/tmp/h \\
    -e QUARTUS_ROOT -e RISCV_TOOLS_HOST \\
    -v /tmp:/tmp \\
    -v "$HERE":/w -w /w \\
    -v "$QUARTUS_ROOT":"$QUARTUS_ROOT":ro \\
    "$IMAGE" sh -c \\
    'export PATH="$QUARTUS_ROOT/{QUARTUS_BIN}:$PATH"; exec riscv-tools "$@"' \\
    riscv-tools "$@"
"""


def write_launcher(project: Path) -> Path:
    """Write the launcher script into a project folder.

    Parameters
    ----------
    project : Path
        The project folder.

    Returns
    -------
    Path
        The script, executable by its owner and readable by all.
    """
    path = project / LAUNCHER_FILE
    path.write_text(_SCRIPT)
    path.chmod(
        stat.S_IRWXU
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )
    return path
