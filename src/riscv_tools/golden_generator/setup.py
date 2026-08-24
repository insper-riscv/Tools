"""Builds and keeps vendor/riscv-isa-sim (Spike) up to date, so
generate_golden always has a working `spike` binary to run — without
requiring a human to remember `./configure && make` or notice the
submodule pointer moved.

Distinct concern from core.py's generate_golden: this is about
producing/maintaining the `spike` binary itself, not running programs
under it.
"""
import os
import shutil
import subprocess
from pathlib import Path

# Overrides where the riscv-isa-sim checkout lives, instead of this
# repo's own vendor/riscv-isa-sim submodule — set this in CI to point
# at a long-lived cache directory (e.g. actions/cache) so a fresh
# checkout of riscv-tools doesn't re-clone+rebuild Spike from scratch
# on every run, burning bandwidth and CI minutes for no reason.
DIR_ENV_VAR = "RISCV_ISA_SIM_DIR"
_REPO_URL = "https://github.com/riscv-software-src/riscv-isa-sim.git"


def _submodule_dir() -> Path:
    """Path to the riscv-isa-sim checkout setup()/update() operate on.

    Args:
        None.

    Returns:
        Path(os.environ[RISCV_ISA_SIM_DIR]) if that's set (see
        DIR_ENV_VAR) — any directory, doesn't have to be this repo's
        submodule, e.g. a CI cache path. Otherwise falls back to this
        repo's own vendor/riscv-isa-sim submodule, resolved relative to
        this installed package's own location (assumes the standard
        riscv-tools repo layout:
        src/riscv_tools/golden_generator/setup.py -> repo
        root/vendor/riscv-isa-sim). Doesn't check either path actually
        exists; see setup()/update() for that.
    """
    override = os.environ.get(DIR_ENV_VAR)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "vendor" / "riscv-isa-sim"


def _pinned_commit() -> str | None:
    """The commit this repo's OWN vendor/riscv-isa-sim submodule is
    pinned to — used to check out a matching commit when
    DIR_ENV_VAR points somewhere that needs cloning from scratch (a
    cold CI cache), so an override directory still ends up running the
    same Spike version this repo actually vendors, not just whatever a
    fresh clone's default branch happens to be.

    Args:
        None.

    Returns:
        The pinned commit hash, or None if it can't be determined
        (e.g. running outside a git checkout of riscv-tools itself, or
        the submodule was never initialized there either) — callers
        should treat that as "no pin available", not an error.
    """
    repo_root = Path(__file__).resolve().parents[3]
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "submodule", "status", "vendor/riscv-isa-sim"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not out:
        return None
    return out.lstrip("+-U ").split()[0]


def _ensure_checkout(submodule_dir: Path) -> None:
    """Clones riscv-isa-sim into submodule_dir if nothing's checked out
    there yet — only meant to fire when DIR_ENV_VAR points somewhere
    other than this repo's own submodule (a cache directory can
    legitimately start out empty, e.g. a CI cache miss). This repo's
    own vendor/riscv-isa-sim is never auto-cloned into this way — it's
    a real git submodule and should be populated with `git submodule
    update --init`, not a parallel plain clone that would confuse git's
    own submodule bookkeeping.

    Args:
        submodule_dir: Directory to ensure has a riscv-isa-sim checkout
            in it.

    Returns:
        None.

    Raises:
        subprocess.CalledProcessError: the clone or checkout failed.
    """
    if (submodule_dir / "configure").is_file():
        return
    submodule_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", _REPO_URL, str(submodule_dir)], check=True)
    commit = _pinned_commit()
    if commit:
        subprocess.run(["git", "-C", str(submodule_dir), "checkout", commit], check=True)


def _build_dir(submodule_dir: Path) -> Path:
    """Where vendor/riscv-isa-sim is configured+built (out-of-tree).

    Args:
        submodule_dir: Path to the vendor/riscv-isa-sim submodule (see
            _submodule_dir).

    Returns:
        submodule_dir / "build".
    """
    return submodule_dir / "build"


def _built_commit_marker(build_dir: Path) -> Path:
    """Where the commit hash a build was made from is recorded, so
    update() can tell whether the submodule has moved since.

    Args:
        build_dir: Path to the out-of-tree build directory (see
            _build_dir).

    Returns:
        build_dir / ".built_commit".
    """
    return build_dir / ".built_commit"


def _current_commit(submodule_dir: Path) -> str:
    """Reads the submodule's currently checked-out commit hash.

    Args:
        submodule_dir: Path to the vendor/riscv-isa-sim submodule.

    Returns:
        The full commit hash `git rev-parse HEAD` reports inside
        submodule_dir.

    Raises:
        subprocess.CalledProcessError: submodule_dir isn't a git
            checkout (e.g. the submodule was never initialized).
    """
    return subprocess.run(
        ["git", "-C", str(submodule_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _check_dependencies() -> None:
    """Checks for the one build dependency Spike's ./configure hard-fails
    without (device-tree-compiler). Boost is also used but is optional —
    configure degrades gracefully (with a warning) if it's missing, so
    it isn't checked here.

    Args:
        None.

    Returns:
        None.

    Raises:
        RuntimeError: `dtc` isn't on PATH.
    """
    if shutil.which("dtc") is None:
        raise RuntimeError(
            "device-tree-compiler (dtc) not found — required by Spike's ./configure. "
            "Install it (e.g. `sudo apt-get install device-tree-compiler`) and retry."
        )


def _build(submodule_dir: Path) -> Path:
    """Configures and builds Spike from source, recording the commit it
    was built from.

    Args:
        submodule_dir: Path to the vendor/riscv-isa-sim submodule.

    Returns:
        Path to the resulting `spike` binary.

    Raises:
        RuntimeError: a required build dependency is missing (see
            _check_dependencies).
        subprocess.CalledProcessError: configure or make failed.
    """
    _check_dependencies()
    build_dir = _build_dir(submodule_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(["../configure"], cwd=build_dir, check=True)
    subprocess.run(["make", f"-j{os.cpu_count() or 1}"], cwd=build_dir, check=True)

    _built_commit_marker(build_dir).write_text(_current_commit(submodule_dir) + "\n")
    return build_dir / "spike"


def setup(spike_bin: str = "spike") -> Path:
    """Ensures a working `spike` binary is available, building
    vendor/riscv-isa-sim from source if nothing usable is found
    already.

    Args:
        spike_bin: The project's configured `emulator.spike_bin` (name
            or path). If this already resolves to something runnable
            (on PATH, or an existing file), it's returned as-is and
            nothing is built — an already-available Spike (e.g. a
            system package) is left alone. Defaults to "spike".

    Returns:
        Path to a ready-to-use `spike` binary: either spike_bin
        resolved, or <checkout>/build/spike after building it — where
        <checkout> is $RISCV_ISA_SIM_DIR if set (see DIR_ENV_VAR),
        else this repo's own vendor/riscv-isa-sim.

    Raises:
        FileNotFoundError: spike_bin doesn't already resolve to
            something runnable, DIR_ENV_VAR isn't set, and this repo's
            own vendor/riscv-isa-sim isn't checked out (submodule not
            initialized — run `git submodule update --init
            --recursive`).
        RuntimeError: a required build dependency is missing.
        subprocess.CalledProcessError: cloning/checking out
            DIR_ENV_VAR's target failed, or configure/make failed.
    """
    found = shutil.which(spike_bin)
    if found:
        return Path(found)
    if Path(spike_bin).is_file():
        return Path(spike_bin)

    submodule_dir = _submodule_dir()

    if os.environ.get(DIR_ENV_VAR):
        # An override directory (e.g. a CI cache) is fair game to
        # populate ourselves — a cache miss legitimately starts empty.
        _ensure_checkout(submodule_dir)
    elif not (submodule_dir / "configure").is_file():
        # An UNinitialized submodule still leaves an empty directory
        # behind (git creates the path but never checks anything out
        # into it), so is_dir() alone can't tell "not initialized"
        # from "checked out" — configure only exists once the
        # submodule's actual content is there. Not auto-cloned here:
        # this IS the repo's own submodule, meant to be populated via
        # `git submodule update`, not a parallel plain clone.
        raise FileNotFoundError(
            f"{spike_bin!r} not found, and {submodule_dir} isn't checked out — "
            "run `git submodule update --init --recursive`"
        )

    built = _build_dir(submodule_dir) / "spike"
    if built.is_file():
        return built
    return _build(submodule_dir)


def update() -> bool:
    """Rebuilds Spike if its checkout's currently checked-out commit has
    moved since the binary at build/spike was built from (e.g. after
    `git submodule update` pulled in a newer pin, or a CI cache
    directory got refreshed with a newer commit — see DIR_ENV_VAR) —
    so a stale binary never silently keeps running against an old
    Spike version once the source has moved on.

    Args:
        None.

    Returns:
        True if a rebuild ran, False if the existing build (if any) was
        already current. Nothing has been built yet if build/spike
        doesn't exist — call setup() first in that case, this returns
        False without building.

    Raises:
        RuntimeError: a required build dependency is missing.
        subprocess.CalledProcessError: configure or make failed, or
            resolving the submodule's current commit failed.
    """
    submodule_dir = _submodule_dir()
    build_dir = _build_dir(submodule_dir)
    built = build_dir / "spike"
    if not built.is_file():
        return False

    marker = _built_commit_marker(build_dir)
    current = _current_commit(submodule_dir)
    if marker.is_file() and marker.read_text().strip() == current:
        return False

    _build(submodule_dir)
    return True
