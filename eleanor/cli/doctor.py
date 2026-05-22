import sys

import click

import eleanor
from eleanor.cli.registry import available_cli_commands
from eleanor.executor.registry import available_executors
from eleanor.kernel.registry import available_kernels
from eleanor.navigator.registry import available_navigators
from eleanor.output.registry import available_output_sinks
from eleanor.plugin import PLUGIN_API_VERSIONS


@click.command()
def doctor() -> None:
    """Print diagnostic information about this eleanor installation."""
    click.echo()
    click.echo(f"  {click.style('eleanor', bold=True)} {click.style(eleanor.__version__, fg='green')}")
    click.echo(f"  {click.style('Python', dim=True)}  {click.style(sys.version.split(chr(10))[0], dim=True)}")
    click.echo()

    click.echo(f"  {click.style('Plugin API versions', bold=True)}")
    for kind in sorted(PLUGIN_API_VERSIONS):
        current, floor = PLUGIN_API_VERSIONS[kind]
        label = f"  {kind:12s}"
        versions = f"v{current} {click.style('(min v' + str(floor) + ')', dim=True)}"
        click.echo(f"  {label}  {versions}")
    click.echo()

    sections = [
        ("Executors", sorted(available_executors())),
        ("Kernels", sorted(available_kernels())),
        ("Navigators", sorted(available_navigators())),
        ("Outputs", sorted(available_output_sinks())),
        ("CLI commands", sorted(available_cli_commands())),
    ]
    for heading, names in sections:
        click.echo(f"  {click.style(heading, bold=True)}")
        if names:
            for name in names:
                click.echo(f"    {click.style('•', fg='green')} {name}")
        else:
            click.echo(f"    {click.style('(none)', dim=True)}")
    click.echo()
