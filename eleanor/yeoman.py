import datetime
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from multiprocessing import Process
from multiprocessing.sharedctypes import Synchronized
from queue import Queue

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from tqdm import tqdm

import eleanor.models as model

from .exceptions import EleanorException
from .models import VSPoint, mapper_registry
from .problem import Problem
from .typing import Any, Float, Number


class Yeoman(object):
    path: str
    engine: Engine

    def __init__(self, path: str | None = None, verbose: bool = False, **kwargs):
        if path is None:
            path = 'campaign.sql'

        self.path = path
        self.engine = create_engine(f'sqlite:///{path}', echo=verbose)

        mapper_registry.metadata.create_all(self.engine)

    def fork(self, *args, **kwargs) -> Process:

        def proc(*args, **kwargs) -> None:
            child = type(self)(self.path)
            return child.run(*args, **kwargs)

        yeoman = Process(target=proc, args=args, kwargs=kwargs)
        yeoman.start()
        return yeoman

    def run(self,
            queue: Queue[VSPoint],
            num_points: int,
            batch_size: int = 100,
            verbose: bool = False,
            show_progress: bool = False,
            **kwargs) -> None:
        if num_points > batch_size and show_progress:
            progress = tqdm(total=num_points)
        else:
            progress = None

        batch: list[VSPoint] = []
        while num_points > 0:
            while len(batch) < min(num_points, batch_size):
                batch.append(queue.get())
                queue.task_done

            with Session(self.engine) as session:
                session.add_all(batch)
                session.commit()

            if progress is not None:
                progress.update(len(batch))

            num_points -= len(batch)
