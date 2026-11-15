"""Builders of the catalog and platforms of external peripherals."""

import shutil
from pathlib import Path

from multifpga_support import BOARDS, CHIPS

from riscv_tools.board_generate import GenerateRequest

FIXTURES = Path(__file__).parent / "fixtures" / "peripherals"
EXAMPLES = sorted(p.stem for p in (FIXTURES / "platforms").glob("*.yaml"))
# Exemplos sem entidade no `Peripherals`: o topo os recusa.
MISSING = ("hdmi_tmds",)
GENERATED = [k for k in EXAMPLES if k not in MISSING]


def catalog(tmp_path: Path) -> Path:
    """Copy the catalog of the fixtures and add the example board.

    Parameters
    ----------
    tmp_path : Path
        An empty folder.

    Returns
    -------
    Path
        The `boards` folder: the boards of the multi-FPGA fixtures, the
        example board with the bus roles of every kind and the modes of
        the video.
    """
    boards = tmp_path / "boards"
    shutil.copytree(BOARDS, boards)
    shutil.copytree(FIXTURES / "boards" / "example", boards / "example")
    shutil.copy(FIXTURES / "boards" / "video-modes.yaml", boards)
    shutil.copytree(CHIPS, tmp_path / "Memory" / "chips")
    return boards


def request(tmp_path: Path, kind: str) -> GenerateRequest:
    """Prepare the generation of the example platform of a kind.

    Parameters
    ----------
    tmp_path : Path
        An empty folder.
    kind : str
        The example (`ps2`, `adc`, `sd_spi`).

    Returns
    -------
    GenerateRequest
        The request, with the catalog and the chips of the fixtures.
    """
    target = tmp_path / "platform.yaml"
    shutil.copy(FIXTURES / "platforms" / f"{kind}.yaml", target)
    return GenerateRequest(
        target, None, catalog(tmp_path), CHIPS, accept_inferred=True
    )
