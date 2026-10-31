"""Recognize the JTAG and cable failures that no retry can fix."""

import subprocess

# Substrings of real Quartus/jtagd error text that mean the JTAG chain
# or cable itself is unreachable, never that the design misbehaved or
# the test failed. Matched case-insensitively against the stdout and
# stderr of a CalledProcessError.
_HARDWARE_FAILURE_SIGNATURES = (
    "can't scan jtag chain",
    "jtag chain broken",
    "unable to read device chain",
    "programming hardware cable not detected",
    "hardware is not found",
    "no editable memory instance",
    "error when scanning hardware",
)


class NeedsHumanInterventionError(Exception):
    """A JTAG/hardware failure that no retry can fix.

    Raised by _run_with_recovery when the error text of a failed
    subprocess matches a known "board or cable unreachable" signature.
    An ordinary test timeout, where every JTAG operation succeeded, is
    not one of these, since it may be a real CPU or test bug. run_suite
    catches this, saves progress and stops, because nothing is left to
    try except a human power-cycling the board.
    """


def _is_hardware_failure(exc: subprocess.CalledProcessError) -> bool:
    """Check whether exc matches a known JTAG/cable failure.

    Only the output of exc itself is checked for the signature.

    Parameters
    ----------
    exc : subprocess.CalledProcessError
        A failure from jtag.link.run/run_tcl or
        quartus_program._run_captured, both always populate
        .stdout/.stderr with real text now (see their own docstrings).

    Returns
    -------
    bool
        True if exc's stdout+stderr contain one of
        _HARDWARE_FAILURE_SIGNATURES; this specific test's own retry
        tiers are exhausted, and neither would a trying-again-later
        retry help without a human power-cycling the board first.
        False for any other failure (e.g. a nonzero exit with
        different or no output), treated as an ordinary test failure,
        not grounds to stop the whole suite.
    """
    text = f"{exc.stdout or ''}\n{exc.stderr or ''}".lower()
    return any(sig in text for sig in _HARDWARE_FAILURE_SIGNATURES)


def raise_if_hardware_failure(exc: subprocess.CalledProcessError) -> None:
    """Re-raise exc as NeedsHumanInterventionError if it looks like one.

    It does nothing otherwise. The classification is in
    _is_hardware_failure.
    """
    if _is_hardware_failure(exc):
        raise NeedsHumanInterventionError(str(exc)) from exc
