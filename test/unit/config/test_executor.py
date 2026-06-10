import pytest
from eleanor.config.executor import ExecutorConfig
from eleanor.exceptions import EleanorError
from eleanor.executor.settings import ExecutorSettings
from eleanor.output.settings import OutputSinkSettings


def test_executor_config_defaults() -> None:
    config = ExecutorConfig()
    assert config.kind == "multiprocessing"
    assert config.settings.chunks_per_worker == 10


def test_executor_config_validation() -> None:
    config = ExecutorConfig(kind="bogus")
    assert config.kind == "bogus"
    with pytest.raises(EleanorError, match="must be greater than zero"):
        _ = ExecutorConfig.from_dict({"chunks_per_worker": 0})


def test_executor_config_raises_for_non_executor_settings_type() -> None:
    with pytest.raises(EleanorError, match=f"requires {ExecutorSettings.__name__}"):
        _ = ExecutorConfig(kind="serial", settings=OutputSinkSettings())  # pyright: ignore[reportArgumentType]
