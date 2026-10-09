import sys
from traceback import print_exception

import click

from eleanor.order import load_order
from eleanor.util import NumberFormat


@click.group()
def order() -> None:
    """Perform operations on orders."""


@order.command("volume")
@click.argument("order", type=click.Path(exists=True, dir_okay=False))
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
        volume = format.fmt(load_order(order).volume(), precision=precision).lower()
    except Exception as e:
        if verbose:
            print_exception(e)
            sys.exit(1)
        else:
            msg = f"failed to compute the order volume - {e}"
            raise click.ClickException(msg) from e

    click.echo(volume)
