from eleanor.exceptions import EleanorException
from eleanor.kernel.exceptions import EleanorKernelException


def test_eleanor_kernel_exception_is_eleanor_exception() -> None:
    e = EleanorKernelException("kernel boom", code=12)

    assert isinstance(e, EleanorException)
    assert e.code == 12
    assert str(e) == "kernel boom"
