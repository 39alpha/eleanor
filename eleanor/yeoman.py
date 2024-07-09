import datetime
import sqlite3
import time
from contextlib import closing
from multiprocessing import Process
from multiprocessing.sharedctypes import Synchronized
from queue import Queue

import numpy as np
import pandas as pd
from tqdm import tqdm

from .exceptions import EleanorException
from .problem import Problem
from .sailor import Result
from .typing import Any, Float, Number


def sql_spec(x: Any, nullable: bool = False) -> str:
    if x is None:
        raise EleanorException('cannot infer SQL type for None')
    if isinstance(x, (int, np.integer)):
        t = 'INTEGER'
    elif isinstance(x, (float, np.floating)):
        t = 'DOUBLE PRECISION DEFAULT 0.0'
    elif isinstance(x, str):
        t = 'TEXT'
    elif isinstance(x, bytes):
        t = 'BLOB'
    elif isinstance(x, (datetime.date, datetime.datetime)):
        t = 'TEXT'
    else:
        raise EleanorException(f'unsupported datatype {type(x)}')

    if nullable:
        return t
    else:
        return f'{t} NOT NULL'


class Yeoman(object):
    path: str
    conn: sqlite3.Connection

    def __init__(self, path: str | None):
        if path is None:
            path = 'campaign.sql'

        self.path = path
        self.conn = sqlite3.connect(path)

    def prepare_vs_table(self, problem: Problem) -> None:
        columns = ['`id` INTEGER PRIMARY KEY AUTOINCREMENT']
        for key, value in problem.to_row().items():
            columns.append(f'`{key}` {sql_spec(value)}')
        columns.extend(['`exit_code` SMALLINT NOT NULL', '`create_date` TEXT NOT NULL'])

        return self.prepare_table('vs', columns)

    def prepare_es_table(self, table: str, result: dict[str, Float]) -> None:
        columns = ['`id` INTEGER PRIMARY KEY AUTOINCREMENT', '`vs_id` INTEGER NOT NULL']
        for key, value in result.items():
            columns.append(f'`{key}` {sql_spec(value)}')

        return self.prepare_table(table, columns, foreign_keys=[('vs_id', 'vs', 'id')])

    def prepare_table(self,
                      table: str,
                      columns: list[str],
                      foreign_keys: list[tuple[str, str, str]] | None = None) -> None:

        if foreign_keys:
            columns.extend(['FOREIGN KEY (`{0}`) REFERENCES `{1}`(`{2}`)'.format(*foreign) for foreign in foreign_keys])

        query = f'CREATE TABLE IF NOT EXISTS `{table}` ({', '.join(columns)})'

        with self.conn as conn:
            conn.execute(query)

    def insert_vs_point(self, problem: Problem, exit_code: int):
        row: dict[str, Any] = problem.to_row()
        row['exit_code'] = exit_code
        row['create_date'] = datetime.datetime.now()

        return self.insert_dict('vs', row)

    def insert_es_point(self, table: str, vs_id: int, point: dict[str, Float]):
        point['vs_id'] = vs_id
        self.insert_dict(table, point)

    def insert_dict(self, table: str, data: dict[str, Any]) -> int:
        columns: list[str] = []
        keys: list[str] = []
        values: list[Any] = []
        for key, value in data.items():
            columns.append(f'`{key}`')
            keys.append(f'?')
            values.append(value)

        query = f'INSERT INTO `{table}` ({', '.join(columns)}) VALUES ({', '.join(keys)})'

        with self.conn as conn:
            cursor = conn.execute(query, values)

        if cursor.lastrowid is None:
            raise EleanorException('failed to get last row id after insert')
        return cursor.lastrowid

    def insert_result(self, result: Result):
        problem, es3, es6, exit_code = result
        id = self.insert_vs_point(problem, exit_code)
        if es3 is not None:
            self.insert_es_point('es3', id, es3)
        if es6 is not None:
            self.insert_es_point('es6', id, es6)

    def insert_results(self, results: list[Result]):
        vs_sample: dict[str, Any] = {}
        es3_sample: dict[str, Float] = {}
        es6_sample: dict[str, Float] = {}
        for problem, es3, es6, _ in results:
            vs_sample.update(problem.to_row())
            if es3 is not None:
                es3_sample.update(es3)
            if es6 is not None:
                es6_sample.update(es6)

        self.expand_table('vs', vs_sample)
        self.expand_table('es3', es3_sample)
        self.expand_table('es6', es6_sample)

        for result in results:
            self.insert_result(result)

    def expand_table(self, table: str, sample: dict[str, Any]):
        columns = set(sample.keys())
        with closing(self.conn.cursor()) as cursor:
            cursor.execute(f"PRAGMA table_info(`{table}`)")
            columns -= set(row[1] for row in cursor.fetchall())

            if columns:
                cursor.execute('BEGIN TRANSACTION')
                for column in columns:
                    query = f'ALTER TABLE `{table}` ADD COLUMN `{column}` {sql_spec(sample[column])}'
                    cursor.execute(query)

            self.conn.commit()

    def fork(self, *args) -> Process:

        def proc(*args) -> None:
            self.conn.close()
            child = type(self)(self.path)
            return child.run(*args)

        yeoman = Process(target=proc, args=args)
        yeoman.start()
        return yeoman

    def run(self, queue: Queue[Result], num_points: int, batch_size: int = 100, show_progress: bool = False) -> None:
        if num_points > batch_size and show_progress:
            progress = tqdm(total=num_points)
        else:
            progress = None

        batch: list[Result] = []
        while num_points > 0:
            while len(batch) < min(num_points, batch_size):
                batch.append(queue.get())
                queue.task_done

            self.insert_results(batch)

            if progress is not None:
                progress.update(len(batch))

            num_points -= len(batch)
