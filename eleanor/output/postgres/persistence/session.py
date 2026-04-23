from typing import override

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from ....connection import DatabaseConfig


class PostgresSession(Session):
    engine: Engine

    def __init__(self, config: DatabaseConfig, *args: object, verbose: bool = False, **kwargs: object):
        if config.sslmode is not None:
            self.engine = create_engine(str(config), connect_args={'sslmode': config.sslmode}, echo=verbose)
        else:
            self.engine = create_engine(str(config), echo=verbose)
        super().__init__(self.engine, *args, **kwargs)

    @override
    def __exit__(self, *args: object, **kwargs: object) -> None:
        super().__exit__(*args, **kwargs)
        self.engine.dispose()
