"""Unit tests for the 'eleanor postgres dump order' Click command."""

import json
import uuid
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner, Result
from eleanor.cli import main
from eleanor.config import Config
from eleanor.order import Order
from eleanor.output.postgres.cli.dump.order import _OPTIONAL_PROPERTIES, _PROPERTIES
from eleanor.output.postgres.persistence.connection import _json_dumps
from eleanor.output.postgres.persistence.converters import OrderRecord, normalize_dict
from eleanor.version import __version__
from pytest_mock import MockerFixture

ORDER_ID = uuid.UUID("018f3a1c-0000-7000-8000-000000000000")


def make_authored_order() -> dict[str, object]:
    """An order populating every optional property, so a dump has something to carry."""
    return cast(
        dict[str, object],
        {
            "name": "dump-me",
            "creator": "tester",
            "notes": "a note",
            "tags": ["alpha", "beta"],
            "seed": 4242,
            "kernel": {"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
            "navigator": "random",
            "temperature": {"min": 50, "max": 150},
            "pressure": 1.0,
            "water_mass": 1.0,
            "elements": {"Na": -9, "Cl": -9},
            "species": {"H+": -7},
            "suppressions": [{"name": "calcite", "except": ["aragonite"]}],
            "reactants": {"quartz": {"type": "mineral", "amount": 1.0}},
            "constraints": [{"kind": "linear", "terms": [{"element": "Na", "coefficient": 1.0}]}],
        },
    )


def make_bare_order() -> dict[str, object]:
    """An order declaring only what is required, so every optional property is empty.

    Every name in ``_OPTIONAL_PROPERTIES`` is omitted here; ``Order`` defaults each to
    an empty value. Dumping this is what actually exercises dropping and ``--keep-empty``.
    """
    return cast(
        dict[str, object],
        {
            "name": "bare",
            "creator": "tester",
            "seed": 4242,
            "kernel": {"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
            "temperature": {"min": 50, "max": 150},
            "pressure": 1.0,
            "elements": {"Na": -9},
        },
    )


def make_raw(order: dict[str, object] | None = None, create_date: datetime | None = None) -> dict[str, object]:
    """Build an ``orders.raw`` payload the way the sink does, through real JSON."""
    parsed = Order.from_dict(order if order is not None else make_authored_order(), create_date=create_date)
    return cast(dict[str, object], json.loads(_json_dumps(normalize_dict(parsed, "order"))))


def make_record(raw: dict[str, object]) -> OrderRecord:
    return OrderRecord(
        id=ORDER_ID,
        name=cast(str, raw["name"]),
        tags=cast(list[str], raw["tags"]),
        eleanor_version=cast(str, raw["eleanor_version"]),
        raw=raw,
        create_date=datetime(2026, 1, 9, 10, 59, 1),
    )


def make_config(database: str | None = "demo_db") -> Config:
    sink: dict[str, object] = {"kind": "postgres"}
    if database is not None:
        sink["database"] = {"database": database}
    return Config.from_dict({"output": sink})


def stub_lookup(
    mocker: MockerFixture,
    raw: dict[str, object] | None = None,
    config: Config | None = None,
    found: bool = True,
) -> MagicMock:
    """Patch the command's config and repository access, returning the get_order mock."""
    _ = mocker.patch(
        "eleanor.output.postgres.cli.dump.order.config_from_args",
        return_value=config if config is not None else make_config(),
    )
    record = make_record(raw if raw is not None else make_raw()) if found else None
    return cast(
        MagicMock,
        mocker.patch("eleanor.output.postgres.cli.dump.order.get_order", return_value=record),
    )


def invoke_dump(runner: CliRunner, *args: str) -> Result:
    return runner.invoke(main, ["postgres", "dump", "order", *args, "-c", "/fake.yaml"])


def dump_text(runner: CliRunner, *args: str) -> str:
    """Invoke the command for the default order id and return its stdout."""
    result = invoke_dump(runner, str(ORDER_ID), *args)
    assert result.exit_code == 0, result.output
    return result.output


def is_json(text: str) -> bool:
    """Every JSON document is also valid YAML, so probe for JSON specifically."""
    try:
        _ = json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def test_defaults_to_yaml_on_stdout(mocker: MockerFixture, runner: CliRunner) -> None:
    _ = stub_lookup(mocker)

    dumped = cast(dict[str, object], yaml.safe_load(dump_text(runner)))

    assert dumped["name"] == "dump-me"


def test_to_json_emits_json_terminated_by_a_newline(mocker: MockerFixture, runner: CliRunner) -> None:
    """A missing trailing newline would leave the shell prompt on the closing brace."""
    _ = stub_lookup(mocker)

    output = dump_text(runner, "-t", "json")

    assert cast(dict[str, object], json.loads(output))["name"] == "dump-me"
    assert output.endswith("}\n")


@pytest.mark.parametrize(
    ("filename", "expect_json"),
    [
        ("order.json", True),
        ("order.JSON", True),
        ("order.yaml", False),
        ("order.yml", False),
        ("order.txt", False),
        ("order", False),
    ],
)
def test_format_is_inferred_from_the_output_extension(
    mocker: MockerFixture, runner: CliRunner, tmp_path: Path, filename: str, expect_json: bool
) -> None:
    _ = stub_lookup(mocker)
    path = tmp_path / filename

    result = invoke_dump(runner, str(ORDER_ID), "-o", str(path))
    assert result.exit_code == 0, result.output

    text = path.read_text()
    assert is_json(text) is expect_json
    assert cast(dict[str, object], yaml.safe_load(text))["name"] == "dump-me"


def test_to_overrides_the_inferred_extension(mocker: MockerFixture, runner: CliRunner, tmp_path: Path) -> None:
    _ = stub_lookup(mocker)
    path = tmp_path / "order.json"

    result = invoke_dump(runner, str(ORDER_ID), "-o", str(path), "-t", "yaml")
    assert result.exit_code == 0, result.output

    assert not is_json(path.read_text())


def test_empty_optional_properties_are_dropped(mocker: MockerFixture, runner: CliRunner) -> None:
    """Every optional property stays out when it carries nothing."""
    _ = stub_lookup(mocker, raw=make_raw(make_bare_order()))

    dumped = cast(dict[str, object], yaml.safe_load(dump_text(runner)))

    assert _OPTIONAL_PROPERTIES.isdisjoint(dumped)


def test_populated_optional_properties_are_kept_without_the_flag(mocker: MockerFixture, runner: CliRunner) -> None:
    """Dropping is about emptiness, not about being optional."""
    _ = stub_lookup(mocker, raw=make_raw(make_authored_order()))

    dumped = cast(dict[str, object], yaml.safe_load(dump_text(runner)))

    assert _OPTIONAL_PROPERTIES <= set(dumped)


def test_keep_empty_retains_empty_optional_properties(mocker: MockerFixture, runner: CliRunner) -> None:
    """-e emits every optional property the default run drops, each still empty."""
    _ = stub_lookup(mocker, raw=make_raw(make_bare_order()))

    dumped = cast(dict[str, object], yaml.safe_load(dump_text(runner, "-e")))

    assert _OPTIONAL_PROPERTIES <= set(dumped)
    assert {prop: dumped[prop] for prop in _OPTIONAL_PROPERTIES} == {
        "tags": [],
        "notes": "",
        "species": {},
        "reactants": [],
        "suppressions": [],
        "constraints": [],
    }


def test_keep_empty_does_not_emit_empty_required_properties(mocker: MockerFixture, runner: CliRunner) -> None:
    """A required property emitted empty would not re-parse, so -e must not reach it."""
    raw = make_raw()
    raw["water_mass"] = {}
    _ = stub_lookup(mocker, raw=raw)

    assert "water_mass" not in cast(dict[str, object], yaml.safe_load(dump_text(runner, "-e")))


def test_properties_are_emitted_in_canonical_order(mocker: MockerFixture, runner: CliRunner) -> None:
    """The dump orders properties by _PROPERTIES, not by the raw column's key order."""
    _ = stub_lookup(mocker, raw=dict(reversed(list(make_raw().items()))))

    dumped = cast(dict[str, object], yaml.safe_load(dump_text(runner, "-e")))

    assert list(dumped) == [prop for prop in _PROPERTIES if prop in dumped]


def test_vs_points_are_never_dumped(mocker: MockerFixture, runner: CliRunner) -> None:
    """The points are persisted separately and must not leak into the order file."""
    _ = stub_lookup(mocker)

    assert "vs_points" not in cast(dict[str, object], yaml.safe_load(dump_text(runner, "-e")))


def test_lookup_uses_the_resolved_settings_and_parsed_uuid(mocker: MockerFixture, runner: CliRunner) -> None:
    get_order = stub_lookup(mocker)

    _ = dump_text(runner)

    settings, order_id = get_order.call_args.args
    assert settings.database == "demo_db"
    assert order_id == ORDER_ID


def test_invalid_uuid_reports_cleanly_without_a_lookup(mocker: MockerFixture, runner: CliRunner) -> None:
    """A malformed id is a CLI error rather than a traceback, and never reaches the database."""
    get_order = stub_lookup(mocker)

    result = invoke_dump(runner, "not-a-uuid")

    assert result.exit_code == 1
    assert "order id must be a UUID" in result.output
    assert "Traceback" not in result.output
    get_order.assert_not_called()


def test_missing_order_reports_the_id(mocker: MockerFixture, runner: CliRunner) -> None:
    _ = stub_lookup(mocker, found=False)

    result = invoke_dump(runner, str(ORDER_ID))

    assert result.exit_code == 1
    assert f"no order found with id {ORDER_ID}" in result.output


def test_a_property_missing_from_raw_reports_cleanly(mocker: MockerFixture, runner: CliRunner) -> None:
    """An order stored before a property existed names the gap rather than raising KeyError."""
    raw = make_raw()
    del raw["seed"]
    _ = stub_lookup(mocker, raw=raw)

    result = invoke_dump(runner, str(ORDER_ID))

    assert result.exit_code == 1
    assert "order is missing the 'seed' property" in result.output
    assert "Traceback" not in result.output


def test_missing_database_exits_before_lookup(mocker: MockerFixture, runner: CliRunner) -> None:
    """A config naming no database must fail rather than query the local default."""
    get_order = stub_lookup(mocker, config=make_config(database=None))

    result = invoke_dump(runner, str(ORDER_ID))

    assert result.exit_code == 1
    assert "no database provided" in result.output
    get_order.assert_not_called()


@pytest.mark.parametrize(
    ("order", "args", "parse"),
    [
        (make_authored_order, (), Order.from_yamls),
        (make_authored_order, ("-t", "json"), Order.from_jsons),
        (make_bare_order, (), Order.from_yamls),
        (make_bare_order, ("-e",), Order.from_yamls),
    ],
)
def test_the_dump_reparses_to_the_same_order(
    mocker: MockerFixture,
    runner: CliRunner,
    order: Callable[[], dict[str, object]],
    args: tuple[str, ...],
    parse: Callable[[str], Order],
) -> None:
    """The point of the command: the dump must be runnable, and run the same order.

    ``create_date`` and ``eleanor_version`` are provenance, not part of what the order
    means, and are deliberately not restored -- see the two tests below.
    """
    _ = stub_lookup(mocker, raw=make_raw(order()))
    original = Order.from_dict(order())

    assert parse(dump_text(runner, *args)) == original


def test_the_dump_records_the_create_date_but_reloading_restamps_it(mocker: MockerFixture, runner: CliRunner) -> None:
    """The dump carries when the order was recorded; re-running it is a new run, dated now.

    ``create_date`` is ``field(compare=False)``, so the equality round-trip above cannot
    see this either way. Both halves have to be asserted directly.
    """
    recorded = datetime(2020, 5, 17, 12, 0, 0)
    _ = stub_lookup(mocker, raw=make_raw(create_date=recorded))

    text = dump_text(runner)
    before_reload = datetime.now()

    assert cast(dict[str, object], yaml.safe_load(text))["create_date"] == str(recorded)
    assert Order.from_yamls(text).create_date >= before_reload


def test_the_dump_records_the_eleanor_version_but_reloading_restamps_it(
    mocker: MockerFixture, runner: CliRunner
) -> None:
    """The dump names the version that recorded the order; reloading stamps the one running it."""
    raw = make_raw()
    raw["eleanor_version"] = "0.19.0"
    _ = stub_lookup(mocker, raw=raw)

    text = dump_text(runner)

    assert cast(dict[str, object], yaml.safe_load(text))["eleanor_version"] == "0.19.0"
    assert Order.from_yamls(text).eleanor_version == __version__


def test_properties_cover_every_order_field() -> None:
    """Guard against drift: a field added to Order must be dumped or deliberately excluded."""
    excluded = {"vs_points"}

    assert set(_PROPERTIES) == {field.name for field in fields(Order)} - excluded


def test_properties_are_unique() -> None:
    assert len(_PROPERTIES) == len(set(_PROPERTIES))


def test_optional_properties_are_dumped_properties() -> None:
    """A name only spelled in _OPTIONAL_PROPERTIES would silently do nothing."""
    assert _OPTIONAL_PROPERTIES <= set(_PROPERTIES)


def test_dump_group_lists_order(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "--help"])

    assert result.exit_code == 0
    assert "order" in result.output


def test_dump_order_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "order", "--help"])

    assert result.exit_code == 0
