import pytest
from eleanor.cli.gen import FORMATS, validate_template


@pytest.mark.parametrize("ref_fmt", FORMATS)
@pytest.mark.parametrize("other_fmt", FORMATS)
def test_config_formats_agree(ref_fmt: str, other_fmt: str) -> None:
    ref = validate_template("config", ref_fmt)
    other = validate_template("config", other_fmt)

    assert ref == other


@pytest.mark.parametrize("ref_fmt", FORMATS)
@pytest.mark.parametrize("other_fmt", FORMATS)
def test_order_formats_agree(ref_fmt: str, other_fmt: str) -> None:
    ref = validate_template("order", ref_fmt)
    other = validate_template("order", other_fmt)

    assert ref == other
