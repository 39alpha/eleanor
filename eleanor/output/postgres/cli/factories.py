from typing import TYPE_CHECKING

from eleanor.plugin import SimplePluginSpec

if TYPE_CHECKING:
    import click


def build_postgres_group() -> click.Group:
    import click

    from eleanor.output.postgres.cli.bulkload import bulkload
    from eleanor.output.postgres.cli.dump import dump
    from eleanor.output.postgres.cli.migrate import migrate
    from eleanor.output.postgres.cli.schema import schema
    from eleanor.output.postgres.cli.scratch import scratch

    cmd = click.Group("postgres", help="Postgres output sink commands.")
    cmd.add_command(bulkload)
    cmd.add_command(dump)
    cmd.add_command(migrate)
    cmd.add_command(schema)
    cmd.add_command(scratch)

    return cmd


postgres_commands_spec = SimplePluginSpec(
    build=build_postgres_group,
    plugin_api_version=1,
)


__all__ = ["postgres_commands_spec"]
