"""Tests for the `-march`, the `-mabi` and the multilib of a core."""

import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from support import GCC, check_equal, check_in

from riscv_tools import profiles
from riscv_tools.memory_map.core_profile import legacy_to_core
from riscv_tools.memory_map.march import abi_of, march_of, multilib_of

MATRIX = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "real_platform"
    / "Core"
    / "profiles"
    / "matrix.yaml"
)
PROFILES = profiles.expand(profiles.load_spec(MATRIX))
# O mapa medido na imagem ci-elf (GCC 16.1.0): base, multiplicação e a
# biblioteca do picolibc que o par `-march` e `-mabi` escolhe.
ORACLE = {
    ("i", "none"): "rv32i/ilp32",
    ("i", "zmmul"): "rv32i_zmmul/ilp32",
    ("i", "m"): "rv32im/ilp32",
    ("e", "none"): "rv32e/ilp32e",
    ("e", "zmmul"): "rv32e_zmmul/ilp32e",
    ("e", "m"): "rv32em_zmmul/ilp32e",
}
HINTS = ["Zihintntl", "Zihintpause"]
NO_EXTRAS: list[str] = []


def _multiplication(generics: Any) -> str:
    """Name the multiplication a profile has: `m`, `zmmul` or `none`."""
    if generics.get("has_m"):
        return "m"
    return "zmmul" if generics.get("has_zmmul") else "none"


def _cases() -> list[tuple[str, dict[str, Any], str]]:
    """List each profile with and without the hint extras.

    Returns
    -------
    list of tuple of (str, dict, str)
        The profile name, its `core` block and the multilib the oracle
        expects for it.
    """
    cases: list[tuple[str, dict[str, Any], str]] = []
    for profile in PROFILES:
        base = "e" if profile.generics.get("has_e") else "i"
        want = ORACLE[base, _multiplication(profile.generics)]
        for extras in (NO_EXTRAS, HINTS):
            core = legacy_to_core(profile.name, extras)
            cases.append((profile.name, core, want))
    return cases


CASES = _cases()


def test_the_matrix_has_480_profiles_and_960_cases() -> None:
    """The matrix of the Core expands to 480 profiles."""
    check_equal(len(PROFILES), 480)
    check_equal(len(CASES), 960)


def test_every_profile_has_one_of_the_six_multilibs() -> None:
    """Each profile maps to the multilib of the measured table."""
    counts: Counter[str] = Counter()
    for name, core, want in CASES:
        found = multilib_of(core)
        check_equal(found, want, f"{name} {core['extensions']}")
        counts[found] += 1
    check_equal(set(counts), set(ORACLE.values()))
    # 80 perfis por biblioteca, vezes dois pelas extras de dica.
    check_equal(set(counts.values()), {160})


def test_the_march_lists_what_the_core_has() -> None:
    """The `-march` has the base and every extension, no RTL extra."""
    for name, core, _ in CASES:
        march = march_of(core)
        head, *tokens = march.split("_")
        base = f"rv32{core['base'].lower()}"
        check_equal(head, base + ("m" if "M" in core["extensions"] else ""))
        for ext in core["extensions"]:
            if ext not in ("M", "Interrupts", "Sscofpmf", "AccessFaults"):
                check_in(ext.lower(), tokens, f"{name}: {march}")
        wants_csr = {"Zicsr", "Zicntr", "Zihpm"} & set(core["extensions"])
        check_equal("zicsr" in tokens, bool(wants_csr), f"{name}: {march}")
        check_equal(len(tokens), len(set(tokens)), march)


def test_the_march_follows_the_order_of_the_matrix() -> None:
    """The names come in the order of the matrix, hints last."""
    core = legacy_to_core(
        "rv32im_zicclsm_zicntr_zihpm_zifencei_zimop_zicond",
        ["Zihintpause", "Zihintntl", "Interrupts", "Sscofpmf"],
    )
    check_equal(
        march_of(core),
        "rv32im_zicclsm_zicsr_zicntr_zihpm_zifencei_zimop_zicond"
        "_zihintntl_zihintpause",
    )
    check_equal(abi_of(core), "ilp32")
    check_equal(multilib_of(core), "rv32im/ilp32")


@pytest.mark.parametrize(
    ("profile", "extras", "march", "abi", "multilib"),
    [
        ("rv32i", [], "rv32i", "ilp32", "rv32i/ilp32"),
        ("rv32e", [], "rv32e", "ilp32e", "rv32e/ilp32e"),
        ("rv32im", [], "rv32im", "ilp32", "rv32im/ilp32"),
        ("rv32e_zmmul", [], "rv32e_zmmul", "ilp32e", "rv32e_zmmul/ilp32e"),
        ("rv32em", [], "rv32em", "ilp32e", "rv32em_zmmul/ilp32e"),
        (
            "rv32i_zicntr",
            ["Interrupts"],
            "rv32i_zicsr_zicntr",
            "ilp32",
            "rv32i/ilp32",
        ),
        (
            "rv32i_zmmul_zihpm",
            ["Zihintpause", "AccessFaults"],
            "rv32i_zicsr_zihpm_zmmul_zihintpause",
            "ilp32",
            "rv32i_zmmul/ilp32",
        ),
    ],
)
def test_march_abi_and_multilib_of_known_cores(
    profile: str, extras: list[str], march: str, abi: str, multilib: str
) -> None:
    """Spot checks of the three values."""
    core = legacy_to_core(profile, extras)
    check_equal(march_of(core), march)
    check_equal(abi_of(core), abi)
    check_equal(multilib_of(core), multilib)


def test_case_and_order_of_the_block_do_not_matter() -> None:
    """The names of the block are not case sensitive."""
    mixed = {"type": 32, "base": "i", "extensions": ["ZICNTR", "m", "zicclsm"]}
    check_equal(march_of(mixed), "rv32im_zicclsm_zicsr_zicntr")


def test_a_64_bit_core_has_an_abi_but_no_multilib() -> None:
    """The image has no RV64 multilib, so the lookup is an error."""
    core = {"type": 64, "base": "I", "extensions": ["M"]}
    check_equal(march_of(core), "rv64im")
    check_equal(abi_of(core), "lp64")
    check_equal(abi_of({**core, "base": "E"}), "lp64e")
    with pytest.raises(ValueError, match="no multilib"):
        multilib_of(core)


def _gcc(args: list[str]) -> str:
    """Run the gcc with the args and return what it prints."""
    done = subprocess.run(
        [GCC, *args], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _lib_dir(path: str) -> str:
    """Name the multilib directory a library path lives in."""
    rest = path.split("riscv32-unknown-elf/lib/", 1)[1]
    return rest.rsplit("/", 1)[0] if "/" in rest else "."


def _probe(case: tuple[str, dict[str, Any], str]) -> list[str]:
    """Compile with the pair and check the libraries it picks.

    Parameters
    ----------
    case : tuple of (str, dict, str)
        The profile name, its block and the multilib the oracle wants.

    Returns
    -------
    list of str
        What is wrong with the profile; empty when the compiler accepts
        the pair and the libraries are there.
    """
    name, core, want = case
    flags = [f"-march={march_of(core)}", f"-mabi={abi_of(core)}"]
    bad: list[str] = []
    try:
        _gcc([*flags, "-S", "-x", "c", "/dev/null", "-o", "/dev/null"])
        directory = _gcc([*flags, "-print-multi-directory"])
        # A variante `rv32im/ilp32` é a raiz da imagem cujo padrão é M.
        if directory not in (want, "." if want == "rv32im/ilp32" else want):
            bad.append(f"{name}: multilib {directory!r}, expected {want!r}")
        for lib in ("libc.a", "crt0-hosted.o"):
            path = _gcc([*flags, f"-print-file-name={lib}"])
            if not Path(path).is_file():
                bad.append(f"{name}: {lib} missing for {flags}")
            elif _lib_dir(path) != directory:
                bad.append(f"{name}: {lib} comes from {_lib_dir(path)}")
    except subprocess.CalledProcessError as error:
        bad.append(f"{name}: {flags} refused: {error.stderr.strip()}")
    return bad


@pytest.mark.skipif(shutil.which(GCC) is None, reason=f"needs {GCC} on PATH")
def test_the_compiler_has_a_multilib_for_each_of_the_960_cases() -> None:
    """The GCC accepts each pair and picks the library of the table."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        wrong = [bad for found in pool.map(_probe, CASES) for bad in found]
    check_equal(wrong, [], "\n".join(wrong[:10]))
