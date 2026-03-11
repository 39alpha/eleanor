import json
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from os.path import join
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.order import (
    ConstraintConfig,
    HufferResult,
    NavigatorConfig,
    Order,
    Suborder,
    Suborders,
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
        Ensure basic config helper classes return expected defaults and dynamic loader behavior.
        """
        self.assertEqual(ConstraintConfig(type="x").volume(), 1.0)

        nav = NavigatorConfig("Random")
        self.assertEqual(nav.type, "eleanor.navigator.Random")

        fake_module = SimpleNamespace(MyNavigator=object())
        with mock.patch("eleanor.order.import_module", return_value=fake_module) as m:
            nav2 = NavigatorConfig("foo.bar.MyNavigator")
            loaded = nav2.load()
        m.assert_called_once_with("foo.bar")
        self.assertIs(loaded, fake_module.MyNavigator)

    def test_transformer_config_init_and_load(self):
        """
        Ensure transformer config parsing normalizes short names and resolves classes dynamically.
        """
        tf = TransformerConfig("GlassReactantEmbedder")
        self.assertEqual(tf.type, "eleanor.transformers.GlassReactantEmbedder")
        self.assertEqual(tf.args, {})

        fake_module = SimpleNamespace(MyTransformer=object())
        with mock.patch("eleanor.order.import_module", return_value=fake_module) as m:
            tf2 = TransformerConfig("pkg.mod.MyTransformer", args={"x": 1})
            loaded = tf2.load()
        m.assert_called_once_with("pkg.mod")
        self.assertIs(loaded, fake_module.MyTransformer)

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

    def test_huffer_result_from_scratch(self):
        """
        Ensure huffer scratch conversion uses null bytes for missing scratch and preserves provided zip.
        """
        h0 = HufferResult.from_scratch(None, exit_code=3)
        self.assertEqual(h0.exit_code, 3)
        self.assertEqual(h0.zip, bytes("\0", "ascii"))

        scratch = Scratch(id=None, zip=b"abc")
        h1 = HufferResult.from_scratch(scratch, exit_code=0, id=5)
        self.assertEqual(h1.id, 5)
        self.assertEqual(h1.zip, b"abc")

    def test_suborder_volume_and_suborders(self):
        """
        Ensure suborder/suborders volume aggregation behavior is computed as expected.
        """
        sub = Suborder(
            kernel=SimpleNamespace(parameters=lambda: [SimpleNamespace(volume=lambda: 2.0)]),
            temperature=SimpleNamespace(volume=lambda: 3.0),
            pressure=SimpleNamespace(volume=lambda: 5.0),
            elements={"Na": SimpleNamespace(volume=lambda: 7.0)},
            species={"Cl": SimpleNamespace(volume=lambda: 11.0)},
            reactants=[SimpleNamespace(volume=lambda: 13.0)],
            constraints=[SimpleNamespace(volume=lambda: 17.0)],
        )
        sub.suborders = SimpleNamespace(volume=lambda: 19.0)
        self.assertEqual(sub.volume(), 2.0 * 3.0 * 5.0 * 7.0 * 11.0 * 13.0 * 17.0 * 19.0)

        raw = {"orders": [{"name": "a", "creator": "u"}, {"name": "b", "creator": "u"}], "combined": True}
        subs = Suborders(raw)
        self.assertTrue(subs.combined)
        self.assertEqual(len(subs.suborders), 2)
        self.assertEqual(subs.volume(), 2.0)  # each minimal suborder volume == 1.0

        subs2 = Suborders([{"name": "a", "creator": "u"}])
        self.assertFalse(subs2.combined)
        self.assertEqual(subs2.volume(), 1.0)

    def test_suborder_from_dict_parsing(self):
        """
        Ensure suborder parsing handles optional fields and delegated loaders.
        """
        fake_settings = object()
        fake_kernel_module = SimpleNamespace(Settings=SimpleNamespace(from_dict=mock.Mock(return_value=fake_settings)))

        raw = {
            "name": "base",
            "notes": "n",
            "creator": "c",
            "kernel": {"type": "eq36"},
            "navigator": "Random",
            "temperature": 25.0,
            "pressure": 1.0,
            "elements": {"Na": 1.0},
            "species": {"H+": 2.0},
            "suppressions": ["Calcite", {"name": "Quartz"}],
            "reactants": {"R": {"type": "mineral", "amount": 1.0}},
            "constraints": [],
            "suborders": [{"name": "child", "creator": "c"}],
        }

        with (
            mock.patch("eleanor.order.import_kernel_module", return_value=fake_kernel_module),
            mock.patch("eleanor.order.AbstractReactant.from_dict", return_value="reactant") as reactant_from_dict,
        ):
            sub = Suborder.from_dict(raw)

        self.assertEqual(sub.name, "base")
        self.assertEqual(sub.notes, "n")
        self.assertEqual(sub.creator, "c")
        self.assertEqual(sub.navigator.type, "eleanor.navigator.Random")
        self.assertIsNotNone(sub.kernel)
        self.assertEqual(list(sub.elements.keys()), ["Na"])
        self.assertEqual(list(sub.species.keys()), ["H+"])
        self.assertEqual(len(sub.suppressions), 2)
        self.assertEqual(sub.reactants, ["reactant"])
        self.assertEqual(len(sub.suborders.suborders), 1)
        reactant_from_dict.assert_called_once()

    def test_suborder_from_dict_none_and_validation_errors(self):
        """
        Ensure suborder parsing handles None input and raises on invalid metadata types.
        """
        sub = Suborder.from_dict(None)
        self.assertEqual(sub.raw, {})

        with self.assertRaises(EleanorException):
            Suborder.from_dict({"name": 1})
        with self.assertRaises(EleanorException):
            Suborder.from_dict({"name": "x", "notes": 1})
        with self.assertRaises(EleanorException):
            Suborder.from_dict({"name": "x", "creator": 1})

    def test_suborder_navigator_dict_branch(self):
        """
        Ensure suborder parsing accepts navigator dict objects.
        """
        sub = Suborder.from_dict({"navigator": {"type": "foo.bar.Baz"}})
        self.assertEqual(sub.navigator.type, "foo.bar.Baz")

    def test_order_core_methods(self):
        """
        Ensure order parsing/hash/parameter collection/splitting work for common paths.
        """
        raw = {
            "name": "order1",
            "creator": "user",
            "temperature": 25.0,
            "pressure": 1.0,
            "elements": {"Na": 1.0},
            "species": {"H+": 2.0},
            "reactants": {},
            "suborders": [{"name": "child", "creator": "user", "temperature": 50.0}],
        }
        with mock.patch("eleanor.order.AbstractReactant.from_dict", return_value="reactant"):
            order = Order(raw)

        h0 = order.hash
        self.assertTrue(isinstance(h0, str) and len(h0) == 64)
        self.assertEqual(order.rehash(), order.hash)

        params = order.parameters()
        self.assertTrue(any(isinstance(p, ValueParameter) for p in params))

        split = order.split_suborders()
        self.assertEqual(len(split), 1)
        self.assertEqual(split[0].name, "child")
        self.assertEqual(split[0].temperature.value, 50.0)

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

        fake_settings = object()
        fake_kernel_module = SimpleNamespace(Settings=SimpleNamespace(from_dict=mock.Mock(return_value=fake_settings)))
        with mock.patch("eleanor.order.import_kernel_module", return_value=fake_kernel_module):
            order = Order(
                {
                    "name": "o",
                    "creator": "u",
                    "kernel": {"type": "eq36"},
                    "navigator": "Random",
                }
            )
        self.assertIsNotNone(order.kernel)
        self.assertEqual(order.navigator.type, "eleanor.navigator.Random")

    def test_order_transformer_configs_parse_and_validate(self):
        """
        Ensure order transformer configs support string/dict forms and reject invalid entries.
        """
        order = Order(
            {
                "name": "o",
                "creator": "u",
                "transformers": [
                    "GlassReactantEmbedder",
                    {"type": "pkg.mod.MyTransformer", "args": {"filename": "x.csv"}},
                ],
            }
        )
        self.assertEqual(len(order.transformers), 2)
        self.assertEqual(order.transformers[0].type, "eleanor.transformers.GlassReactantEmbedder")
        self.assertEqual(order.transformers[1].type, "pkg.mod.MyTransformer")
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
