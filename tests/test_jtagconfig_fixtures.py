"""The samples of tests/fixtures/jtagconfig, read by Tools."""

from pathlib import Path

import pytest
import yaml
from support import check_equal

from riscv_tools.jtag import detect_jtag_hardware, jtag_chain_healthy

FIXTURES = Path(__file__).parent / "fixtures" / "jtagconfig"


def _serve(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make `jtagconfig` print the content of one sample."""
    text = (FIXTURES / name).read_text(encoding="utf-8")

    def run(*_a: object, **_k: object) -> object:
        return type("Done", (), {"stdout": text, "stderr": ""})()

    monkeypatch.setattr("riscv_tools.jtag.hardware.subprocess.run", run)


def _manifest() -> list[dict[str, str]]:
    """Read the entries of the MANIFEST.yaml of the samples."""
    text = (FIXTURES / "MANIFEST.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return list(data["fixtures"])


def test_every_sample_is_listed_with_its_origin() -> None:
    """Each listed sample exists and says where it came from."""
    listed = {entry["arquivo"] for entry in _manifest()}
    for name in listed:
        check_equal((FIXTURES / name).is_file(), True, name)
    for entry in _manifest():
        name = entry["arquivo"]
        check_equal(entry["origem"] in {"medido", "inferido"}, True, name)
        needed = "host" if entry["origem"] == "medido" else "fonte"
        check_equal(bool(entry.get(needed)), True, f"{name} {needed}")


@pytest.mark.parametrize(
    ("device", "cable"),
    [
        ("x (0x02B050DD)", "USB-Blaster [1-2]"),
        ("x (0x020F70DD)", "USB-Blaster [1-3]"),
        ("x (0x020F30DD)", "USB-Blaster [1-5]"),
        ("x (0x031050DD)", "USB-Blaster [1-6]"),
    ],
)
def test_the_four_cables_of_the_workstation_are_told_by_idcode(
    monkeypatch: pytest.MonkeyPatch, device: str, cable: str
) -> None:
    """Each IDCODE of the measured PC1 listing picks its own cable."""
    _serve(monkeypatch, "four-cables.txt")
    check_equal(detect_jtag_hardware(device), cable, "cable")


@pytest.mark.parametrize(
    "name", ["pc1_four_cables_nodes.txt", "notebook_one_cable_nodes.txt"]
)
def test_the_node_lines_do_not_hide_the_cable(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """The -n listing (Design hash and nodes) still picks the cable."""
    _serve(monkeypatch, name)
    notebook = name.startswith("notebook")
    want = "USB-Blaster [3-6]" if notebook else "USB-Blaster [1-2]"
    check_equal(detect_jtag_hardware("x (0x02B050DD)"), want, "cable")


@pytest.mark.parametrize(
    ("name", "healthy"),
    [
        ("four-cables.txt", True),
        ("notebook_one_cable.txt", True),
        ("de10-nano.txt", True),
        ("vidor_emulated_usb_blaster.txt", True),
        ("broken.txt", False),
    ],
)
def test_a_broken_chain_is_told_from_a_healthy_one(
    monkeypatch: pytest.MonkeyPatch, name: str, healthy: bool
) -> None:
    """Only the samples with the 'chain broken' text are unhealthy."""
    _serve(monkeypatch, name)
    check_equal(jtag_chain_healthy(), healthy, name)
