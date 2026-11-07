"""Measure the profiles of a family with the project's compile command.

For each profile the harness copies the project to a work directory,
writes the profile into the copy's ``platform.yaml``, regenerates the
package of the memory map with ``generate-memory-map`` and runs the
compile script of the project in synthesis only (``quartus_map``), under
the lock of the machine. It does not synthesize in any other way: the
script is the one the project already has. The summary of each run goes
to a record with the seed, the hash of the sources and the version of
the Quartus, in YAML so it can be versioned.
"""

import fcntl
import hashlib
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.calibration.profiles import ProfileDef, ProfileList
from riscv_tools.quartus_program.core import CompileOptions, compile_command
from riscv_tools.quartus_reports import (
    ResourceUsage,
    parse_fit_report,
    parse_map_report,
    succeeded,
)

IGNORED = (".git", ".venv", "build", "db", "output_files", "incremental_db")
CONSTANT = re.compile(
    r"((?:[ \t]*--[^\n]*\n)*[ \t]*constant\s+(\w+)\s*:[^;]*;\n)", re.I
)
QSF_FILE = re.compile(
    r"^set_global_assignment\s+-name\s+"
    r"(?:VHDL_FILE|VERILOG_FILE|SYSTEMVERILOG_FILE|SDC_FILE|QIP_FILE|"
    r"MIF_FILE)\s+(\S+)",
    re.M,
)
INTERRUPT_PERIPHERALS = ("CLINT", "PLIC")
QUARTUS_TIMEOUT_S = 3600
Log = Callable[[str], None]


def _no_log(_: str) -> None:
    """Discard a message."""


@dataclass(frozen=True)
class Settings:
    """Where the harness works and which tools it calls.

    Parameters
    ----------
    project : Path
        Root of the original project; it is never changed.
    work_dir : Path
        Directory for the throwaway copies.
    out_dir : Path
        Directory of the raw records.
    lock : Path
        Lock file of the machine's Quartus.
    riscv_tools : tuple of str
        Command that starts ``riscv-tools``.
    quartus_sh : str
        The ``quartus_sh`` executable.
    keep : bool
        Keep the work copies (for debugging).
    log : callable
        Receives progress messages.
    stop_after : str
        ``"map"`` (synthesis only) or ``"fit"``; with ``"fit"`` the
        record also carries what the fitter reported, to measure the
        ratio between the two.
    """

    project: Path
    work_dir: Path
    out_dir: Path
    lock: Path
    riscv_tools: tuple[str, ...] = ("riscv-tools",)
    quartus_sh: str = "quartus_sh"
    keep: bool = False
    log: Log = field(default=_no_log)
    stop_after: str = "map"


@contextmanager
def machine_lock(path: Path, log: Log = _no_log) -> Generator[None]:
    """Hold the exclusive lock of the machine's Quartus.

    Parameters
    ----------
    path : Path
        Lock file, ``/tmp/quartus-<host>.lock``; the same one the other
        tracks take with ``flock``.
    log : callable, optional
        Receives a message when the lock is not free at once.

    Yields
    ------
    None
        While the lock is held.
    """
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(f"waiting for {path}")
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def copy_project(root: Path, dest: Path) -> None:
    """Copy the project without version control or build output.

    Parameters
    ----------
    root : Path
        Root of the project (the parent repository with its modules).
    dest : Path
        New directory; it must not exist.
    """
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns(*IGNORED))


def apply_profile(platform: Path, definition: ProfileDef) -> None:
    """Write a profile into a ``platform.yaml`` (a copy of it).

    Without the Interrupts extra the ``interrupts`` section and the
    CLINT and PLIC slots go away, as the generator requires.

    Parameters
    ----------
    platform : Path
        The ``platform.yaml`` of the work copy.
    definition : ProfileDef
        The profile.
    """
    data = cast(
        "dict[str, Any]", yaml.safe_load(platform.read_text(encoding="utf-8"))
    )
    data["profile"] = definition.profile
    data["extras"] = list(definition.extras)
    memory = cast("dict[str, Any]", data["memory"])
    for name, kbit in (
        ("icache", definition.icache_kbit),
        ("dcache", definition.dcache_kbit),
    ):
        memory[name] = {"enabled": True, "size_bits": kbit * 1024}
    if "Interrupts" not in definition.extras:
        data.pop("interrupts", None)
        data["peripherals"] = [
            item
            for item in data["peripherals"]
            if item["name"] not in INTERRUPT_PERIPHERALS
        ]
    platform.write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def complete_package(package: Path, reference: str) -> list[str]:
    """Add to a generated package the constants the top still reads.

    The top of the project reads the constants of the interrupts
    (``PLIC_ADDR_WIDTH``, ``IRQ_*``) even when the profile has none, so
    a package generated without them does not elaborate. The missing
    declarations come from the package of the unchanged platform.

    Parameters
    ----------
    package : Path
        The generated package of the work copy.
    reference : str
        Text of the package generated from the unchanged platform.

    Returns
    -------
    list of str
        Names of the constants added.
    """
    text = package.read_text(encoding="utf-8")
    present = {name.lower() for _, name in CONSTANT.findall(text)}
    added = [
        (block, name)
        for block, name in CONSTANT.findall(reference)
        if name.lower() not in present
    ]
    if added:
        end = text.rindex("end package")
        text = text[:end] + "".join(b for b, _ in added) + text[end:]
        package.write_text(text, encoding="utf-8")
    return [name for _, name in added]


def sources_hash(project: Path, qsf: Path, extra: Sequence[Path]) -> str:
    """Hash the sources the Quartus reads.

    Parameters
    ----------
    project : Path
        Root of the (work) project.
    qsf : Path
        Settings file; its file assignments name the sources.
    extra : sequence of Path
        Files that shape the run without being in the settings file,
        such as the ``platform.yaml``.

    Returns
    -------
    str
        SHA-256 over the relative path and the bytes of each file.
    """
    names = {
        (qsf.parent / item).resolve()
        for item in QSF_FILE.findall(qsf.read_text(encoding="utf-8"))
    }
    names |= {path.resolve() for path in (qsf, *extra)}
    digest = hashlib.sha256()
    for path in sorted(names):
        if path.is_file():
            digest.update(str(path.relative_to(project.resolve())).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    """Run git in ``root``; None when it fails."""
    done = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout if done.returncode == 0 else None


def revisions(root: Path) -> dict[str, str]:
    """Read the commit of the project and of each of its modules.

    Parameters
    ----------
    root : Path
        Root of the original project (a git repository).

    Returns
    -------
    dict of {str: str}
        ``"."`` and each submodule path to its commit; empty when git
        cannot tell.
    """
    head = _git(root, "rev-parse", "HEAD")
    modules = _git(root, "submodule", "status")
    if head is None or modules is None:
        return {}
    result = {".": head.strip()}
    for line in modules.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) > 1:
            result[parts[1]] = parts[0]
    return result


def run_generate(
    riscv_tools: Sequence[str], root: Path, platform: str
) -> None:
    """Regenerate the files of the memory map of a work copy.

    Parameters
    ----------
    riscv_tools : sequence of str
        Command that starts ``riscv-tools`` (a container wrapper, for
        instance).
    root : Path
        Root of the work copy.
    platform : str
        Platform YAML relative to the root.

    Raises
    ------
    RuntimeError
        When the generator fails.
    """
    done = subprocess.run(
        [
            *riscv_tools,
            "--root",
            str(root),
            "generate-memory-map",
            "--platform",
            platform,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        msg = f"generate-memory-map failed: {done.stdout}{done.stderr}"
        raise RuntimeError(msg)


def _package_path(work: Path, platform: str) -> Path:
    """Locate the generated VHDL package named by the platform."""
    data = cast(
        "Mapping[str, Any]",
        yaml.safe_load((work / platform).read_text(encoding="utf-8")),
    )
    vhdl = cast("Mapping[str, Any]", data["generate"])["vhdl"]
    return work / str(cast("Mapping[str, Any]", vhdl)["path"])


def materialize(
    plan: ProfileList,
    definition: ProfileDef,
    work: Path,
    riscv_tools: Sequence[str],
) -> list[str]:
    """Write a profile into a work copy and regenerate its package.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    definition : ProfileDef
        The profile.
    work : Path
        Work copy of the project.
    riscv_tools : sequence of str
        Command that starts ``riscv-tools``.

    Returns
    -------
    list of str
        Constants added to the package by complete_package.
    """
    run_generate(riscv_tools, work, plan.platform)
    package = _package_path(work, plan.platform)
    reference = package.read_text(encoding="utf-8")
    apply_profile(work / plan.platform, definition)
    run_generate(riscv_tools, work, plan.platform)
    return complete_package(package, reference)


def generate_project(
    plan: ProfileList, work: Path, riscv_tools: Sequence[str]
) -> tuple[Path, str]:
    """Write the Quartus project of the board with ``board generate``.

    The package of the memory map of the work copy is a source of the
    project: it is the component named in ``plan.targets``.

    Parameters
    ----------
    plan : ProfileList
        The family's plan, with ``board`` and ``targets``.
    work : Path
        Work copy of the project.
    riscv_tools : sequence of str
        Command that starts ``riscv-tools``.

    Returns
    -------
    tuple
        The folder of the generated project and the name of its
        revision.

    Raises
    ------
    RuntimeError
        When the generator fails or leaves no project file.
    """
    out = work / "build"
    done = subprocess.run(
        [
            *riscv_tools,
            "--root",
            str(work),
            "--board",
            plan.board,
            "board",
            "generate",
            "--platform",
            plan.platform,
            "--out",
            str(out),
            "--accept-inferred-pins",
            *(item for name in plan.targets for item in ("--target", name)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    projects = sorted(out.glob("*/*.qpf"))
    if done.returncode != 0 or len(projects) != 1:
        msg = f"board generate failed: {done.stdout}{done.stderr}"
        raise RuntimeError(msg)
    return projects[0].parent, projects[0].stem


def _project(
    plan: ProfileList, work: Path, riscv_tools: Sequence[str]
) -> tuple[Path, str, Path]:
    """Find the folder, the revision and the settings file of a run."""
    if plan.board:
        folder, revision = generate_project(plan, work, riscv_tools)
        return folder, revision, folder / f"{revision}.qsf"
    qsf = work / plan.qsf
    return (work / plan.synth).parent, qsf.stem, qsf


def run_synthesis(
    plan: ProfileList,
    definition: ProfileDef,
    work: Path,
    settings: Settings,
    project: tuple[Path, str] | None = None,
) -> tuple[list[str], str]:
    """Run the compile command of the project up to the stop point.

    With a hand-written project this is its script; with a generated
    one it is the single compile script that ``program --stop-after``
    runs, so there is no other way to synthesize.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    definition : ProfileDef
        The profile; its generics go to the script as ``NAME=value``.
    work : Path
        Work copy of the project.
    settings : Settings
        Gives the ``quartus_sh`` executable and the stop point.
    project : tuple, optional
        Folder and revision of a generated project.

    Returns
    -------
    tuple
        The command that ran and its log.

    Raises
    ------
    RuntimeError
        When the script fails or times out.
    """
    if project is not None:
        folder, revision = project
        command = compile_command(
            revision,
            CompileOptions(
                seed=plan.seed,
                generics=tuple(definition.generics.items()),
                stop_after=settings.stop_after,
                compile_only=True,
            ),
        )
        command[0] = settings.quartus_sh
    else:
        script = work / plan.synth
        folder = script.parent
        command = [
            settings.quartus_sh,
            "-t",
            script.name,
            str(plan.seed),
            settings.stop_after,
            *(f"{k}={v}" for k, v in definition.generics.items()),
        ]
    try:
        done = subprocess.run(
            command,
            cwd=folder,
            capture_output=True,
            text=True,
            check=False,
            timeout=QUARTUS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as error:
        msg = f"{definition.id}: synthesis timed out"
        raise RuntimeError(msg) from error
    if done.returncode != 0:
        tail = "\n".join(done.stdout.splitlines()[-15:])
        msg = f"{definition.id}: synthesis failed\n{tail}"
        raise RuntimeError(msg)
    return command, done.stdout


def read_synthesis(folder: Path) -> ResourceUsage:
    """Read the synthesis reports a run left next to the project.

    Parameters
    ----------
    folder : Path
        Folder of the Quartus project (its ``output_files`` has them).

    Returns
    -------
    ResourceUsage
        The resources after the synthesis.

    Raises
    ------
    RuntimeError
        When the report is missing or the synthesis did not succeed.
    """
    output = folder / "output_files"
    reports = sorted(output.glob("*.map.rpt"))
    if not reports:
        msg = f"no map.rpt in {output}"
        raise RuntimeError(msg)
    report = reports[0]
    summary = report.with_suffix(".summary")
    usage = parse_map_report(
        report.read_text(encoding="utf-8", errors="replace"),
        summary.read_text(encoding="utf-8") if summary.exists() else None,
    )
    if not succeeded(usage) or usage.logic is None:
        msg = f"{report}: synthesis did not succeed"
        raise RuntimeError(msg)
    return usage


def read_fit(folder: Path) -> ResourceUsage:
    """Read the fitter reports a run left next to the project.

    Parameters
    ----------
    folder : Path
        Folder of the Quartus project.

    Returns
    -------
    ResourceUsage
        The resources after the fitter.

    Raises
    ------
    RuntimeError
        When the report is missing or the fitter did not succeed.
    """
    output = folder / "output_files"
    reports = sorted(output.glob("*.fit.rpt"))
    summaries = sorted(output.glob("*.fit.summary"))
    if not reports:
        msg = f"no fit.rpt in {output}"
        raise RuntimeError(msg)
    usage = parse_fit_report(
        reports[0].read_text(encoding="utf-8", errors="replace"),
        summaries[0].read_text(encoding="utf-8") if summaries else None,
    )
    if not succeeded(usage) or usage.logic is None:
        msg = f"{reports[0]}: fitter did not succeed"
        raise RuntimeError(msg)
    return usage


def record_of(
    plan: ProfileList,
    definition: ProfileDef,
    usage: ResourceUsage,
    facts: Mapping[str, Any],
    fitted: ResourceUsage | None = None,
) -> dict[str, Any]:
    """Build the raw record of a measurement.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    definition : ProfileDef
        The profile.
    usage : ResourceUsage
        What the synthesis reported.
    facts : mapping
        ``sources_hash``, ``revisions``, ``added_constants``,
        ``command`` and ``elapsed_s``.
    fitted : ResourceUsage, optional
        What the fitter reported; adds ``fit_result``.

    Returns
    -------
    dict of {str: Any}
        The record, in the order the file keeps.
    """

    def amount(value: Any) -> int | None:
        return None if value is None else int(value.used)

    record = {
        "id": definition.id,
        "group": definition.group,
        "family": plan.family,
        "unit": plan.unit,
        "profile": definition.profile,
        "extras": list(definition.extras),
        "icache_kbit": definition.icache_kbit,
        "dcache_kbit": definition.dcache_kbit,
        "generics": dict(definition.generics),
        "holdout": definition.holdout,
        "seed": plan.seed,
        "tool": f"Quartus {usage.meta.get('version', '?')}",
        "device": usage.meta.get("device"),
        "measured_on": date.today().isoformat(),
        **{key: facts[key] for key in facts},
        "result": {
            "logic": amount(usage.logic),
            "registers": usage.registers,
            "ram_bits": amount(usage.ram_bits),
            "multipliers": amount(usage.multipliers),
            "plls": amount(usage.plls),
            "pins": amount(usage.pins),
        },
        "entities": [
            {
                "name": item.name,
                "depth": item.depth,
                "luts": item.luts,
                "registers": item.registers,
                "memory_bits": item.memory_bits,
            }
            for item in usage.entities
            if item.depth <= 1
        ],
    }
    if fitted is not None:
        record["fit_result"] = {
            "logic": amount(fitted.logic),
            "registers": fitted.registers,
            "ram_bits": amount(fitted.ram_bits),
            "multipliers": amount(fitted.multipliers),
            "plls": amount(fitted.plls),
            "pins": amount(fitted.pins),
        }
    return record


def is_current(
    path: Path,
    seed: int,
    digest: str,
    generics: Any,
    with_fit: bool = False,
) -> bool:
    """Tell whether a record already holds this exact measurement.

    A run that stops after the fitter needs the fitter's numbers too.
    """
    if not path.exists():
        return False
    old = cast(
        "Mapping[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return (
        old.get("sources_hash") == digest
        and old.get("seed") == seed
        and old.get("generics") == dict(generics)
        and (not with_fit or "fit_result" in old)
    )


def measure(
    plan: ProfileList,
    definition: ProfileDef,
    settings: Settings,
) -> str:
    """Measure one profile and write its record.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    definition : ProfileDef
        The profile.
    settings : Settings
        Where the project, the work area and the tools are.

    Returns
    -------
    str
        ``"measured"`` or ``"current"`` (a record of this exact
        measurement already existed).
    """
    work = settings.work_dir / definition.id
    if work.exists():
        shutil.rmtree(work)
    copy_project(settings.project, work)
    try:
        added = materialize(plan, definition, work, settings.riscv_tools)
        folder, revision, qsf = _project(plan, work, settings.riscv_tools)
        digest = sources_hash(work, qsf, [work / plan.platform])
        target = settings.out_dir / f"{definition.id}.yaml"
        with_fit = settings.stop_after == "fit"
        if is_current(
            target, plan.seed, digest, definition.generics, with_fit
        ):
            return "current"
        started = time.monotonic()
        with machine_lock(settings.lock, settings.log):
            command, _ = run_synthesis(
                plan,
                definition,
                work,
                settings,
                (folder, revision) if plan.board else None,
            )
        usage = read_synthesis(folder)
        fitted = read_fit(folder) if with_fit else None
        facts = {
            "sources_hash": digest,
            "revisions": revisions(settings.project),
            "added_constants": added,
            "command": command,
            "elapsed_s": round(time.monotonic() - started),
        }
        settings.out_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(
                record_of(plan, definition, usage, facts, fitted),
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    finally:
        if not settings.keep:
            shutil.rmtree(work, ignore_errors=True)
    return "measured"


def run_all(
    plan: ProfileList,
    settings: Settings,
    only: Sequence[str] = (),
) -> dict[str, str]:
    """Measure the profiles of the plan one after the other.

    A profile whose record already holds the same sources, seed and
    generics is skipped, so an interrupted run resumes.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    settings : Settings
        Where the project, the work area and the tools are.
    only : sequence of str, optional
        Ids to measure; all of them when empty.

    Returns
    -------
    dict of {str: str}
        Profile id to ``"measured"`` or ``"current"``.

    Raises
    ------
    ValueError
        When an id of ``only`` is not in the plan.
    """
    ids = {item.id for item in plan.profiles}
    unknown = [name for name in only if name not in ids]
    if unknown:
        msg = f"unknown profile id(s): {', '.join(unknown)}"
        raise ValueError(msg)
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    outcome: dict[str, str] = {}
    for definition in plan.profiles:
        if only and definition.id not in only:
            continue
        settings.log(f"profile {definition.id}")
        outcome[definition.id] = measure(plan, definition, settings)
        settings.log(f"  {outcome[definition.id]}")
    return outcome
