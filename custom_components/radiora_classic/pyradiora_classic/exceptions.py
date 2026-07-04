"""Exception hierarchy for pyradiora-classic."""


class RadioRAError(Exception):
    """Base exception for all pyradiora-classic errors."""


class RadioRAConnectionError(RadioRAError):
    """Failed to establish connection."""


class RadioRAConnectionLost(RadioRAError):
    """Connection was lost during operation."""


class RadioRATimeoutError(RadioRAError):
    """Operation timed out waiting for response."""


class RadioRAProtocolError(RadioRAError):
    """Received malformed or unexpected protocol data."""


class RadioRACommandError(RadioRAError):
    """Controller returned '!' — the command was not recognized.

    This indicates a protocol error: the command string was malformed
    or the RA-RS232 firmware doesn't support it. It does NOT indicate
    a hardware failure or communication error.
    """
