import pytest
from eleanor.cli.gen import FORMATS, validate_template
from eleanor.config import Config
from eleanor.order import Order


@pytest.mark.parametrize("fmt", FORMATS)
def test_config_templates_are_valid(fmt: str) -> None:
    result = validate_template("config", fmt)
    assert isinstance(result, Config)


@pytest.mark.parametrize("fmt", FORMATS)
def test_order_templates_are_valid(fmt: str) -> None:
    result = validate_template("order", fmt)
    assert isinstance(result, Order)


def test_unknown_template_raises() -> None:
    with pytest.raises(ValueError):
        _ = validate_template("bogus", "yaml")
