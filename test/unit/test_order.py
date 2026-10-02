import json
from datetime import datetime
from os.path import join
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

import numpy as np
import pytest
from eleanor.config.constraint import ConstraintConfig
from eleanor.exceptions import EleanorError
from eleanor.kernel.settings import KernelSettings
from eleanor.order import Order, Suppression, load_order
from eleanor.parameters import ValueParameter
from eleanor.variable_space import Point as VSPoint


def _minimal_raw(**overrides):
    """Return a raw dict with all required Order fields populated."""
    base = {
        "name": "o",
        "creator": "u",
        "kernel": {"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
        "temperature": 25.0,
        "pressure": 1.0,
        "elements": {"Na": 1.0},
    }
    base.update(overrides)
    return base


_FAKE_KERNEL_SPEC = SimpleNamespace(
    settings_from_dict=mock.Mock(return_value=KernelSettings(timeout=None)),
    build=mock.Mock(),
)


def _make_order(
    raw=None,
    *,
    tags=None,
    seed=None,
    vs_points=None,
    create_date=None,
    **overrides,
):
    """Build an Order with the kernel registry mocked out."""
    effective = raw if raw is not None else _minimal_raw(**overrides)
    with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
        return Order.from_dict(
            cast(dict[str, object], cast(object, effective)),
            tags=tags,
            seed=seed,
            vs_points=vs_points,
            create_date=create_date,
        )


class TestOrder(TestCase):
    """
    Tests of the eleanor.order module.
    """

    def test_suppression(self) -> None:
        """
        Ensure suppression construction and parsing validate name/type/exception constraints.
        """
        with self.assertRaises(EleanorError):
            _ = Suppression(None, None, [])

        s = Suppression.from_dict({"name": "Quartz", "except": ["H2O"]})
        self.assertEqual(s.name, "Quartz")
        self.assertEqual(s.type, None)
        self.assertEqual(s.exceptions, ["H2O"])

        s2 = Suppression.from_dict({"type": "mineral"}, name="Calcite")
        self.assertEqual(s2.name, "Calcite")
        self.assertEqual(s2.type, "mineral")

        with self.assertRaises(EleanorError):
            _ = Suppression.from_dict(cast(dict[str, object], cast(object, {"name": 1})))
        with self.assertRaises(EleanorError):
            _ = Suppression.from_dict(cast(dict[str, object], cast(object, {"name": "x", "type": 2})))
        with self.assertRaises(EleanorError):
            _ = Suppression.from_dict(cast(dict[str, object], cast(object, {"name": "x", "except": [1]})))

    def test_order_core_methods(self) -> None:
        """
        Ensure order parsing and parameter collection work for common paths.
        """
        order = _make_order(
            name="order1",
            creator="user",
            temperature=25.0,
            pressure=1.0,
            elements={"Na": 1.0},
            species={"H+": 2.0},
            reactants={},
        )

        params = order.parameters()
        self.assertTrue(any(isinstance(p, ValueParameter) for p in params))

    def test_order_rejects_an_id_in_raw(self) -> None:
        """
        Ensure a raw ``id`` key is refused rather than ignored. The key used to
        carry meaning, so dropping it silently would change an existing order
        file's behaviour without saying so.
        """
        with self.assertRaisesRegex(EleanorError, "user-specified order ids are no longer supported"):
            _ = _make_order(id=12)

        with self.assertRaisesRegex(EleanorError, "user-specified order ids are no longer supported"):
            _ = _make_order(id="not-an-int")

    def test_order_validation_and_kernel_branches(self) -> None:
        """
        Ensure order validation and kernel/navigator parsing branches behave correctly.
        """
        with self.assertRaises(EleanorError):
            _ = Order.from_dict(cast(dict[str, object], cast(object, _minimal_raw(name=1))))
        with self.assertRaises(EleanorError):
            _ = Order.from_dict(cast(dict[str, object], cast(object, _minimal_raw(notes=1))))
        with self.assertRaises(EleanorError):
            _ = Order.from_dict(cast(dict[str, object], cast(object, _minimal_raw(creator=1))))

        order = _make_order(
            name="o",
            creator="u",
            kernel={"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
            navigator="random",
        )
        self.assertIsNotNone(order.kernel)
        self.assertEqual(order.navigator.kind, "random")

    def test_order_parameters_includes_kernel_and_reactant_parameters(self) -> None:
        """
        Ensure :meth:`Order.parameters` includes kernel and reactant-derived parameter lists.
        """
        order = _make_order()
        kparam = ValueParameter(np.float64(1.0))
        rparam = ValueParameter(np.float64(2.0))
        order.kernel = SimpleNamespace(parameters=lambda: [kparam])
        order.reactants = [SimpleNamespace(parameters=lambda: [rparam])]

        params = order.parameters()
        self.assertIn(kparam, params)
        self.assertIn(rparam, params)

    def test_order_rejects_duplicate_names_between_reactants_and_combined_components(
        self,
    ) -> None:
        """
        Ensure duplicate concrete names across standalone reactants and combined components are rejected.
        """
        with self.assertRaisesRegex(
            EleanorError,
            "appears more than once across reactants and combined-reactant components",
        ):
            _ = _make_order(
                reactants={
                    "FeO": {
                        "type": "special",
                        "amount": 1.0,
                        "composition": {"Fe": 1, "O": 1},
                    },
                    "mixed": {
                        "type": "combined",
                        "amount": 1.0,
                        "components": {
                            "FeO": {
                                "type": "special",
                                "fraction": 0.5,
                                "composition": {"Fe": 1, "O": 1},
                            },
                            "SiO2": {
                                "type": "special",
                                "fraction": 0.5,
                                "composition": {"Si": 1, "O": 2},
                            },
                        },
                    },
                }
            )

    def test_order_file_loaders_and_load_order(self) -> None:
        """
        Ensure order file/string loaders and load_order dispatch behave across formats.
        """
        raw = _minimal_raw()
        yaml_content = (
            "name: o\n"
            "creator: u\n"
            "kernel:\n"
            "  kind: eq36\n"
            "  model: b-dot\n"
            "  charge_balance: H+\n"
            "temperature: 25.0\n"
            "pressure: 1.0\n"
            "elements:\n"
            "  Na: 1.0\n"
        )
        toml_content = (
            'name = "o"\n'
            'creator = "u"\n'
            "temperature = 25.0\n"
            "pressure = 1.0\n"
            "[kernel]\n"
            'kind = "eq36"\n'
            'model = "b-dot"\n'
            'charge_balance = "H+"\n'
            "[elements]\n"
            "Na = 1.0\n"
        )
        json_content = json.dumps(raw)

        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with TemporaryDirectory() as tmp:
                yml = join(tmp, "o.yaml")
                yml2 = join(tmp, "o.yml")
                toml = join(tmp, "o.toml")
                js = join(tmp, "o.json")
                bad = join(tmp, "o.ini")

                with open(yml, "w") as handle:
                    _ = handle.write(yaml_content)
                with open(yml2, "w") as handle:
                    _ = handle.write(yaml_content)
                with open(toml, "w") as handle:
                    _ = handle.write(toml_content)
                with open(js, "w") as handle:
                    _ = handle.write(json_content)
                with open(bad, "w") as handle:
                    _ = handle.write("[x]\n")

                self.assertIsInstance(Order.from_yaml(yml), Order)
                self.assertIsInstance(Order.from_toml(toml), Order)
                self.assertIsInstance(Order.from_json(js), Order)
                self.assertIsInstance(Order.from_yamls(yaml_content), Order)
                self.assertIsInstance(Order.from_tomls(toml_content), Order)
                self.assertIsInstance(Order.from_jsons(json_content), Order)
                self.assertIsInstance(Order.from_file(yml), Order)
                self.assertIsInstance(Order.from_file(yml2), Order)
                self.assertIsInstance(Order.from_file(toml), Order)
                self.assertIsInstance(Order.from_file(js), Order)
                with self.assertRaises(EleanorError):
                    _ = Order.from_file(bad)

                self.assertIsInstance(load_order(yml), Order)

        o = _make_order(name="x")
        self.assertIs(load_order(o), o)

    def test_order_from_file_re_raises_eleanor_exception(self) -> None:
        """
        Ensure Order.from_file re-raises EleanorError from parser branches without wrapping.
        """
        with mock.patch("eleanor.order.Order.from_yaml", side_effect=EleanorError("boom")):
            with self.assertRaisesRegex(EleanorError, "boom"):
                _ = Order.from_file("test.yaml")

    def test_order_requires_kernel(self) -> None:
        """Ensure Order raises when kernel is absent."""
        with self.assertRaisesRegex(EleanorError, "kernel is required"):
            _ = Order.from_dict(
                {
                    "name": "o",
                    "creator": "u",
                    "temperature": 25.0,
                    "pressure": 1.0,
                    "elements": {"Na": 1.0},
                },
            )

    def test_order_requires_temperature(self) -> None:
        """Ensure Order raises when temperature is absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorError, "temperature is required"):
                _ = Order.from_dict(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {
                            "kind": "eq36",
                            "model": "b-dot",
                            "charge_balance": "H+",
                        },
                        "pressure": 1.0,
                        "elements": {"Na": 1.0},
                    }
                )

    def test_order_requires_pressure(self) -> None:
        """Ensure Order raises when pressure is absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorError, "pressure is required"):
                _ = Order.from_dict(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {
                            "kind": "eq36",
                            "model": "b-dot",
                            "charge_balance": "H+",
                        },
                        "temperature": 25.0,
                        "elements": {"Na": 1.0},
                    }
                )

    def test_order_requires_nonempty_elements(self) -> None:
        """Ensure Order raises when elements is empty or absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorError, "elements must not be empty"):
                _ = Order.from_dict(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {
                            "kind": "eq36",
                            "model": "b-dot",
                            "charge_balance": "H+",
                        },
                        "temperature": 25.0,
                        "pressure": 1.0,
                    }
                )
            with self.assertRaisesRegex(EleanorError, "elements must not be empty"):
                _ = Order.from_dict(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {
                            "kind": "eq36",
                            "model": "b-dot",
                            "charge_balance": "H+",
                        },
                        "temperature": 25.0,
                        "pressure": 1.0,
                        "elements": {},
                    }
                )

    def test_order_volume_all_scalar(self) -> None:
        """An order with no variable parameters has zero volume."""
        order = _make_order()
        self.assertEqual(order.volume(), np.float64(0.0))

    def test_order_volume_ignores_a_degenerate_normal(self) -> None:
        """A normal pinned to a point refines away rather than zeroing the whole product."""
        order = _make_order(
            temperature={"mean": 5.0, "min": 5.0, "max": 5.0},
            pressure={"min": 1.0, "max": 11.0},
        )
        self.assertIsInstance(order.temperature, ValueParameter)
        self.assertEqual(order.volume(), np.float64(10.0))

    def test_order_volume_single_range_parameter(self) -> None:
        """A range contributes its width."""
        order = _make_order(temperature={"min": 20.0, "max": 30.0})
        self.assertEqual(order.volume(), np.float64(10.0))

    def test_order_volume_multiple_range_parameters(self) -> None:
        """Range widths multiply."""
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            elements={"Na": {"min": 0.5, "max": 2.5}},
        )
        self.assertEqual(order.volume(), np.float64(20.0))

    def test_order_volume_list_parameter(self) -> None:
        """A list contributes its length."""
        order = _make_order(pressure=[1.0, 2.0, 3.0])
        self.assertEqual(order.volume(), np.float64(3.0))

    def test_order_volume_mixed_range_and_list(self) -> None:
        """A range width and a list length multiply."""
        order = _make_order(
            temperature={"min": 0.0, "max": 10.0},
            pressure=[1.0, 2.0],
        )
        self.assertEqual(order.volume(), np.float64(20.0))

    def test_order_volume_includes_reactant_parameters(self) -> None:
        """Variable reactant parameters contribute to the order's volume."""
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            reactants={
                "quartz": {
                    "type": "mineral",
                    "amount": {"min": 0.0, "max": 2.0},
                    "titration_rate": 1.0,
                },
            },
        )
        self.assertEqual(order.volume(), np.float64(20.0))

    def test_order_parameters_include_constraint_locals(self) -> None:
        """A constraint's own parameters are the order's by transitivity, so volume counts them."""
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            pressure={"min": 1.0, "max": 5.0},
            constraints=[
                {
                    "kind": "linear",
                    "terms": [
                        {"variable": "temperature", "coefficient": 1.0},
                        {"variable": "pressure", "coefficient": -2.0},
                    ],
                    "constant": {"min": 0.0, "max": 4.0},
                }
            ],
        )
        constant = order.constraints[0].parameters()[0]

        self.assertTrue(any(p is constant for p in order.parameters()))
        self.assertEqual(order.volume(), np.float64(160.0))

    def test_order_volume_ignores_a_fixed_constraint_local(self) -> None:
        """A fixed constant varies nothing, so it drops out like any other fixed parameter."""
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            pressure={"min": 1.0, "max": 5.0},
            constraints=[
                {
                    "kind": "linear",
                    "terms": [{"variable": "temperature", "coefficient": 1.0}],
                    "constant": 7.0,
                }
            ],
        )

        self.assertEqual(order.volume(), np.float64(40.0))

    def test_order_parameters_returns_the_same_objects_each_call(self) -> None:
        """The parameter registry keys on identity, so repeated calls must not re-parse."""
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            constraints=[
                {
                    "kind": "linear",
                    "terms": [{"variable": "temperature", "coefficient": 1.0}],
                    "constant": {"min": 0.0, "max": 4.0},
                }
            ],
        )

        first, second = order.parameters(), order.parameters()

        self.assertEqual(len(first), len(second))
        self.assertTrue(all(a is b for a, b in zip(first, second, strict=True)))

    def test_order_picks_up_a_constraint_added_after_construction(self) -> None:
        """Nothing is cached, so an order stays editable until it is used."""
        order = _make_order(temperature={"min": 20.0, "max": 30.0})
        self.assertEqual(order.volume(), np.float64(10.0))

        order.constraints.append(
            ConstraintConfig.from_dict(
                {
                    "kind": "linear",
                    "terms": [{"variable": "temperature", "coefficient": 1.0}],
                    "constant": {"min": 0.0, "max": 4.0},
                }
            )
        )

        self.assertEqual(order.volume(), np.float64(40.0))


def test_order_tags_defaults_to_empty_list() -> None:
    assert _make_order().tags == []


def test_order_tags_parses_scalar_string_from_raw() -> None:
    assert _make_order(raw=_minimal_raw(tags="experiment-1")).tags == ["experiment-1"]


def test_order_tags_parses_list_from_raw() -> None:
    assert _make_order(raw=_minimal_raw(tags=["foo", "bar"])).tags == ["foo", "bar"]


def test_order_tags_deduplicates_preserving_order() -> None:
    assert _make_order(raw=_minimal_raw(tags=["foo", "bar", "foo"])).tags == [
        "foo",
        "bar",
    ]


def test_order_tags_rejects_non_string_raw_value() -> None:
    with pytest.raises(EleanorError, match="tags must be a string or list of strings"):
        _ = _make_order(raw=_minimal_raw(tags=123))


def test_order_tags_rejects_list_with_non_string_element() -> None:
    with pytest.raises(EleanorError, match="tags must be a string or list of strings"):
        _ = _make_order(raw=_minimal_raw(tags=["valid", 42]))


def test_order_tags_kwarg_as_scalar_string_wraps_to_list() -> None:
    assert _make_order(tags="experiment-1").tags == ["experiment-1"]


def test_order_tags_kwarg_overrides_raw() -> None:
    order = _make_order(raw=_minimal_raw(tags="raw-tag"), tags=["kwarg-tag"])
    assert order.tags == ["kwarg-tag"]


def test_load_order_returns_order_as_is() -> None:
    order = _make_order(tags=["raw-tag"])
    returned = load_order(order)
    assert returned is order
    assert order.tags == ["raw-tag"]


def test_order_seed_is_generated_when_raw_and_kwarg_omit_it() -> None:
    seed = _make_order().seed

    assert isinstance(seed, int)
    assert 0 <= seed < 2**63


def test_order_seed_is_read_from_raw() -> None:
    assert _make_order(raw=_minimal_raw(seed=12345)).seed == 12345


def test_order_seed_zero_from_raw_is_preserved() -> None:
    """A falsy-but-explicit seed must not be replaced by a generated one."""
    assert _make_order(raw=_minimal_raw(seed=0)).seed == 0


def test_order_seed_kwarg_overrides_raw() -> None:
    assert _make_order(raw=_minimal_raw(seed=12345), seed=999).seed == 999


def test_order_seed_rejects_non_integer_raw_value() -> None:
    with pytest.raises(EleanorError):
        _ = _make_order(raw=_minimal_raw(seed="nope"))


def test_order_rng_is_determined_by_the_seed() -> None:
    """Two orders sharing a seed must draw the same stream."""
    a = _make_order(seed=4242)
    b = _make_order(seed=4242)

    assert a.rng.random(5).tolist() == b.rng.random(5).tolist()


def test_order_rng_differs_between_seeds() -> None:
    a = _make_order(seed=1)
    b = _make_order(seed=2)

    assert a.rng.random(5).tolist() != b.rng.random(5).tolist()


def test_order_rng_is_cached() -> None:
    """``rng`` must be one generator per order, not a fresh one per access."""
    order = _make_order(seed=7)

    assert order.rng is order.rng


def test_order_rng_is_not_a_dataclass_field() -> None:
    """``rng`` must stay out of ``fields()`` so it never reaches asdict/__eq__."""
    from dataclasses import fields

    order = _make_order(seed=7)
    _ = order.rng

    assert "rng" not in {f.name for f in fields(order)}


def _sentinel_vs_points() -> list[VSPoint]:
    """``load_order`` only rebinds ``vs_points``, so an opaque marker list suffices."""
    return cast(list[VSPoint], cast(object, [object()]))


def test_load_order_leaves_every_field_alone_when_no_overrides_given() -> None:
    order = _make_order(raw=_minimal_raw(seed=11, tags=["raw-tag"]))
    create_date, vs_points = order.create_date, order.vs_points

    returned = load_order(order)

    assert returned is order
    assert order.seed == 11
    assert order.tags == ["raw-tag"]
    assert order.create_date == create_date
    assert order.vs_points is vs_points


def test_load_order_overrides_seed_on_an_order_instance() -> None:
    order = _make_order(seed=11)
    _ = order.rng

    _ = load_order(order, seed=99)

    assert order.seed == 99


def test_load_order_seed_override_invalidates_the_cached_rng() -> None:
    """The stale generator must not survive a reseed."""
    order = _make_order(seed=11)
    _ = order.rng.random(3)

    _ = load_order(order, seed=99)

    assert order.rng.random(3).tolist() == np.random.default_rng(99).random(3).tolist()


def test_load_order_overrides_seed_when_the_rng_was_never_accessed() -> None:
    order = _make_order(seed=11)

    _ = load_order(order, seed=99)

    assert order.seed == 99
    assert order.rng.random(3).tolist() == np.random.default_rng(99).random(3).tolist()


def test_load_order_seed_zero_is_applied_as_an_override() -> None:
    """A falsy-but-explicit seed must not be read as 'no override'."""
    order = _make_order(seed=11)
    _ = order.rng

    _ = load_order(order, seed=0)

    assert order.seed == 0


def test_load_order_overrides_tags_on_an_order_instance() -> None:
    order = _make_order(raw=_minimal_raw(tags=["raw-tag"]))

    _ = load_order(order, tags=["kwarg-tag"])

    assert order.tags == ["kwarg-tag"]


def test_load_order_tags_override_accepts_a_scalar_string() -> None:
    order = _make_order(raw=_minimal_raw(tags=["raw-tag"]))

    _ = load_order(order, tags="experiment-1")

    assert order.tags == ["experiment-1"]


def test_load_order_tags_override_deduplicates_and_drops_empties() -> None:
    order = _make_order()

    _ = load_order(order, tags=["foo", "", "bar", "foo"])

    assert order.tags == ["foo", "bar"]


def test_load_order_tags_override_of_only_empty_strings_clears_the_tags() -> None:
    """``_prepare_tags`` returns ``[]`` rather than ``None``, so the override still lands."""
    order = _make_order(raw=_minimal_raw(tags=["raw-tag"]))

    _ = load_order(order, tags=[""])

    assert order.tags == []


def test_load_order_rejects_a_non_string_tags_override() -> None:
    order = _make_order(raw=_minimal_raw(tags=["raw-tag"]))

    with pytest.raises(EleanorError, match="tags must be a string or list of strings"):
        _ = load_order(order, tags=cast(list[str], cast(object, 123)))

    assert order.tags == ["raw-tag"]


def test_load_order_overrides_create_date_on_an_order_instance() -> None:
    order = _make_order()
    stamp = datetime(2020, 1, 2, 3, 4, 5)

    _ = load_order(order, create_date=stamp)

    assert order.create_date == stamp


def test_load_order_overrides_vs_points_on_an_order_instance() -> None:
    order = _make_order()
    points = _sentinel_vs_points()

    _ = load_order(order, vs_points=points)

    assert order.vs_points is points


def test_load_order_empty_vs_points_override_is_ignored() -> None:
    """``[]`` is falsy but not ``None``; the guard is ``is not None``, so it still applies."""
    order = _make_order(vs_points=_sentinel_vs_points())

    _ = load_order(order, vs_points=[])

    assert order.vs_points == []


def test_load_order_applies_every_override_in_one_call() -> None:
    order = _make_order(raw=_minimal_raw(seed=11, tags=["raw-tag"]))
    _ = order.rng
    stamp = datetime(2020, 1, 2, 3, 4, 5)
    points = _sentinel_vs_points()

    returned = load_order(order, seed=99, tags="kwarg-tag", create_date=stamp, vs_points=points)

    assert returned is order
    assert order.seed == 99
    assert order.tags == ["kwarg-tag"]
    assert order.create_date == stamp
    assert order.vs_points is points


def test_load_order_mutates_in_place_rather_than_copying() -> None:
    """Callers holding the original reference must see the overrides."""
    order = _make_order(seed=11)
    _ = order.rng

    returned = load_order(order, seed=99, tags="t")

    assert returned is order
    assert (order.seed, order.tags) == (99, ["t"])


def test_load_order_forwards_overrides_to_the_file_loader() -> None:
    order = _make_order()
    stamp = datetime(2020, 1, 2, 3, 4, 5)
    points = _sentinel_vs_points()

    with mock.patch("eleanor.order.Order.from_file", return_value=order) as from_file:
        returned = load_order("o.yaml", seed=99, tags="t", create_date=stamp, vs_points=points)

    assert returned is order
    from_file.assert_called_once_with("o.yaml", seed=99, tags="t", create_date=stamp, vs_points=points)


def test_load_order_does_not_re_apply_overrides_after_loading_from_a_file() -> None:
    """The file loader owns the overrides; the instance branch must not run as well."""
    order = _make_order(raw=_minimal_raw(seed=11, tags=["from-file"]))

    with mock.patch("eleanor.order.Order.from_file", return_value=order):
        returned = load_order("o.yaml", seed=99, tags="ignored")

    assert returned is order
    assert order.seed == 11
    assert order.tags == ["from-file"]
