import click

import eleanor
from eleanor.cli.doctor import doctor
from eleanor.cli.gen import gen
from eleanor.cli.registry import available_cli_commands, get_factory
from eleanor.cli.run import run


@click.group()
@click.version_option(version=eleanor.__version__, prog_name="eleanor")
def main() -> None:
    """Run eleanor or interact with a generated dataset."""


main.add_command(run)
main.add_command(doctor)
main.add_command(gen)
for _name in sorted(available_cli_commands()):
    _spec = get_factory(_name)
    _parent = click.Group(
        name=_name,
        help=_spec.help or f"Commands provided by the {_name} plugin.",
    )
    for _cmd in _spec.commands:
        _parent.add_command(_cmd)
    main.add_command(_parent)
