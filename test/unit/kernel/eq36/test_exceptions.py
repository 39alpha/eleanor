from eleanor.exceptions import EleanorError
from eleanor.kernel.eq36.exceptions import Eq36Error
from eleanor.kernel.exceptions import EleanorKernelError


def test_eq36_exception_inheritance_and_formatting() -> None:
    e = Eq36Error("eq36 failed", code=29)

    assert isinstance(e, EleanorError)
    assert isinstance(e, EleanorKernelError)
    assert e.code == 29
    assert str(e) == "eq36 failed"
