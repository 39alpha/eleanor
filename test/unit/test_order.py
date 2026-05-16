import json
from os.path import join
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest import mock

import numpy as np

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.kernel.config import Settings as KernelSettings
from eleanor.order import (
    NavigatorConfig,
    Order,
    OrderRaw,
    Suppression,
    SuppressionRaw,
    load_order,
)
from eleanor.parameters import ValueParameter

from .common import TestCase


def _minimal_raw(**overrides):
    """Return a raw dict with all required Order fields populated."""
    base = {
        "name": "o",
        "creator": "u",
        "kernel": {"type": "eq36", "args": {}},
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
    tag=None,
    vs_points=None,
    create_date=None,
    **overrides,
):
    """Build an Order with the kernel registry mocked out."""
    effective = raw if raw is not None else _minimal_raw(**overrides)
    with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
        return Order(
            cast(OrderRaw, cast(object, effective)),
            order_id=order_id,
            tag=tag,
            vs_points=vs_points,
            create_date=create_date,
        )


class TestOrder(TestCase):
    """
    Tests of the eleanor.order module.
    """

    def test_constraint_and_navigator_config(self):
        """
        Ensure basic config helper classes return expected defaults.
        """
        nav = NavigatorConfig("random")
        self.assertEqual(nav.type, "random")
        self.assertEqual(nav.args, {})

        nav2 = NavigatorConfig("my_plugin", args={"seed": 42})
        self.assertEqual(nav2.type, "my_plugin")
        self.assertEqual(nav2.args, {"seed": 42})

    def test_suppression(self):
        """
        Ensure suppression construction and parsing validate name/type/exception constraints.
        """
        with self.assertRaises(EleanorException):
            Suppression(None, None, [])

        s = Suppression.from_dict({"name": "Quartz", "except": ["H2O"]})
        self.assertEqual(s.name, "Quartz")
        self.assertEqual(s.type, None)
        self.assertEqual(s.exceptions, ["H2O"])

        s2 = Suppression.from_dict({"type": "mineral"}, name="Calcite")
        self.assertEqual(s2.name, "Calcite")
        self.assertEqual(s2.type, "mineral")

        with self.assertRaises(EleanorException):
            Suppression.from_dict(cast(SuppressionRaw, cast(object, {"name": 1})))
        with self.assertRaises(EleanorException):
            Suppression.from_dict(cast(SuppressionRaw, cast(object, {"name": "x", "type": 2})))
        with self.assertRaises(EleanorException):
            Suppression.from_dict(cast(SuppressionRaw, cast(object, {"name": "x", "except": [1]})))

    def test_order_core_methods(self):
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

    def test_order_reads_id_from_raw(self):
        """
        Ensure Order.__init__ reads an optional numeric ``id`` from raw
        and defaults to None when the field is absent.
        """
        order_with_id = _make_order(id=12)
        self.assertEqual(order_with_id.id, 12)

        order_without_id = _make_order()
        self.assertIsNone(order_without_id.id)

        with self.assertRaisesRegex(EleanorException, "id must be an integer"):
            _make_order(id="not-an-int")

    def test_order_reads_tag_from_raw_and_defaults_to_empty_string(self):
        """
        Ensure Order.__init__ reads an optional ``tag`` from raw, defaults to
        the empty string when the field is absent, and rejects non-string values.
        """
        order_with_tag = _make_order(tag="experiment-1")
        self.assertEqual(order_with_tag.tag, "experiment-1")

        order_without_tag = _make_order()
        self.assertEqual(order_without_tag.tag, "")

        with self.assertRaisesRegex(EleanorException, "tag must be a string"):
            _make_order(raw=_minimal_raw(tag=123))

    def test_order_kwargs_override_raw_id_and_tag(self):
        """
        Ensure explicit order_id and tag kwargs to Order.__init__ take precedence
        over matching fields in the raw dict.
        """
        order = _make_order(
            raw=_minimal_raw(id=1, tag="raw-tag"),
            order_id=42,
            tag="kwarg-tag",
        )
        self.assertEqual(order.id, 42)
        self.assertEqual(order.tag, "kwarg-tag")

    def test_load_order_returns_order_as_is(self):
        """
        Ensure load_order returns an already-loaded Order unchanged.
        """
        order = _make_order(tag="raw-tag")
        order.id = 7
        returned = load_order(order)
        self.assertIs(returned, order)
        self.assertEqual(order.id, 7)
        self.assertEqual(order.tag, "raw-tag")

    def test_order_validation_and_kernel_branches(self):
        """
        Ensure order validation and kernel/navigator parsing branches behave correctly.
        """
        with self.assertRaises(EleanorException):
            Order(cast(OrderRaw, cast(object, _minimal_raw(name=1))))
        with self.assertRaises(EleanorException):
            Order(cast(OrderRaw, cast(object, _minimal_raw(notes=1))))
        with self.assertRaises(EleanorException):
            Order(cast(OrderRaw, cast(object, _minimal_raw(creator=1))))

        order = _make_order(
            name="o",
            creator="u",
            kernel={"type": "eq36", "args": {}},
            navigator="Random",
        )
        self.assertIsNotNone(order.kernel)
        self.assertEqual(order.navigator.type, "Random")

    def test_order_parameters_includes_kernel_and_reactant_parameters(self):
        """
        Ensure :meth:`Order.parameters` includes kernel and reactant-derived parameter lists.
        """
        order = _make_order()
        kparam = ValueParameter("k", None, np.float64(1.0))
        rparam = ValueParameter("r", None, np.float64(2.0))
        setattr(order, "kernel", SimpleNamespace(parameters=lambda: [kparam]))
        setattr(order, "reactants", [SimpleNamespace(parameters=lambda: [rparam])])

        params = order.parameters()
        self.assertIn(kparam, params)
        self.assertIn(rparam, params)

    def test_order_rejects_duplicate_names_between_reactants_and_combined_components(self):
        """
        Ensure duplicate concrete names across standalone reactants and combined components are rejected.
        """
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            "appears more than once across reactants and combined-reactant components",
        ):
            _make_order(
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

    def test_order_file_loaders_and_load_order(self):
        """
        Ensure order file/string loaders and load_order dispatch behave across formats.
        """
        raw = _minimal_raw()
        yaml_content = (
            "name: o\n"
            "creator: u\n"
            "kernel:\n"
            "  type: eq36\n"
            "  args: {}\n"
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
            'type = "eq36"\n'
            "[kernel.args]\n"
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
                    handle.write(yaml_content)
                with open(yml2, "w") as handle:
                    handle.write(yaml_content)
                with open(toml, "w") as handle:
                    handle.write(toml_content)
                with open(js, "w") as handle:
                    handle.write(json_content)
                with open(bad, "w") as handle:
                    handle.write("[x]\n")

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
                    Order.from_file(bad)

                self.assertIsInstance(load_order(yml), Order)

        o = _make_order(name="x")
        self.assertIs(load_order(o), o)

    def test_order_from_file_re_raises_eleanor_exception(self):
        """
        Ensure Order.from_file re-raises EleanorException from parser branches without wrapping.
        """
        with mock.patch("eleanor.order.Order.from_yaml", side_effect=EleanorException("boom")):
            with self.assertRaisesRegex(EleanorException, "boom"):
                Order.from_file("test.yaml")

    def test_order_requires_kernel(self):
        """Ensure Order raises when kernel is absent."""
        with self.assertRaisesRegex(EleanorException, "kernel is required"):
            Order({"name": "o", "creator": "u", "temperature": 25.0, "pressure": 1.0, "elements": {"Na": 1.0}})

    def test_order_requires_temperature(self):
        """Ensure Order raises when temperature is absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorException, "temperature is required"):
                Order(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {"type": "eq36", "args": {}},
                        "pressure": 1.0,
                        "elements": {"Na": 1.0},
                    }
                )

    def test_order_requires_pressure(self):
        """Ensure Order raises when pressure is absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorException, "pressure is required"):
                Order(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {"type": "eq36", "args": {}},
                        "temperature": 25.0,
                        "elements": {"Na": 1.0},
                    }
                )

    def test_order_requires_nonempty_elements(self):
        """Ensure Order raises when elements is empty or absent."""
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
            with self.assertRaisesRegex(EleanorException, "elements must not be empty"):
                Order(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {"type": "eq36", "args": {}},
                        "temperature": 25.0,
                        "pressure": 1.0,
                    }
                )
            with self.assertRaisesRegex(EleanorException, "elements must not be empty"):
                Order(
                    {
                        "name": "o",
                        "creator": "u",
                        "kernel": {"type": "eq36", "args": {}},
                        "temperature": 25.0,
                        "pressure": 1.0,
                        "elements": {},
                    }
                )

    def test_order_volume_all_scalar(self):
        """
        All-scalar parameters yield a volume of 1.0 (ValueParameter.volume returns 1.0
        for each, and the product of 1s is 1).
        """
        order = _make_order()
        self.assertEqual(order.volume(), np.float64(1.0))

    def test_order_volume_single_range_parameter(self):
        """
        A single RangeParameter contributes its width (max - min); all other
        parameters remain scalar so the total volume equals that width.
        """
        order = _make_order(temperature={"min": 20.0, "max": 30.0})
        self.assertEqual(order.volume(), np.float64(10.0))

    def test_order_volume_multiple_range_parameters(self):
        """
        Multiple RangeParameters each contribute their width; the total volume
        is the product of those widths.
        """
        order = _make_order(
            temperature={"min": 20.0, "max": 30.0},
            elements={"Na": {"min": 0.5, "max": 2.5}},
        )
        self.assertEqual(order.volume(), np.float64(20.0))

    def test_order_volume_list_parameter(self):
        """
        A ListParameter contributes its length; the total volume equals that
        count when all other parameters are scalar.
        """
        order = _make_order(pressure=[1.0, 2.0, 3.0])
        self.assertEqual(order.volume(), np.float64(3.0))

    def test_order_volume_mixed_range_and_list(self):
        """
        A mix of RangeParameter (width) and ListParameter (length) multiplies
        their contributions together.
        """
        order = _make_order(
            temperature={"min": 0.0, "max": 10.0},
            pressure=[1.0, 2.0],
        )
        self.assertEqual(order.volume(), np.float64(20.0))
