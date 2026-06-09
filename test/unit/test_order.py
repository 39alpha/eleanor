import json
from os.path import join
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

import numpy as np
import pytest
from eleanor.exceptions import EleanorException
from eleanor.kernel.settings import KernelSettings
from eleanor.order import Order, Suppression, load_order
from eleanor.parameters import ValueParameter


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
    order_id=None,
    tags=None,
    vs_points=None,
    create_date=None,
    **overrides,
):
    """Build an Order with the kernel registry mocked out."""
    effective = raw if raw is not None else _minimal_raw(**overrides)
    with mock.patch(
        "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
    ):
        return Order.from_dict(
            cast(dict[str, object], cast(object, effective)),
            order_id=order_id,
            tags=tags,
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
        with self.assertRaises(EleanorException):
            _ = Suppression(None, None, [])

        s = Suppression.from_dict({"name": "Quartz", "except": ["H2O"]})
        self.assertEqual(s.name, "Quartz")
        self.assertEqual(s.type, None)
        self.assertEqual(s.exceptions, ["H2O"])

        s2 = Suppression.from_dict({"type": "mineral"}, name="Calcite")
        self.assertEqual(s2.name, "Calcite")
        self.assertEqual(s2.type, "mineral")

        with self.assertRaises(EleanorException):
            _ = Suppression.from_dict(
                cast(dict[str, object], cast(object, {"name": 1}))
            )
        with self.assertRaises(EleanorException):
            _ = Suppression.from_dict(
                cast(dict[str, object], cast(object, {"name": "x", "type": 2}))
            )
        with self.assertRaises(EleanorException):
            _ = Suppression.from_dict(
                cast(dict[str, object], cast(object, {"name": "x", "except": [1]}))
            )

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

    def test_order_reads_id_from_raw(self) -> None:
        """
        Ensure Order.__init__ reads an optional numeric ``id`` from raw
        and defaults to None when the field is absent.
        """
        order_with_id = _make_order(id=12)
        self.assertEqual(order_with_id.id, 12)

        order_without_id = _make_order()
        self.assertIsNone(order_without_id.id)

        with self.assertRaisesRegex(EleanorException, "id must be an integer"):
            _ = _make_order(id="not-an-int")

    def test_order_validation_and_kernel_branches(self) -> None:
        """
        Ensure order validation and kernel/navigator parsing branches behave correctly.
        """
        with self.assertRaises(EleanorException):
            _ = Order.from_dict(
                cast(dict[str, object], cast(object, _minimal_raw(name=1)))
            )
        with self.assertRaises(EleanorException):
            _ = Order.from_dict(
                cast(dict[str, object], cast(object, _minimal_raw(notes=1)))
            )
        with self.assertRaises(EleanorException):
            _ = Order.from_dict(
                cast(dict[str, object], cast(object, _minimal_raw(creator=1)))
            )

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
            EleanorException,
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

        with mock.patch(
            "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
        ):
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
                with self.assertRaises(EleanorException):
                    _ = Order.from_file(bad)

                self.assertIsInstance(load_order(yml), Order)

        o = _make_order(name="x")
        self.assertIs(load_order(o), o)

    def test_order_from_file_re_raises_eleanor_exception(self) -> None:
        """
        Ensure Order.from_file re-raises EleanorException from parser branches without wrapping.
        """
        with mock.patch(
            "eleanor.order.Order.from_yaml", side_effect=EleanorException("boom")
        ):
            with self.assertRaisesRegex(EleanorException, "boom"):
                _ = Order.from_file("test.yaml")

    def test_order_requires_kernel(self) -> None:
        """Ensure Order raises when kernel is absent."""
        with self.assertRaisesRegex(EleanorException, "kernel is required"):
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
        with mock.patch(
            "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
        ):
            with self.assertRaisesRegex(EleanorException, "temperature is required"):
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
        with mock.patch(
            "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
        ):
            with self.assertRaisesRegex(EleanorException, "pressure is required"):
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
        with mock.patch(
            "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
        ):
            with self.assertRaisesRegex(EleanorException, "elements must not be empty"):
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
            with self.assertRaisesRegex(EleanorException, "elements must not be empty"):
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
        """
        All-scalar parameters yield a volume of 1.0 (ValueParameter.volume returns 1.0
        for each, and the product of 1s is 1).
        """
        order = _make_order()
        self.assertEqual(order.volume(), np.float64(1.0))

    def test_order_volume_single_range_parameter(self) -> None:
        """
        A single RangeParameter contributes its width (max - min); all other
        parameters remain scalar so the total volume equals that width.
        """
        order = _make_order(temperature={"min": 20.0, "max": 30.0})
        self.assertEqual(order.volume(), np.float64(10.0))

    def test_order_volume_multiple_range_parameters(self) -> None:
        """
        Multiple RangeParameters each contribute their width; the total volume
        is the product of those widths.
        """
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            elements={"Na": {"min": 0.5, "max": 2.5}},
        )
        self.assertEqual(order.volume(), np.float64(20.0))

    def test_order_volume_list_parameter(self) -> None:
        """
        A ListParameter contributes its length; the total volume equals that
        count when all other parameters are scalar.
        """
        order = _make_order(pressure=[1.0, 2.0, 3.0])
        self.assertEqual(order.volume(), np.float64(3.0))

    def test_order_volume_mixed_range_and_list(self) -> None:
        """
        A mix of RangeParameter (width) and ListParameter (length) multiplies
        their contributions together.
        """
        order = _make_order(
            temperature={"min": 0.0, "max": 10.0},
            pressure=[1.0, 2.0],
        )
        self.assertEqual(order.volume(), np.float64(20.0))


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
    with pytest.raises(
        EleanorException, match="tags must be a string or list of strings"
    ):
        _ = _make_order(raw=_minimal_raw(tags=123))


def test_order_tags_rejects_list_with_non_string_element() -> None:
    with pytest.raises(
        EleanorException, match="tags must be a string or list of strings"
    ):
        _ = _make_order(raw=_minimal_raw(tags=["valid", 42]))


def test_order_tags_kwarg_as_scalar_string_wraps_to_list() -> None:
    assert _make_order(tags="experiment-1").tags == ["experiment-1"]


def test_order_tags_kwarg_overrides_raw() -> None:
    order = _make_order(raw=_minimal_raw(tags="raw-tag"), tags=["kwarg-tag"])
    assert order.tags == ["kwarg-tag"]


def test_order_kwargs_override_raw_id_and_tags() -> None:
    order = _make_order(
        raw=_minimal_raw(id=1, tags="raw-tag"), order_id=42, tags=["kwarg-tag"]
    )
    assert order.id == 42
    assert order.tags == ["kwarg-tag"]


def test_load_order_returns_order_as_is() -> None:
    order = _make_order(tags=["raw-tag"])
    order.id = 7
    returned = load_order(order)
    assert returned is order
    assert order.id == 7
    assert order.tags == ["raw-tag"]
