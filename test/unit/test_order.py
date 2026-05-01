import json
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from os.path import join
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.order import (
    ConstraintConfig,
    NavigatorConfig,
    Order,
    Suppression,
    TransformerConfig,
    load_order,
)
from eleanor.parameters import ValueParameter
from eleanor.variable_space import Scratch

from .common import TestCase


class TestOrder(TestCase):
    """
    Tests of the eleanor.order module.
    """

    def test_constraint_and_navigator_config(self):
        """
        Ensure basic config helper classes return expected defaults.
        """
        self.assertEqual(ConstraintConfig(type="x").volume(), 1.0)

        nav = NavigatorConfig("random")
        self.assertEqual(nav.type, "random")
        self.assertEqual(nav.args, {})

        nav2 = NavigatorConfig("my_plugin", args={"seed": 42})
        self.assertEqual(nav2.type, "my_plugin")
        self.assertEqual(nav2.args, {"seed": 42})

    def test_transformer_config_init(self):
        """
        Ensure transformer config parsing preserves short names and args.
        """
        tf = TransformerConfig("transformer")
        self.assertEqual(tf.type, "transformer")
        self.assertEqual(tf.args, {})

        tf2 = TransformerConfig("my_transformer", args={"x": 1})
        self.assertEqual(tf2.type, "my_transformer")
        self.assertEqual(tf2.args, {"x": 1})

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
            Suppression.from_dict({"name": 1})
        with self.assertRaises(EleanorException):
            Suppression.from_dict({"name": "x", "type": 2})
        with self.assertRaises(EleanorException):
            Suppression.from_dict({"name": "x", "except": [1]})


    def test_order_core_methods(self):
        """
        Ensure order parsing, parameter collection, and splitting work for common paths.
        """
        raw = {
            "name": "order1",
            "creator": "user",
            "temperature": 25.0,
            "pressure": 1.0,
            "elements": {"Na": 1.0},
            "species": {"H+": 2.0},
            "reactants": {},
        }
        with mock.patch("eleanor.order.AbstractReactant.from_dict", return_value="reactant"):
            order = Order(raw)

        params = order.parameters()
        self.assertTrue(any(isinstance(p, ValueParameter) for p in params))

    def test_order_ignores_suborders_key(self):
        """
        Ensure Order construction succeeds when raw contains suborders and ignores that content.
        """
        order = Order(
            {
                "name": "o",
                "creator": "u",
                "temperature": 25.0,
                "suborders": [{"name": "child", "temperature": 100.0}],
            }
        )

        self.assertEqual(order.name, "o")
        self.assertIsNotNone(order.temperature)
        self.assertEqual(order.temperature.value, 25.0)

    def test_order_reads_id_from_raw(self):
        """
        Ensure Order.__init__ reads an optional numeric ``id`` from raw
        and defaults to None when the field is absent.
        """
        order_with_id = Order({"id": 12, "name": "o", "creator": "u"})
        self.assertEqual(order_with_id.id, 12)

        order_without_id = Order({"name": "o", "creator": "u"})
        self.assertIsNone(order_without_id.id)

        with self.assertRaisesRegex(EleanorException, "id must be an integer"):
            Order({"id": "not-an-int", "name": "o", "creator": "u"})

    def test_order_reads_tag_from_raw_and_defaults_to_empty_string(self):
        """
        Ensure Order.__init__ reads an optional ``tag`` from raw, defaults to
        the empty string when the field is absent, and rejects non-string values.
        """
        order_with_tag = Order({"name": "o", "creator": "u", "tag": "experiment-1"})
        self.assertEqual(order_with_tag.tag, "experiment-1")

        order_without_tag = Order({"name": "o", "creator": "u"})
        self.assertEqual(order_without_tag.tag, "")

        with self.assertRaisesRegex(EleanorException, "tag must be a string"):
            Order({"name": "o", "creator": "u", "tag": 123})

    def test_order_kwargs_override_raw_id_and_tag(self):
        """
        Ensure explicit order_id and tag kwargs to Order.__init__ take precedence
        over matching fields in the raw dict.
        """
        order = Order(
            {"id": 1, "name": "o", "creator": "u", "tag": "raw-tag"},
            order_id=42,
            tag="kwarg-tag",
        )
        self.assertEqual(order.id, 42)
        self.assertEqual(order.tag, "kwarg-tag")

    def test_load_order_returns_order_as_is(self):
        """
        Ensure load_order returns an already-loaded Order unchanged.
        """
        order = Order({"name": "o", "creator": "u", "tag": "raw-tag"})
        order.id = 7
        returned = load_order(order)
        self.assertIs(returned, order)
        self.assertEqual(order.id, 7)
        self.assertEqual(order.tag, "raw-tag")

    def test_order_post_init_validation_and_kernel_branches(self):
        """
        Ensure order post-init validates metadata and handles kernel/navigator parsing branches.
        """
        with self.assertRaises(EleanorException):
            Order({"name": 1, "creator": "u"})
        with self.assertRaises(EleanorException):
            Order({"name": "x", "creator": "u", "notes": 1})
        with self.assertRaises(EleanorException):
            Order({"name": "x", "creator": 1})

        from eleanor.kernel.config import Settings as KernelSettings

        fake_settings = KernelSettings(timeout=None)
        fake_spec = SimpleNamespace(
            settings_from_dict=mock.Mock(return_value=fake_settings),
            build=mock.Mock(),
        )
        with mock.patch("eleanor.kernel.registry.get_factory", return_value=fake_spec):
            order = Order(
                {
                    "name": "o",
                    "creator": "u",
                    "kernel": {"type": "eq36", "args": {}},
                    "navigator": "Random",
                }
            )
        self.assertIsNotNone(order.kernel)
        self.assertEqual(order.navigator.type, "Random")

    def test_order_transformer_configs_parse_and_validate(self):
        """
        Ensure order transformer configs support string/dict forms and reject invalid entries.
        """
        order = Order(
            {
                "name": "o",
                "creator": "u",
                "transformers": [
                    "my_transformer_a",
                    {"type": "my_transformer", "args": {"filename": "x.csv"}},
                ],
            }
        )
        self.assertEqual(len(order.transformers), 2)
        self.assertEqual(order.transformers[0].type, "my_transformer_a")
        self.assertEqual(order.transformers[1].type, "my_transformer")
        self.assertEqual(order.transformers[1].args, {"filename": "x.csv"})

        with self.assertRaises(EleanorException):
            Order({"name": "bad", "creator": "u", "transformers": [123]})

    def test_order_parameters_includes_kernel_and_reactant_parameters(self):
        """
        Ensure :meth:`Order.parameters` includes kernel and reactant-derived parameter lists.
        """
        with mock.patch("eleanor.order.AbstractReactant.from_dict", return_value="reactant"):
            order = Order({"name": "o", "creator": "u"})
        kparam = ValueParameter("k", None, 1.0)
        rparam = ValueParameter("r", None, 2.0)
        order.kernel = SimpleNamespace(parameters=lambda: [kparam])
        order.reactants = [SimpleNamespace(parameters=lambda: [rparam])]

        params = order.parameters()
        self.assertIn(kparam, params)
        self.assertIn(rparam, params)

    def test_order_file_loaders_and_load_order(self):
        """
        Ensure order file/string loaders and load_order dispatch behave across formats.
        """
        raw = {"name": "o", "creator": "u"}
        with TemporaryDirectory() as tmp:
            yml = join(tmp, "o.yaml")
            toml = join(tmp, "o.toml")
            js = join(tmp, "o.json")
            bad = join(tmp, "o.ini")

            with open(yml, "w") as f:
                f.write("name: o\ncreator: u\n")
            with open(toml, "w") as f:
                f.write('name = "o"\ncreator = "u"\n')
            with open(js, "w") as f:
                json.dump(raw, f)
            with open(bad, "w") as f:
                f.write("[x]\n")

            self.assertIsInstance(Order.from_yaml(yml), Order)
            self.assertIsInstance(Order.from_toml(toml), Order)
            self.assertIsInstance(Order.from_json(js), Order)
            self.assertIsInstance(Order.from_yamls("name: o\ncreator: u\n"), Order)
            self.assertIsInstance(Order.from_tomls('name = "o"\ncreator = "u"\n'), Order)
            self.assertIsInstance(Order.from_jsons('{"name":"o","creator":"u"}'), Order)
            self.assertIsInstance(Order.from_file(yml), Order)
            yml2 = join(tmp, "o.yml")
            with open(yml2, "w") as f:
                f.write("name: o\ncreator: u\n")
            self.assertIsInstance(Order.from_file(yml2), Order)
            self.assertIsInstance(Order.from_file(toml), Order)
            self.assertIsInstance(Order.from_file(js), Order)
            with self.assertRaises(EleanorException):
                Order.from_file(bad)

            self.assertIsInstance(load_order(yml), Order)

        o = Order({"name": "x", "creator": "u"})
        self.assertIs(load_order(o), o)

    def test_order_from_file_re_raises_eleanor_exception(self):
        """
        Ensure Order.from_file re-raises EleanorException from parser branches without wrapping.
        """
        with mock.patch("eleanor.order.Order.from_yaml", side_effect=EleanorException("boom")):
            with self.assertRaisesRegex(EleanorException, "boom"):
                Order.from_file("test.yaml")
