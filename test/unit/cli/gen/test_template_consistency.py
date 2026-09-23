import pytest
from eleanor.cli.gen import FORMATS, validate_template
from eleanor.order import Order


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

    # The template omits ``seed``, so each parse generates its own. The property
    # under test is that the three renderings describe the same order, so pin the
    # seeds equal rather than weakening the comparison.
    assert isinstance(ref, Order) and isinstance(other, Order)
    other.seed = ref.seed

    assert ref == other
