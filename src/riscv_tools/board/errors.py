"""The errors of the board identification, one per case of the plan."""


class BoardError(Exception):
    """A board could not be identified, selected or locked.

    Attributes
    ----------
    case : int or None
        The number of the ambiguity case of the identification plan
        (1 to 9) that the error reports, or None.
    """

    def __init__(self, message: str, case: int | None = None) -> None:
        """Build the error.

        Parameters
        ----------
        message : str
            What went wrong and what to do.
        case : int, optional
            The ambiguity case number.
        """
        super().__init__(message)
        self.case = case


class BoardBusyError(BoardError):
    """The lock of the board is held by another process."""

    def __init__(self, message: str) -> None:
        """Build the error (case 9 of the plan).

        Parameters
        ----------
        message : str
            The lock file and the owner it records.
        """
        super().__init__(message, case=9)
