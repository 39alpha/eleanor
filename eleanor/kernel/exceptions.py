from eleanor.exceptions import EleanorError, EleanorWarning
from eleanor.util import require_int


class EleanorKernelError(EleanorError):
    code: int

    def __init__(self, *args: object, code: int | None = None) -> None:
        super().__init__(*args)
        self.code = require_int(code if code is not None else 1, "code")


class EleanorKernelWarning(EleanorWarning): ...


__all__ = [
    "EleanorKernelError",
    "EleanorKernelWarning",
]
