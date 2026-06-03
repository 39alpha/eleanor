from eleanor.exceptions import EleanorException


def test_eleanor_exception_str():
    e = EleanorException("boom")
    assert str(e) == "boom"


def test_eleanor_exception_has_no_code():
    e = EleanorException()
    assert not hasattr(e, "code")
