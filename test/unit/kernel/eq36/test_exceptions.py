from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.exceptions import Eq36Exception
from eleanor.kernel.exceptions import EleanorKernelException


def test_eq36_exception_inheritance_and_formatting() -> None:
    e = Eq36Exception("eq36 failed", code=29)

    assert isinstance(e, EleanorException)
    assert isinstance(e, EleanorKernelException)
    assert e.code == 29
    assert str(e) == "eq36 failed"
