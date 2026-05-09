"""``eleanor gen config`` and ``eleanor gen order`` — emit starter templates.

Templates live as plain files under ``eleanor/cli/templates/`` and are loaded
via :mod:`importlib.resources` so they work both from source checkouts and
installed wheels.
"""

import argparse
import sys
from importlib.resources import as_file, files

from eleanor.config import Config, load_config
from eleanor.order import Order, load_order

_TEMPLATES_PKG = files("eleanor.cli").joinpath("templates")

#: Filename looked up inside ``templates/`` for each (target, format) pair.
_TEMPLATE_FILES: dict[tuple[str, str], str] = {
    ("config", "yaml"): "config.yaml",
    ("config", "toml"): "config.toml",
    ("config", "json"): "config.json",
    ("order", "yaml"): "order.yaml",
    ("order", "toml"): "order.toml",
    ("order", "json"): "order.json",
}


def _load_template(target: str, fmt: str) -> str | None:
    filename = _TEMPLATE_FILES.get((target, fmt))
    if filename is None:
        return None
    return _TEMPLATES_PKG.joinpath(filename).read_text(encoding="utf-8")


def validate_template(target: str, fmt: str) -> Config | Order:
    """Load a template and parse it through :func:`load_config` or :func:`load_order`.

    Raises on any parse or validation error, confirming that the shipped
    template is at least superficially valid.
    """
    filename = _TEMPLATE_FILES.get((target, fmt))
    if filename is None:
        raise ValueError(f"unknown template: {target}/{fmt}")
    with as_file(_TEMPLATES_PKG.joinpath(filename)) as path:
        if target == "config":
            return load_config(str(path))
        return load_order(str(path))


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = "Generate starter template files"
    subs = parser.add_subparsers(required=True, dest="gen_target")

    for name, help_text in (
        ("config", "Generate a starter configuration file"),
        ("order", "Generate a starter order file"),
    ):
        sub = subs.add_parser(name, help=help_text)
        _ = sub.add_argument(
            "-f",
            "--format",
            choices=("yaml", "toml", "json"),
            default="yaml",
            dest="fmt",
            help="output format (default: %(default)s)",
        )
        sub.set_defaults(func=execute, gen_target=name)

    parser.set_defaults(func=execute)
    return parser


def execute(_parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    target: str = getattr(ns, "gen_target", "")
    fmt: str = getattr(ns, "fmt", "yaml")
    template = _load_template(target, fmt)
    if template is None:
        print(f"error: unknown target/format: {target}/{fmt}", file=sys.stderr)
        sys.exit(1)
    _ = sys.stdout.write(template)
