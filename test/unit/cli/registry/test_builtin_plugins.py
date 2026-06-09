import pytest
from eleanor.cli.registry import available_cli_commands


@pytest.mark.usefixtures("clean_registry")
def test_postgres_is_registered() -> None:
    assert "postgres" in available_cli_commands()
