import sys

import click

from eleanor.cli.util import handle_exception
from eleanor.order import load_order
from eleanor.util import NumberFormat


@click.group()
def order() -> None:
    """Perform operations on orders."""


@order.command("volume")
@click.argument(
    "order",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
    help="A path to an order file; pass - to read an order from stdin",
)
@click.option(
    "-p",
    "--precision",
    type=click.IntRange(min=0),
    default=3,
    show_default=True,
    help="Number of digits: significant figures for adaptive, decimal places otherwise.",
)
@click.option(
    "-f",
    "--format",
    type=click.Choice(NumberFormat, case_sensitive=False),
    default="adaptive",
    show_default=True,
    help="Floating-point format.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose output.")
def order_volume(
    order: str,
    precision: int = 3,
    format: NumberFormat = NumberFormat.ADAPTIVE,
    verbose: bool = False,
) -> None:
    """Print the volume of an order's parameter space."""
    try:
        source = sys.stdin if order == "-" else order
        parsed_order = load_order(source)
    except Exception as e:
        handle_exception(e, "failed to load the order", verbose=verbose)

    try:
        volume = parsed_order.volume()
    except Exception as e:
        handle_exception(e, "failed to compute the order volume", verbose=verbose)

    volume_str = format.fmt(volume, precision=precision).lower()
    click.echo(volume_str)
