"""The exit code contract shared by every mdcompose command.

Code 1 and code 2 differ in whose fault the outcome is. Code 1 means mdcompose
worked correctly and is reporting a real condition the user must resolve. Code 2
means mdcompose could not do its job at all.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_ATTENTION = 1
EXIT_INTERNAL = 2


class AttentionError(Exception):
    """A condition the user or the environment must resolve.

    Raised by the core layer, caught once at the CLI boundary, and reported as
    exit code ``EXIT_ATTENTION``. This is an error boundary type, not a control
    flow mechanism: core code never catches it to decide what to do next.

    The message must name the thing at fault, usually a path, so the user can
    act on it without rerunning under a debugger.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
