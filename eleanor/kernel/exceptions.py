from eleanor.exceptions import EleanorException
from eleanor.util import require_int


class EleanorKernelException(EleanorException):
    code: int

    def __init__(self, *args: object, code: int | None = None) -> None:
        super().__init__(*args)
        self.code = require_int(code if code is not None else 1, "code")


__all__ = ["EleanorKernelException"]
