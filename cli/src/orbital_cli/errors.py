"""Exit codes and the error type every command raises.

The exit codes are a public contract (docs/CLI.md#exit-codes): CI scripts
and agents branch on them, so never renumber an existing code.
"""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1  # unexpected: network failure, 5xx, bug
    USAGE = 2  # bad flags, invalid manifest, missing --yes
    AUTH = 3  # 401 / 403
    NOT_FOUND = 4  # 404, unknown slug
    CONFLICT = 5  # 409
    VALIDATION = 6  # 422
    TIMEOUT = 7  # --wait timed out
    FAILED = 8  # the awaited operation failed (build, rollout, scan gate)


_STATUS_TO_CODE = {
    401: ExitCode.AUTH,
    403: ExitCode.AUTH,
    404: ExitCode.NOT_FOUND,
    409: ExitCode.CONFLICT,
    422: ExitCode.VALIDATION,
}


def code_for_status(status: int) -> ExitCode:
    if status == 400:
        return ExitCode.VALIDATION
    return _STATUS_TO_CODE.get(status, ExitCode.ERROR)


class CliError(Exception):
    """An error reported to the user with a specific exit code."""

    def __init__(
        self, message: str, code: ExitCode = ExitCode.ERROR, *, http_status: int | None = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status

    def to_dict(self) -> dict:
        err: dict = {"code": int(self.code), "message": self.message}
        if self.http_status is not None:
            err["http_status"] = self.http_status
        return {"error": err}


def usage(message: str) -> CliError:
    return CliError(message, ExitCode.USAGE)
