"""calibration: profile list, harness steps and fit, with fake tools."""

import fcntl
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check, check_equal, check_in

from riscv_tools import calibration as cal
from riscv_tools import fit_estimate as fe
from riscv_tools.calibration import harness

MAX_ROUNDING_PCT = 0.1
PLATFORM: dict[str, Any] = {
    "platform": "demo",
    "profile": "rv32im",
    "extras": ["Interrupts"],
    "interrupts": {"plic": {"priority_bits": 3}},
    "peripherals": [
        {"name": "UART", "base": 1, "id": 4},
        {"name": "CLINT", "base": 2, "id": 6},
        {"name": "PLIC", "base": 3, "id": 7},
    ],
    "memory": {"icache": {"enabled": True, "size_bits": 32768}},
    "generate": {"vhdl": {"path": "demo/pkg.vhd"}},
}
PLAN: dict[str, Any] = {
    "family": "demo",
    "unit": "alm",
    "project": {
        "platform": "demo/platform.yaml",
        "synth": "demo/synth.tcl",
        "qsf": "demo/demo.qsf",
        "seed": 5,
    },
    "bits_per_block": 10240,
    "reference_kbit": 32,
    "fixed": {"peripherals.UART": 0.0},
    "known_fit": {"profile": "full", "alms": [900, 1100]},
    "profiles": [
        {"id": "base", "group": 1, "profile": "rv32i"},
        {"id": "mul", "group": 2, "profile": "rv32im"},
        {"id": "zmmul", "group": 2, "profile": "rv32i_zmmul"},
        {"id": "csr", "group": 3, "profile": "rv32im_zicsr"},
        {
            "id": "ic8",
            "group": 7,
            "profile": "rv32im_zicsr",
            "icache_kbit": 8,
        },
        {
            "id": "ic128",
            "group": 7,
            "profile": "rv32im_zicsr",
            "icache_kbit": 128,
        },
        {
            "id": "ic64",
            "group": 7,
            "profile": "rv32im_zicsr",
            "icache_kbit": 64,
            "holdout": True,
        },
        {"id": "full", "group": 5, "profile": "rv32im_zicsr", "holdout": True},
    ],
}
PACKAGE = (
    "package demo_pkg is\n"
    "\t-- Base.\n\tconstant A : natural := 1;\n"
    "end package demo_pkg;\n"
)
REFERENCE = PACKAGE.replace(
    "end package",
    "\t-- So com interrupcoes.\n\tconstant PLIC_ADDR_WIDTH : natural := 20;\n"
    "end package",
)


def write_plan(tmp_path: Path) -> Path:
    """Write the demo profile list."""
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(PLAN), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "name, base, extensions",
    [
        ("rv32i", "rv32i", set[str]()),
        ("rv32em", "rv32e", {"M"}),
        (
            "rv32im_zicclsm_zicntr_zihpm_zifencei",
            "rv32i",
            {"M", "Zicclsm", "Zicntr", "Zihpm", "Zifencei"},
        ),
        ("rv32i_zmmul", "rv32i", {"Zmmul"}),
    ],
)
def test_profile_names_are_split(
    name: str, base: str, extensions: set[str]
) -> None:
    """Profile names are split into base and extensions."""
    check_equal(cal.parse_profile_name(name), (base, frozenset(extensions)))


@pytest.mark.parametrize("name", ["rv64i", "rv32ix", "rv32i_zfoo"])
def test_unknown_profile_names_are_refused(name: str) -> None:
    """Unknown bases, letters and extensions are refused."""
    with pytest.raises(ValueError, match="unknown"):
        cal.parse_profile_name(name)


def test_the_plan_is_read_and_checked(tmp_path: Path) -> None:
    """The plan is read; a repeated id is refused."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    check_equal(len(plan.profiles), 8)
    check(plan.profiles[-1].holdout)
    PLAN["profiles"].append(dict(PLAN["profiles"][0]))
    try:
        with pytest.raises(ValueError, match="repeated"):
            cal.load_profile_list(write_plan(tmp_path))
    finally:
        PLAN["profiles"].pop()


def test_the_spec_takes_hpm_from_the_generics() -> None:
    """The Zihpm size of a spec comes from the generics."""
    definition = cal.ProfileDef(
        "x",
        4,
        "rv32im_zicntr_zihpm",
        generics={"HPM_COUNTERS": 4, "HPM_WIDTH": 40},
    )
    spec = cal.spec_of(definition)
    check_equal((spec.hpm_counters, spec.hpm_width), (4, 40))


def test_apply_profile_drops_the_interrupts_without_the_extra(
    tmp_path: Path,
) -> None:
    """Without Interrupts the section and the CLINT and PLIC go away."""
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(PLATFORM), encoding="utf-8")
    definition = cal.ProfileDef("x", 1, "rv32i", icache_kbit=8, dcache_kbit=16)
    harness.apply_profile(path, definition)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    check_equal(data["profile"], "rv32i")
    check_equal(data["extras"], [])
    check("interrupts" not in data)
    check_equal([p["name"] for p in data["peripherals"]], ["UART"])
    check_equal(data["memory"]["icache"]["size_bits"], 8192)
    check_equal(data["memory"]["dcache"]["size_bits"], 16384)


def test_apply_profile_keeps_the_interrupts_with_the_extra(
    tmp_path: Path,
) -> None:
    """With the Interrupts extra the section and the slots stay."""
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(PLATFORM), encoding="utf-8")
    definition = cal.ProfileDef("x", 1, "rv32im", extras=("Interrupts",))
    harness.apply_profile(path, definition)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    check_in("interrupts", data)
    check_equal(len(data["peripherals"]), 3)


def test_complete_package_adds_only_the_missing_constants(
    tmp_path: Path,
) -> None:
    """Only the constants the package lacks are added."""
    package = tmp_path / "pkg.vhd"
    package.write_text(PACKAGE, encoding="utf-8")
    added = harness.complete_package(package, REFERENCE)
    check_equal(added, ["PLIC_ADDR_WIDTH"])
    text = package.read_text(encoding="utf-8")
    check_in("-- So com interrupcoes.", text)
    check(text.rstrip().endswith("end package demo_pkg;"))
    check_equal(harness.complete_package(package, REFERENCE), [])


def test_the_sources_hash_follows_the_sources(tmp_path: Path) -> None:
    """The hash changes with a source the settings file lists."""
    (tmp_path / "a.vhd").write_text("a", encoding="utf-8")
    qsf = tmp_path / "p.qsf"
    qsf.write_text(
        "set_global_assignment -name VHDL_FILE a.vhd\n", encoding="utf-8"
    )
    first = harness.sources_hash(tmp_path, qsf, [])
    (tmp_path / "a.vhd").write_text("b", encoding="utf-8")
    check(harness.sources_hash(tmp_path, qsf, []) != first)


def synthetic_record(
    definition: cal.ProfileDef,
    coefficients: dict[str, float | None],
) -> dict[str, Any]:
    """Make the record the table's own coefficients would give."""
    spec = cal.spec_of(definition)
    table = fe.CalibrationTable("demo", "alm", coefficients)
    logic, _ = fe.estimate_logic(spec, table, 10240)
    return {
        "id": definition.id,
        "tool": "Quartus fake",
        "sources_hash": "h",
        "revisions": {"Core": "abc"},
        "result": {"logic": round(logic)},
    }


def test_the_fit_recovers_known_coefficients(tmp_path: Path) -> None:
    """A fit of data made from known coefficients recovers them."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    truth: dict[str, float | None] = {
        "core.rv32i": 1000.0,
        "extensions.Zmmul": 100.0,
        "extensions.M": 50.0,
        "extensions.Zicsr": 30.0,
        "cache.icache.c0": -64.0,
        "cache.icache.c1": 2.0,
        "cache.dcache.c0": -96.0,
        "cache.dcache.c1": 3.0,
    }
    records = {d.id: synthetic_record(d, truth) for d in plan.profiles}
    content = cal.fit_table(plan, records)
    flat = fe.flatten(content["coefficients"])
    check_equal(flat["core.rv32i"], 1000.0)
    check_equal(flat["extensions.M"], 50.0)
    check_equal(flat["cache.icache.c1"], 2.0)
    check_equal(flat["cache.icache.c0"], -64.0)
    check(flat["extensions.Zicntr"] is None)
    check_equal(content["error"]["holdout"], ["ic64", "full"])
    check(content["error"]["max_pct"] < MAX_ROUNDING_PCT)
    check_equal(content["error"]["rms_pct"], 0.0)
    check(content["known_fit_check"]["ratio_mid"] > 0)
    check_equal(content["absorbed"], ["peripherals.UART"])


def test_the_fit_needs_a_measured_profile(tmp_path: Path) -> None:
    """A fit with no record is an error."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    with pytest.raises(ValueError, match="no measured"):
        cal.fit_table(plan, {})


def test_the_table_written_by_the_fit_loads_back(tmp_path: Path) -> None:
    """The file the fit writes is a valid table for the estimator."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    truth: dict[str, float | None] = {
        "core.rv32i": 1000.0,
        "extensions.Zmmul": 100.0,
        "extensions.M": 50.0,
        "extensions.Zicsr": 30.0,
        "cache.icache.c1": 2.0,
        "cache.dcache.c1": 3.0,
    }
    records = {d.id: synthetic_record(d, truth) for d in plan.profiles}
    target = tmp_path / "demo.yaml"
    cal.write_table(cal.fit_table(plan, records), target)
    table = fe.load_table(target, fe.DEFAULT_VOCABULARY)
    # Sem os termos c0 a cache de referência fica dentro do núcleo.
    check_equal(table.coefficients["core.rv32i"], 1160.0)
    check(table.logic_error_enabled)


def write_fake_tools(tmp_path: Path) -> tuple[list[str], Path]:
    """Write a fake riscv-tools and a fake quartus_sh."""
    generator = tmp_path / "fake_rt.py"
    generator.write_text(
        "import sys, yaml, pathlib\n"
        "a = sys.argv\n"
        "root = pathlib.Path(a[a.index('--root') + 1])\n"
        "plat = root / a[a.index('--platform') + 1]\n"
        "d = yaml.safe_load(plat.read_text())\n"
        "pkg = root / d['generate']['vhdl']['path']\n"
        "pkg.parent.mkdir(parents=True, exist_ok=True)\n"
        "body = '\\tconstant A : natural := 1;\\n'\n"
        "if 'interrupts' in d:\n"
        "    body += '\\tconstant PLIC_ADDR_WIDTH : natural := 20;\\n'\n"
        "pkg.write_text('package p is\\n' + body + 'end package p;\\n')\n",
        encoding="utf-8",
    )
    quartus = tmp_path / "fake_quartus.sh"
    quartus.write_text(
        "#!/bin/sh\n"
        "mkdir -p output_files\n"
        "printf '; Analysis & Synthesis Resource Usage Summary ;\\n"
        "+---+---+\\n; Resource ; Usage ;\\n+---+---+\\n"
        "; Estimate of Logic utilization (ALMs needed) ; 1234 ;\\n"
        "; I/O pins ; 93 ;\\n+---+---+\\n"
        "; Analysis & Synthesis Summary ;\\n+---+---+\\n"
        "; Analysis & Synthesis Status ; Successful - now ;\\n"
        "; Quartus Prime Version ; 25.1 ;\\n+---+---+\\n'"
        " > output_files/demo.map.rpt\n",
        encoding="utf-8",
    )
    quartus.chmod(quartus.stat().st_mode | stat.S_IXUSR)
    return ["python3", str(generator)], quartus


def make_project(tmp_path: Path) -> Path:
    """Write a tiny project with the files the harness reads."""
    root = tmp_path / "project"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "platform.yaml").write_text(
        yaml.safe_dump(PLATFORM), encoding="utf-8"
    )
    (root / "demo" / "demo.qsf").write_text(
        "set_global_assignment -name VHDL_FILE pkg.vhd\n", encoding="utf-8"
    )
    (root / "demo" / "synth.tcl").write_text("# tcl\n", encoding="utf-8")
    return root


def test_the_harness_measures_and_resumes(tmp_path: Path) -> None:
    """The harness measures, records and skips a current record."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    riscv_tools, quartus = write_fake_tools(tmp_path)
    root = make_project(tmp_path)
    messages: list[str] = []
    settings = cal.Settings(
        project=root,
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "raw",
        lock=tmp_path / "q.lock",
        riscv_tools=tuple(riscv_tools),
        quartus_sh=str(quartus),
        log=messages.append,
    )
    first = cal.run_all(plan, settings, ["base"])
    check_equal(first, {"base": "measured"})
    record = yaml.safe_load((tmp_path / "raw" / "base.yaml").read_text())
    check_equal(record["result"]["logic"], 1234)
    check_equal(record["seed"], 5)
    check_equal(record["added_constants"], ["PLIC_ADDR_WIDTH"])
    check_equal(record["tool"], "Quartus 25.1")
    check_equal(len(record["sources_hash"]), 64)
    check(not (tmp_path / "work" / "base").exists())
    check_equal(cal.run_all(plan, settings, ["base"]), {"base": "current"})
    with pytest.raises(ValueError, match="unknown profile id"):
        cal.run_all(plan, settings, ["nope"])


def test_a_failed_synthesis_names_the_profile(tmp_path: Path) -> None:
    """A synthesis that fails is an error naming the profile."""
    plan = cal.load_profile_list(write_plan(tmp_path))
    riscv_tools, _ = write_fake_tools(tmp_path)
    broken = tmp_path / "broken.sh"
    broken.write_text("#!/bin/sh\necho boom\nexit 3\n", encoding="utf-8")
    broken.chmod(broken.stat().st_mode | stat.S_IXUSR)
    settings = cal.Settings(
        project=make_project(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "raw",
        lock=tmp_path / "q.lock",
        riscv_tools=tuple(riscv_tools),
        quartus_sh=str(broken),
    )
    with pytest.raises(RuntimeError, match="base: synthesis failed"):
        cal.run_all(plan, settings, ["base"])


def test_the_machine_lock_is_exclusive(tmp_path: Path) -> None:
    """A second holder of the lock has to wait."""
    lock = tmp_path / "q.lock"
    waited: list[str] = []
    with cal.machine_lock(lock, waited.append):
        other = lock.open("a")
        with pytest.raises(BlockingIOError):
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        other.close()
    check_equal(waited, [])
