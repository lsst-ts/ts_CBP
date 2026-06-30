"""Public enumerations used by the CBP package."""

import enum


class ErrorCode(enum.IntEnum):
    """Error codes published by the CBP CSC.

    Attributes
    ----------
    CONNECTION_FAILED : `int`
        Connection to the controller failed or was lost.
    TELEMETRY_LOOP_FAILED : `int`
        Telemetry publishing failed.
    PANICKED : `int`
        The controller reported a panic condition.
    MONITOR_LOOP_FAILED : `int`
        Monitor loop failure while reading hardware telemetry.
    REPLY_FAILED : `int`
        Controller reply could not be parsed or was not received.
    """

    CONNECTION_FAILED = enum.auto()
    TELEMETRY_LOOP_FAILED = enum.auto()
    PANICKED = enum.auto()
    MONITOR_LOOP_FAILED = enum.auto()
    REPLY_FAILED = enum.auto()
