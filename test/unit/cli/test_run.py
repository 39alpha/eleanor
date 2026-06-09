from pathlib import Path

from click.testing import CliRunner
from eleanor import Eleanor
from eleanor.cli import main
from eleanor.config import Config
from eleanor.exceptions import EleanorShutdown
from eleanor.executor import AbstractExecutor
from eleanor.executor.settings import ExecutorSettings
from eleanor.order import Order
from eleanor.output.null import NullSink
from eleanor.output.postgres.settings import PostgresSinkSettings
from pytest_mock import MockerFixture


def make_eleanor(mocker: MockerFixture, run_return: int | None = None):
    eleanor = mocker.create_autospec(Eleanor, instance=True)
    eleanor.__enter__.return_value = eleanor
    eleanor.__exit__.return_value = None
    if run_return is None:
        run_return = 1
    eleanor.run.return_value = run_return
    return eleanor


def make_executor(mocker: MockerFixture):
    executor = mocker.create_autospec(AbstractExecutor, instance=True)
    executor.__enter__.return_value = executor
    executor.__exit__.return_value = None
    return executor


def make_config(kind: str = "multiprocessing", chunks_per_worker: int = 1) -> Config:
    return Config.from_dict(
        {
            "output": {
                "kind": "postgres",
                "database": {"database": "sample"},
            },
            "executor": {
                "kind": kind,
                "chunks_per_worker": chunks_per_worker,
            },
        },
    )


def invoke_run(runner: CliRunner, extra_args: list[str]):
    with runner.isolated_filesystem():
        _ = Path("order.yaml").write_text("order: demo\n", encoding="utf-8")
        return runner.invoke(main, ["run", *extra_args, "order.yaml", "10"])


def test_run_uses_config_executor_defaults(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config(kind="serial", chunks_per_worker=6)
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    config_from_args = mocker.patch(
        "eleanor.cli.run.config_from_args", return_value=config
    )
    load_order = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    load_executor = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    eleanor_ctor = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--num-workers", "3"]
    )

    config_from_args.assert_called_once()
    load_order.assert_called_once()
    load_executor.assert_called_once_with(
        kind="serial", settings=ExecutorSettings(chunks_per_worker=6, num_workers=3)
    )
    eleanor_ctor.assert_called_once_with(config=config, executor=executor)
    eleanor.run.assert_called_once_with(
        order,
        10,
        kernel_args=[],
        scratch=False,
        show_progress=False,
        verbose=False,
        chunks_per_worker=6,
        batch_size=None,
        max_nav_attempts=1,
        output_sink=None,
    )
    assert result.exit_code == 0


def test_run_cli_flags_override_config_executor_values(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config(kind="multiprocessing", chunks_per_worker=2)
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    config_from_args = mocker.patch(
        "eleanor.cli.run.config_from_args", return_value=config
    )
    load_order = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    load_executor = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    eleanor_ctor = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner,
        [
            "-c",
            "/fake.yaml",
            "-d",
            "sample",
            "--executor",
            "serial",
            "--chunks-per-worker",
            "9",
        ],
    )

    config_from_args.assert_called_once()
    load_order.assert_called_once()
    load_executor.assert_called_once_with(
        kind="serial",
        settings=ExecutorSettings(chunks_per_worker=9, num_workers=None),
    )
    eleanor_ctor.assert_called_once_with(config=config, executor=executor)
    assert eleanor.run.call_args.kwargs["chunks_per_worker"] == 9
    assert eleanor.run.call_args.kwargs["max_nav_attempts"] == 1
    assert result.exit_code == 0


def test_run_null_sink_overrides_output_sink(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config(kind="serial", chunks_per_worker=2)
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    mock_sink_init = mocker.patch.object(NullSink, "initialize")
    mock_sink_fin = mocker.patch.object(NullSink, "finalize")
    config_from_args = mocker.patch(
        "eleanor.cli.run.config_from_args", return_value=config
    )
    load_order = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    load_executor = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    eleanor_ctor = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "--null-sink"])

    config_from_args.assert_called_once_with("/fake.yaml", None, require_database=False)
    load_order.assert_called_once()
    load_executor.assert_called_once_with(
        kind="serial",
        settings=ExecutorSettings(chunks_per_worker=2, num_workers=None),
    )
    eleanor_ctor.assert_called_once_with(config=config, executor=executor)
    assert isinstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)
    mock_sink_init.assert_called_once()
    mock_sink_fin.assert_called_once()

    assert result.exit_code == 0


def test_run_max_nav_attempts_is_forwarded(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--max-nav-attempts", "4"]
    )

    assert eleanor.run.call_args.kwargs["max_nav_attempts"] == 4
    assert result.exit_code == 0


def test_run_disables_progress_when_verbose(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor")
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--progress", "--verbose"]
    )

    assert not eleanor.run.call_args.kwargs["show_progress"]
    assert result.exit_code == 0


def test_run_applies_order_id_to_loaded_order(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--order-id", "321"]
    )

    assert result.exit_code == 0
    assert eleanor.run.call_args.args[0] is order
    assert order.id == 321


def test_run_applies_single_tag_to_loaded_order(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order, instance=True)
    order.tags = []

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--tag", "experiment-1"]
    )

    assert result.exit_code == 0
    assert order.tags == ["experiment-1"]
    assert eleanor.run.call_args.args[0] is order


def test_run_applies_multiple_tags_to_loaded_order(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order, instance=True)
    order.tags = []

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--tag", "foo", "--tag", "bar"]
    )

    assert result.exit_code == 0
    assert order.tags == ["foo", "bar"]


def test_run_cli_tags_merge_with_order_file_tags(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order, instance=True)
    order.tags = ["existing"]

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample", "--tag", "new"])

    assert result.exit_code == 0
    assert order.tags == ["existing", "new"]


def test_run_cli_tags_deduplicates_against_order_file_tags(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order, instance=True)
    order.tags = ["foo"]

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--tag", "foo", "--tag", "bar"]
    )

    assert result.exit_code == 0
    assert order.tags == ["foo", "bar"]


def test_run_without_tag_flag_leaves_order_tags_unchanged(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order, instance=True)
    order.tags = ["existing"]

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample"])

    assert result.exit_code == 0
    assert order.tags == ["existing"]


def test_run_rejects_unknown_executor_kind(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.available_executors", return_value={"serial"})
    eleanor_ctor = mocker.patch("eleanor.cli.run.Eleanor")

    result = invoke_run(
        runner, ["-c", "/fake.yaml", "-d", "sample", "--executor", "does-not-exist"]
    )

    eleanor_ctor.assert_not_called()
    assert result.exit_code == 0
    assert "does-not-exist" in result.output
    assert "unsupported" in result.output
    assert "executor" in result.output


def test_run_keyboard_interrupt_exits_130_with_friendly_message(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    eleanor.run.side_effect = KeyboardInterrupt()
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample"])

    assert result.exit_code == 130
    assert (
        "Eleanor run interrupted by interrupt; sink finalized cleanly." in result.output
    )


def test_run_bulk_load_sets_optimization_in_postgres_config(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample", "--bulk-load"])

    assert result.exit_code == 0
    assert config.output is not None
    assert isinstance(config.output.settings, PostgresSinkSettings)
    assert config.output.settings.bulk_load_optimization


def test_run_bulk_load_rejects_non_postgres_sink(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = Config.from_dict(
        {
            "output": {
                "kind": "null",
            },
            "executor": {
                "kind": "serial",
                "chunks_per_worker": 1,
            },
        }
    )

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    eleanor_ctor = mocker.patch("eleanor.cli.run.Eleanor")

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample", "--bulk-load"])

    assert result.exit_code == 0
    eleanor_ctor.assert_not_called()
    assert "--bulk-load" in result.output
    assert "postgres" in result.output


def test_run_no_bulk_load_disables_config_optimization(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    assert config.output is not None
    assert isinstance(config.output.settings, PostgresSinkSettings)
    config.output.settings.bulk_load_optimization = True

    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample", "--no-bulk-load"])

    assert result.exit_code == 0
    assert not config.output.settings.bulk_load_optimization


def test_run_bulk_load_omitted_leaves_config_unchanged(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    assert config.output is not None
    assert isinstance(config.output.settings, PostgresSinkSettings)
    config.output.settings.bulk_load_optimization = True

    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample"])

    assert result.exit_code == 0
    assert config.output.settings.bulk_load_optimization


def test_run_bulk_load_ignored_when_null_sink(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    order = mocker.create_autospec(Order)

    _ = mocker.patch.object(NullSink, "initialize")
    _ = mocker.patch.object(NullSink, "finalize")
    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "--null-sink", "--bulk-load"])

    assert result.exit_code == 0
    assert isinstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)


def test_run_eleanor_shutdown_uses_signal_name_in_message(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    config = make_config()
    executor = make_executor(mocker)
    eleanor = make_eleanor(mocker)
    eleanor.run.side_effect = EleanorShutdown("SIGTERM")
    order = mocker.create_autospec(Order)

    _ = mocker.patch("eleanor.cli.run.config_from_args", return_value=config)
    _ = mocker.patch("eleanor.cli.run.load_order", return_value=order)
    _ = mocker.patch("eleanor.cli.run.load_executor", return_value=executor)
    _ = mocker.patch("eleanor.cli.run.Eleanor", return_value=eleanor)

    result = invoke_run(runner, ["-c", "/fake.yaml", "-d", "sample"])

    assert result.exit_code == 130
    assert (
        "Eleanor run interrupted by SIGTERM; sink finalized cleanly." in result.output
    )
