from eleanor.output.postgres.settings import PostgresDatabaseSettings


def export_duckdb(settings: PostgresDatabaseSettings) -> None: ...


__all__ = ["export_duckdb"]
