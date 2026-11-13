"""Tests for the `core` block and the profile it stands for."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check_equal, check_in, profile_matrix

from riscv_tools.memory_map import load_platform, set_override
from riscv_tools.memory_map.core_profile import legacy_to_core, normalize

MATRIX = profile_matrix("rv32i", "rv32e", "rv64i")


def _load(
    root: Path,
    core: Any,
    matrix: dict[str, Any] = MATRIX,
    **changes: Any,
) -> dict[str, Any]:
    """Write a platform with a `core` block and load it."""
    (root / "matrix.yaml").write_text(yaml.safe_dump(matrix))
    data = {"core": core, "profiles": "matrix.yaml"} | changes
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return load_platform(path)


def _block(extensions: list[str], **changes: Any) -> dict[str, Any]:
    """Write a block of an RV32I core."""
    return {"type": 32, "base": "I", "extensions": extensions} | changes


@pytest.fixture(autouse=True)
def _no_override() -> None:
    """Start each test without `--profile`."""
    set_override(None)


def test_the_profile_is_inferred_in_the_order_of_the_matrix(
    tmp_path: Path,
) -> None:
    """Order and case of the block do not change the name."""
    platform = _load(tmp_path, _block(["zicntr", "M", "Zicclsm"]))
    check_equal(platform["profile"], "rv32im_zicclsm_zicntr")
    check_equal(platform["extras"], [])
    base_e = _load(tmp_path, _block([], base="e"))
    check_equal(base_e["profile"], "rv32e")


def test_zicsr_beside_zicntr_is_accepted(tmp_path: Path) -> None:
    """Zicntr implies Zicsr, so the name does not cite it."""
    platform = _load(tmp_path, _block(["Zicsr", "Zicntr"]))
    check_equal(platform["profile"], "rv32i_zicntr")
    check_equal(_load(tmp_path, _block(["Zicsr"]))["profile"], "rv32i_zicsr")


def test_the_extensions_the_matrix_lacks_are_the_extras(
    tmp_path: Path,
) -> None:
    """Zihintpause, Interrupts and the like stay on."""
    ext = ["Interrupts", "M", "Zihintpause", "AccessFaults"]
    platform = _load(tmp_path, _block(ext))
    check_equal(platform["profile"], "rv32im")
    check_equal(
        platform["extras"], ["Zihintpause", "Interrupts", "AccessFaults"]
    )


def test_profile_replaces_only_the_part_of_the_matrix(tmp_path: Path) -> None:
    """`--profile` keeps the extras and skips the extensions."""
    set_override("rv32i_zicsr")
    platform = _load(tmp_path, _block(["M", "Zicsr", "Interrupts"]))
    check_equal(platform["extras"], ["Interrupts"])


@pytest.mark.parametrize(
    ("core", "message"),
    [
        (_block(["Zbb"]), "unknown extension 'Zbb'"),
        (_block(["M", "m"]), "M is listed twice"),
        (_block(["Zmmul"]), "Zmmul is not in the specification"),
        ({"type": 32, "isa": "I", "extensions": []}, "the key is called base"),
        ({"type": 16, "base": "I", "extensions": []}, "32 or 64"),
        ({"type": 32, "base": "X", "extensions": []}, "I or E"),
        ({"type": 32, "base": "I"}, "core.extensions is required"),
        (_block([], other=1), "unknown keys"),
        ("rv32i", "must be a mapping"),
    ],
)
def test_an_invalid_block_is_an_error(
    tmp_path: Path, core: Any, message: str
) -> None:
    """Each mistake has its own message."""
    with pytest.raises(ValueError, match=message):
        _load(tmp_path, core)


def test_a_64_bit_core_needs_an_rv64_base(tmp_path: Path) -> None:
    """`type: 64` without an rv64 base in the matrix is an error."""
    with pytest.raises(ValueError, match="needs a base rv64i"):
        _load(tmp_path, _block(["M"], type=64), profile_matrix("rv32i"))
    check_equal(_load(tmp_path, _block([], type=64))["profile"], "rv64i")


def test_the_matrix_can_refuse_a_combination(tmp_path: Path) -> None:
    """M with Zmmul is refused by the exclusion of the matrix."""
    matrix = profile_matrix("rv32i")
    matrix["extensions"].append({"name": "Zmmul", "generic": "has_zmmul"})
    matrix["mutually_exclusive"].append(["M", "Zmmul"])
    with pytest.raises(ValueError, match="refuses rv32i with M, Zmmul"):
        _load(tmp_path, _block(["M", "Zmmul"]), matrix)


@pytest.mark.parametrize("key", ["profile", "extras"])
def test_profile_and_extras_are_refused_with_the_migration(
    tmp_path: Path, key: str
) -> None:
    """The message says which block replaces them."""
    value: Any = "rv32em_zicntr" if key == "profile" else ["Interrupts"]
    with pytest.raises(ValueError, match="no longer accepted") as error:
        _load(tmp_path, _block([]), **{key: value})
    check_in("becomes `core` with type 32, base", str(error.value))


def test_the_migration_names_the_base_and_the_extensions(
    tmp_path: Path,
) -> None:
    """`rv32e` turns into base E."""
    path = tmp_path / "platform.yaml"
    path.write_text("profile: rv32em_zicntr_zihpm\nextras: [Interrupts]\n")
    with pytest.raises(ValueError, match="no longer accepted") as error:
        load_platform(path)
    check_in(
        "type 32, base E and extensions M, Zicntr, Zihpm, Interrupts",
        str(error.value),
    )


def test_legacy_to_core_writes_the_block() -> None:
    """A profile name and extras give the block."""
    check_equal(
        legacy_to_core("rv64im_zicsr", ["Interrupts"]),
        {
            "type": 64,
            "base": "I",
            "extensions": ["M", "Zicsr", "Interrupts"],
        },
    )
    with pytest.raises(ValueError, match="must start with"):
        legacy_to_core("arm", [])


def test_without_a_matrix_the_name_follows_the_order_of_the_core() -> None:
    """A platform without `profiles` still gets a name."""
    data: dict[str, Any] = {"core": _block(["Zifencei", "Zicntr", "M"])}
    normalize(data, Path("platform.yaml"))
    check_equal(data["profile"], "rv32im_zicntr_zifencei")
