import enum


class ErrorCode(enum.IntEnum):
    CONNECTION_FAILED = enum.auto()
    TELEMETRY_LOOP_FAILED = enum.auto()
    PANICKED = enum.auto()
