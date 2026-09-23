"""Round-trip coverage: an order dumped to JSON must parse back to the same order.

This is the property the persisted ``orders.raw`` column exists to support --
dump it to a file, feed it back to eleanor, and get the same run.
"""

import json
from typing import cast

import pytest

from eleanor.order import Order
from eleanor.output.postgres.persistence.connection import _json_dumps
from eleanor.output.postgres.persistence.converters import normalize_dict


def _rich_raw() -> dict[str, object]:
    """A raw order exercising every shape that differs between authoring and asdict."""
    return cast(
        dict[str, object],
        {
            "name": "round-trip",
            "creator": "tester",
            "notes": "a note",
            "tags": ["alpha", "beta"],
            "seed": 4242,
            # flat plugin-config form; asdict re-emits it nested
            "kernel": {"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
            # string shorthand; asdict re-emits it as kind + settings
            "navigator": "random",
            "temperature": {"min": 50, "max": 150},
            "pressure": 1.0,
            "water_mass": 1.0,
            "elements": {"Na": -9, "Cl": -9},
            "species": {"H+": -7},
            # authoring key is ``except``; asdict emits ``exceptions``
            "suppressions": [{"name": "calcite", "except": ["aragonite"]}],
            # dict keyed by name; asdict emits a list carrying ``name`` and ``type``
            "reactants": {
                "forsterite": {
                    "type": "mineral",
                    "amount": {"mean": 0, "stddev": 0.05},
                    "titration_rate": -9,
                },
                "quartz": {"type": "mineral", "amount": 1.0},
            },
        },
    )


def _through_json(order: Order) -> Order:
    """Serialize as the postgres sink does, pass through real JSON, and re-parse.

    Uses the sink's own dumper rather than bare ``json.dumps`` so the test tracks
    what actually reaches the ``raw`` column.
    """
    wire = json.loads(_json_dumps(normalize_dict(order, "order")))
    return Order.from_dict(cast(dict[str, object], wire))


def test_order_survives_a_json_round_trip() -> None:
    order = Order.from_dict(_rich_raw())

    assert _through_json(order) == order


def test_round_trip_is_idempotent() -> None:
    """A second pass must not drift from the first."""
    once = _through_json(Order.from_dict(_rich_raw()))

    assert _through_json(once) == once


def test_round_trip_preserves_the_seed() -> None:
    """``__eq__`` covers this, but assert it directly: a regenerated seed is silent."""
    order = Order.from_dict(_rich_raw())

    assert _through_json(order).seed == order.seed == 4242


def test_round_trip_preserves_suppression_exceptions() -> None:
    """``asdict`` emits ``exceptions`` while the authoring key is ``except``."""
    order = Order.from_dict(_rich_raw())

    assert [s.exceptions for s in _through_json(order).suppressions] == [["aragonite"]]


def test_round_trip_preserves_reactant_identity() -> None:
    """Reactants serialize as a list, so name and type must survive in the payload."""
    order = Order.from_dict(_rich_raw())
    reactants = _through_json(order).reactants

    assert {r.name for r in reactants} == {"forsterite", "quartz"}
    assert {str(r.type) for r in reactants} == {"mineral"}


def test_round_trip_preserves_plugin_config_kinds() -> None:
    """Flat authoring form in, nested asdict form out; both must resolve the same."""
    order = Order.from_dict(_rich_raw())
    got = _through_json(order)

    assert got.kernel.kind == "eq36"
    assert got.navigator.kind == "random"


def test_dumped_order_is_json_serializable() -> None:
    """numpy scalars and enums must be coerced, or the sink cannot write the row."""
    order = Order.from_dict(_rich_raw())

    assert isinstance(_json_dumps(normalize_dict(order, "order")), str)


def test_constraints_survive_a_json_round_trip() -> None:
    """Constraints can be reloaded from a dump"""
    raw = _rich_raw()
    raw["constraints"] = [{"kind": "example", "args": {"x": 1}}]
    order = Order.from_dict(raw)

    got = _through_json(order)

    assert [(c.kind, c.args) for c in got.constraints] == [("example", {"x": 1})]
