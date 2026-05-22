from typing import override

from click.testing import CliRunner

from eleanor.cli import main
from eleanor.cli.gen import _FORMATS, validate_template
from eleanor.config import Config
from eleanor.order import Order

from .common import TestCase


class TestGenTemplateValidation(TestCase):
    """Ensure every shipped template parses through load_config / load_order."""

    def test_config_templates_are_valid(self):
        for fmt in _FORMATS:
            with self.subTest(fmt=fmt):
                result = validate_template("config", fmt)
                self.assertIsInstance(result, Config)

    def test_order_templates_are_valid(self):
        for fmt in _FORMATS:
            with self.subTest(fmt=fmt):
                result = validate_template("order", fmt)
                self.assertIsInstance(result, Order)

    def test_unknown_template_raises(self):
        with self.assertRaises(ValueError):
            _ = validate_template("bogus", "yaml")


class TestGenTemplateCrossFormat(TestCase):
    """Ensure YAML, TOML and JSON templates parse to equivalent objects."""

    def test_config_formats_agree(self):
        configs = {fmt: validate_template("config", fmt) for fmt in ("yaml", "toml", "json")}
        ref = configs["yaml"]
        for fmt in ("toml", "json"):
            with self.subTest(fmt=fmt):
                other = configs[fmt]
                self.assertIsInstance(other, Config)
                assert isinstance(ref, Config) and isinstance(other, Config)
                self.assertEqual(ref.output.kind, other.output.kind)
                self.assertEqual(ref.output.args, other.output.args)
                self.assertEqual(ref.parallel.backend, other.parallel.backend)
                self.assertEqual(ref.parallel.chunks_per_worker, other.parallel.chunks_per_worker)

    def test_order_formats_agree(self):
        orders = {fmt: validate_template("order", fmt) for fmt in ("yaml", "toml", "json")}
        ref = orders["yaml"]
        for fmt in ("toml", "json"):
            with self.subTest(fmt=fmt):
                other = orders[fmt]
                self.assertIsInstance(other, Order)
                assert isinstance(ref, Order) and isinstance(other, Order)
                self.assertEqual(ref.name, other.name)
                self.assertEqual(ref.creator, other.creator)
                self.assertEqual(ref.notes, other.notes)
                self.assertEqual(ref.kernel.type, other.kernel.type)
                self.assertEqual(ref.navigator.type, other.navigator.type)
                self.assertEqual(ref.navigator.args, other.navigator.args)
                self.assertEqual(ref.temperature, other.temperature)
                self.assertEqual(ref.pressure, other.pressure)
                self.assertEqual(ref.elements.keys(), other.elements.keys())
                self.assertEqual(ref.species.keys(), other.species.keys())
                self.assertEqual(len(ref.reactants), len(other.reactants))
                for r, o in zip(ref.reactants, other.reactants):
                    self.assertEqual(r.name, o.name)
                    self.assertEqual(r.type, o.type)


class TestGenCli(TestCase):
    """Smoke-test the Click CLI entry point."""

    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_cli_emits_config_yaml(self):
        result = self.runner.invoke(main, ["gen", "config", "--format", "yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("output:", result.output)

    def test_cli_emits_order_toml(self):
        result = self.runner.invoke(main, ["gen", "order", "--format", "toml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("[kernel]", result.output)
