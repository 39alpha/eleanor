import pytest
from eleanor.config import Config
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
from eleanor.executor.settings import ExecutorSettings
from eleanor.output.settings import OutputSinkSettings


def test_output_config_defers_kind_validation() -> None:
    config = OutputSinkConfig(kind="definitely-not-a-sink")
    assert config.kind == "definitely-not-a-sink"

    plugin = OutputSinkConfig(kind="csv")
    assert plugin.kind == "csv"


def test_config_rejects_legacy_database_key() -> None:
    with pytest.raises(EleanorError, match='the top-level "database:"'):
        _ = Config.from_dict(
            {
                "database": {
                    "database": "sample",
                }
            }
        )


def test_output_config_raises_for_non_output_settings_type() -> None:
    with pytest.raises(
        EleanorError, match=f"requires {OutputSinkSettings.__name__}"
    ):
        _ = OutputSinkConfig(kind="null", settings=ExecutorSettings())  # pyright: ignore[reportArgumentType]
