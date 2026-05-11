"""Built-in CLI command specs used by entry-point discovery."""

from eleanor.cli.registry import CliCommandSpec


def build_postgres_commands() -> CliCommandSpec:
    from eleanor.output.postgres.cli import bulkload, schema, scratch

    return CliCommandSpec(
        commands=(schema, scratch, bulkload),
        help="Postgres output sink commands.",
    )
