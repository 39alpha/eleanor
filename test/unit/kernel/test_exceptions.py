from eleanor.exceptions import EleanorError
from eleanor.kernel.exceptions import EleanorKernelError


def test_eleanor_kernel_exception_is_eleanor_exception() -> None:
    e = EleanorKernelError("kernel boom", code=12)

    assert isinstance(e, EleanorError)
    assert e.code == 12
    assert str(e) == "kernel boom"
