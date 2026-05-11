"""``eleanor gen config`` and ``eleanor gen order`` — emit starter templates.

Templates live as plain files under ``eleanor/cli/templates/`` and are loaded
via :mod:`importlib.resources` so they work both from source checkouts and
installed wheels.
"""

from importlib.resources import as_file, files

import click

from eleanor.config import Config, load_config
from eleanor.order import Order, load_order

_TEMPLATES_PKG = files("eleanor.cli").joinpath("templates")

_TARGETS = ("config", "order")
_FORMATS = ("yaml", "toml", "json")


def _load_template(target: str, fmt: str) -> str | None:
    if target not in _TARGETS or fmt not in _FORMATS:
        return None
    return _TEMPLATES_PKG.joinpath(f"{target}.{fmt}").read_text(encoding="utf-8")


def validate_template(target: str, fmt: str) -> Config | Order:
    """Load a template and parse it through :func:`load_config` or :func:`load_order`.

    Raises on any parse or validation error, confirming that the shipped
    template is at least superficially valid.
    """
    if target not in _TARGETS or fmt not in _FORMATS:
        raise ValueError(f"unknown template: {target}/{fmt}")
    with as_file(_TEMPLATES_PKG.joinpath(f"{target}.{fmt}")) as path:
        if target == "config":
            return load_config(str(path))
        return load_order(str(path))


@click.group()
def gen() -> None:
    """Generate starter template files."""


def _emit_template(target: str, fmt: str) -> None:
    template = _load_template(target, fmt)
    if template is None:
        raise click.ClickException(f"unknown target/format: {target}/{fmt}")
    click.echo(template, nl=False)


@gen.command("config")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["yaml", "toml", "json"]),
    default="yaml",
    help="Output format.",
)
def gen_config(fmt: str) -> None:
    """Generate a starter configuration file."""
    _emit_template("config", fmt)


@gen.command("order")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["yaml", "toml", "json"]),
    default="yaml",
    help="Output format.",
)
def gen_order(fmt: str) -> None:
    """Generate a starter order file."""
    _emit_template("order", fmt)
