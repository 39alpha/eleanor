from sys import stderr

import ray
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .config import DatabaseConfig


class SerializableEngine(object):

    def __init__(self, config: DatabaseConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.engine = create_engine(str(self.config), echo=self.verbose)

    def __reduce__(self):
        return SerializableEngine, (self.config, self.verbose)


@ray.remote
class YeomanActor(object):
    num_samples: int
    engine: SerializableEngine

    def __init__(self, config: DatabaseConfig, num_samples: int, verbose: bool = False, **kwargs) -> None:
        self.num_samples = num_samples
        self.engine = SerializableEngine(config, verbose=verbose)

    def write(self, entity):
        if self.num_samples <= 0:
            print('WARNING: the yeoman received more vs points than expected', file=stderr)

        self.num_samples -= 1
        with Session(self.engine.engine) as session:
            session.add(entity)
            session.commit()

    def is_done(self) -> bool:
        return self.num_samples <= 0
