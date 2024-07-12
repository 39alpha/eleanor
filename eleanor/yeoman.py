from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, registry

from .exceptions import EleanorException
from .typing import Optional

engine: Engine | None = None
yeoman_registry = registry()


class Yeoman(Session):

    def __init__(self, *args, **kwargs):
        global engine

        if engine is None:
            raise EleanorException('cannot create Yeoman session without first setting up')

        super().__init__(engine, *args, **kwargs)

    @staticmethod
    def setup(db_path: Optional[str] = None, verbose: bool = False, **kwargs) -> None:
        global engine, yeoman_registry

        if engine is not None:
            raise EleanorException('cannot resetup Yeoman')

        if db_path is None:
            db_path = 'campaign.sql'

        engine = create_engine(f'sqlite:///{db_path}', echo=verbose)
        yeoman_registry.metadata.create_all(engine)

    @staticmethod
    def is_setup() -> bool:
        global engine
        return engine is not None

    @staticmethod
    def unsafe_engine() -> Optional[Engine]:
        global engine
        return engine

    @staticmethod
    def dispose(close: bool = False) -> None:
        global engine

        if engine is None:
            raise EleanorException('cannot dispose Yeoman before it is setup')

        engine.dispose(close=close)
