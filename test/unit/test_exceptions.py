from eleanor.exceptions import EleanorError


def test_eleanor_exception_str() -> None:
    e = EleanorError("boom")
    assert str(e) == "boom"


def test_eleanor_exception_has_no_code() -> None:
    e = EleanorError()
    assert not hasattr(e, "code")
