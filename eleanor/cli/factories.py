from typing import TYPE_CHECKING

from eleanor.plugin import SimplePluginSpec

if TYPE_CHECKING:
    import click


def build_postgres_group() -> click.Group:
    import click

    from eleanor.output.postgres.cli import bulkload, schema, scratch

    cmd = click.Group("postgres", help="Postgres output sink commands.")
    cmd.add_command(schema)
    cmd.add_command(scratch)
    cmd.add_command(bulkload)

    return cmd


postgres_commands_spec = SimplePluginSpec(
    build=build_postgres_group,
    plugin_api_version=1,
)


__all__ = ["postgres_commands_spec"]
