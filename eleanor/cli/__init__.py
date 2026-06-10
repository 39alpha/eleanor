import click

import eleanor
from eleanor.cli.doctor import doctor
from eleanor.cli.gen import gen
from eleanor.cli.registry import available_cli_commands, get_factory
from eleanor.cli.run import run
from eleanor.exceptions import EleanorError
from eleanor.plugin import SimplePluginSpec


@click.group()
@click.version_option(version=eleanor.__version__, prog_name="eleanor")
def main() -> None:
    """Run eleanor or interact with a generated dataset."""


main.add_command(run)
main.add_command(doctor)
main.add_command(gen)

for _name in sorted(available_cli_commands()):
    _spec = get_factory(_name)

    if not isinstance(_spec, SimplePluginSpec):
        msg = f"cli command plugin {_name!r} must be a {SimplePluginSpec.__name__}, got {type(_spec).__name__}"
        raise EleanorError(msg)

    _cmd_or_group = _spec.build()
    if not isinstance(_cmd_or_group, (click.Group, click.Command)):
        msg = f"cli command plugin {_name!r} build a click.Group or click.Command, got {type(_cmd_or_group).__name__}"
        raise EleanorError(msg)

    main.add_command(_cmd_or_group)


__all__ = [
    "main",
]
