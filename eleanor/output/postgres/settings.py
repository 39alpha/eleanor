from dataclasses import dataclass
from typing import Self, override

from eleanor.output.settings import OutputSinkSettings
from eleanor.util import (
    guard_is_bool,
    guard_is_instance,
    guard_is_int_or_none,
    guard_is_str_or_none,
    require_bool,
    require_dict,
    require_opt_int,
    require_opt_str,
)


@dataclass(kw_only=True, frozen=True)
class PostgresDatabaseSettings:
    """Frozen connection-config dataclass for the postgres output sink.

    Hashable; safe to use as a dict key in the per-process connection
    cache.
    """

    host: str | None = "localhost"
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    sslmode: str | None = None

    def __post_init__(self) -> None:
        guard_is_str_or_none(self.host, "host")
        guard_is_int_or_none(self.port, "port")
        guard_is_str_or_none(self.database, "database")
        guard_is_str_or_none(self.username, "username")
        guard_is_str_or_none(self.password, "password")
        guard_is_str_or_none(self.sslmode, "sslmode")

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        return cls(
            host=require_opt_str(raw.get("host", "localhost"), "host"),
            port=require_opt_int(raw.get("port"), "port"),
            database=require_opt_str(raw.get("database"), "database"),
            username=require_opt_str(raw.get("username"), "username"),
            password=require_opt_str(raw.get("password"), "password"),
            sslmode=require_opt_str(raw.get("sslmode"), "sslmode"),
        )


@dataclass(kw_only=True)
class PostgresSinkSettings(OutputSinkSettings):
    database: PostgresDatabaseSettings
    bulk_load_optimization: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()

        guard_is_instance(self.database, PostgresDatabaseSettings, "database")
        guard_is_bool(self.bulk_load_optimization, "bulk_load_optimization")

    @classmethod
    @override
    def from_dict(cls, raw: dict[str, object]) -> Self:
        base_settings = OutputSinkSettings.from_dict(raw)

        database_raw: dict[str, object] = require_dict(raw.get("database", {}), "database")
        database = PostgresDatabaseSettings.from_dict(database_raw)

        optimize = require_bool(
            raw.get("bulk_load_optimization", False),
            "bulk_load_optimization",
        )

        return cls(
            verbose=base_settings.verbose,
            database=database,
            bulk_load_optimization=optimize,
        )


__all__ = [
    "PostgresDatabaseSettings",
    "PostgresSinkSettings",
]
