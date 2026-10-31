"""Run a whole manifest against the board, with resume and waiting."""

import json
import subprocess
import time
from typing import Any

from riscv_tools import (
    display,
    quartus_program,
)
from riscv_tools.jtag import jtag_chain_healthy
from riscv_tools.orchestrator.failure import (
    NeedsHumanInterventionError,
    raise_if_hardware_failure,
)
from riscv_tools.orchestrator.runner import (
    RunContext,
    SuiteOptions,
    full_reconfigure_entry,
    run_one,
)

# How often run_suite's wait_for_hardware mode polls `jtagconfig` while
# blocked waiting for a human to physically fix the board.
_HARDWARE_WAIT_POLL_S = 5.0


def _wait_for_hardware_healthy(
    poll_interval_s: float = _HARDWARE_WAIT_POLL_S,
) -> None:
    """Block until the JTAG chain recovers.

    Polls jtag.jtag_chain_healthy. It runs after the message of a
    NeedsHumanInterventionError, only when run_suite was given
    wait_for_hardware=True, so the person fixing the board (typically
    with a power-cycle) can watch this process instead of re-invoking
    it.

    Parameters
    ----------
    poll_interval_s : float, optional
        Seconds between `jtagconfig` checks. Defaults to
        _HARDWARE_WAIT_POLL_S.

    Returns
    -------
    None
        Once jtag_chain_healthy() returns True.
    """
    while not jtag_chain_healthy():
        time.sleep(poll_interval_s)
    print("jtagconfig reports the chain is healthy again; resuming.")


def run_suite(
    ctx: RunContext,
    manifest: list[dict[str, Any]],
    options: SuiteOptions | None = None,
) -> dict[str, bool]:
    """Run every test in manifest against real hardware.

    Compiles and programs the board once, then runs each entry with
    run_one, in order. It stops (without raising) when a test raises
    NeedsHumanInterventionError. With options.results_path, each result
    is saved as soon as it is known, so an interrupted run can resume.

    Parameters
    ----------
    ctx : RunContext
        The shared state.
    manifest : list of dict of {str: Any}
        The tests to run; must be non-empty. With options.reconfigure,
        the ROM of manifest[0] is baked into the initial compile.
    options : SuiteOptions, optional
        The optional behaviors. None means SuiteOptions().

    Returns
    -------
    dict of {str: bool}
        {test_name: passed}, including options.results_so_far. Fewer
        entries than results_so_far plus manifest means the run stopped.

    Raises
    ------
    ValueError
        manifest is empty.
    """
    if not manifest:
        raise ValueError("Manifest is empty; nothing to run")
    suite = _SuiteRun(ctx, manifest, options or SuiteOptions())
    if suite.options.reconfigure and not suite.reconfigure():
        return suite.results
    suite.run_entries()
    return suite.results


class _SuiteRun:
    """The state and steps of one run_suite call."""

    def __init__(
        self,
        ctx: RunContext,
        manifest: list[dict[str, Any]],
        options: SuiteOptions,
    ) -> None:
        self.ctx = ctx
        self.manifest = manifest
        self.options = options
        self.already_done = len(options.results_so_far or {})
        self.results: dict[str, bool] = dict(options.results_so_far or {})

    def persist(self) -> None:
        """Write the results so far, if a results path was given."""
        path = self.options.results_path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.results, indent=2))

    def handle_hardware_stop(
        self, name: str, exc: NeedsHumanInterventionError
    ) -> bool:
        """Report a hardware stop.

        Always persists progress and prints exc. If wait_for_hardware,
        blocks in _wait_for_hardware_healthy and returns True (retry
        the step that just failed) instead of False (stop the suite).

        Parameters
        ----------
        name : str
            The test (or step) that hit the failure.
        exc : NeedsHumanInterventionError
            The failure.

        Returns
        -------
        bool
            True if the caller should retry.
        """
        self.persist()
        wait = self.options.wait_for_hardware
        remaining = len(self.manifest) - (
            len(self.results) - self.already_done
        )
        action = (
            "waiting for the board to come back"
            if wait
            else "stopping the suite"
        )
        print(
            f"\n{name}: {action} ({exc})\n"
            f"This needs a physical power-cycle of the board, not "
            f"another retry. {len(self.results)} test(s) done, "
            f"{remaining} remaining (including this one)."
        )
        if not wait:
            print(
                "Once the board is back (`jtagconfig` shows it healthy "
                "again), re-run the exact same command to resume from "
                "here; completed tests won't be re-run."
            )
            return False
        _wait_for_hardware_healthy()
        return True

    def reconfigure(self) -> bool:
        """Compile and program the board once, before any test.

        Returns
        -------
        bool
            False if the suite must stop on a hardware failure.
        """
        print("Compiling and programming the board once ...")
        already_compiled = self.options.skip_recompile
        while True:
            try:
                self._reconfigure_once(already_compiled)
                return True
            except subprocess.CalledProcessError as exc:
                already_compiled = True
                if not self._can_retry(exc):
                    return False

    def _reconfigure_once(self, already_compiled: bool) -> None:
        """Run one attempt of the initial reconfigure.

        If an earlier attempt finished quartus_sh --flow compile, the
        .sof is known good: the hardware-failure signatures all come
        from quartus_pgm or quartus_stp, which only run after the
        compile. Then only the reprogramming is retried, not another
        recompile of the same design.

        Parameters
        ----------
        already_compiled : bool
            Whether to reprogram the existing .sof only.
        """
        ctx = self.ctx
        if already_compiled:
            quartus_program.program_only(
                hardware_name=ctx.link.hardware_name,
                project_dir=ctx.project_dir,
                sof_file=ctx.cfg["quartus"]["sof_file"],
            )
        else:
            full_reconfigure_entry(
                ctx.cfg,
                ctx.link,
                self.manifest[0],
                ctx.root,
                ctx.project_dir,
            )

    def _can_retry(self, exc: subprocess.CalledProcessError) -> bool:
        """Classify a failure of the initial reconfigure.

        There is no retry path for the initial reconfigure: either the
        failure matches a known JTAG or cable signature and is handled
        like every other call site, or it is a real build or hardware
        problem and propagates.

        Parameters
        ----------
        exc : subprocess.CalledProcessError
            The failure.

        Returns
        -------
        bool
            True to retry, False to stop the suite.

        Raises
        ------
        subprocess.CalledProcessError
            exc itself, when it is not a known hardware failure.
        """
        try:
            raise_if_hardware_failure(exc)
        except NeedsHumanInterventionError as hi_exc:
            return self.handle_hardware_stop(self.manifest[0]["name"], hi_exc)
        raise exc

    def run_entries(self) -> None:
        """Run every manifest entry, stopping on a hardware failure."""
        # 1-based position across the ORIGINAL manifest, not just this
        # invocation's (possibly resumed/already-filtered) one, a
        # resume restarting the header count at "[1/N]" would
        # understate both how far along the suite actually is and what
        # N even means.
        total = self.already_done + len(self.manifest)
        show = bool(
            self.ctx.cfg.get("orchestrator", {}).get("board_display", False)
        )
        if show and not self.already_done:
            # a new session starts without a failure; a resumed one
            # keeps the flag it had
            display.write_fail(self.ctx.link, False)
        for i, entry in enumerate(self.manifest, start=self.already_done + 1):
            if show:
                # the number of the program in the session, in
                # decimal, on the six digits
                display.write_display(self.ctx.link, display.encode_test(i))
            if not self._run_entry(entry, (i, total), show):
                return
            self.persist()

    def _run_entry(
        self, entry: dict[str, Any], position: tuple[int, int], show: bool
    ) -> bool:
        """Run one entry, retrying after a hardware stop if asked.

        Parameters
        ----------
        entry : dict of {str: Any}
            The manifest entry.
        position : tuple of (int, int)
            (index, total) of the entry in the whole suite.
        show : bool
            Whether the board display follows the suite.

        Returns
        -------
        bool
            False if the suite must stop.
        """
        name = entry["name"]
        while True:
            try:
                passed = run_one(
                    self.ctx,
                    entry,
                    position=position,
                    duration=self.options.durations,
                )
            except NeedsHumanInterventionError as exc:
                if self.handle_hardware_stop(name, exc):
                    continue
                return False
            self.results[name] = passed
            if show and not passed:
                # the first red LED stays lit once any program has
                # failed
                display.write_fail(self.ctx.link, True)
            return True
