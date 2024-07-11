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
from tqdm import tqdm

import eleanor.models as model

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

    def initialize(self, problem: Problem) -> None:
        columns = ['`id` INTEGER PRIMARY KEY AUTOINCREMENT']
        for key, value in problem.to_row().items():
            columns.append(f'`{key}` {sql_spec(value)}')
        columns.extend(['`exit_code` SMALLINT NOT NULL', '`create_date` TEXT NOT NULL'])
        self.prepare_table('vs', columns)

        self.conn.executescript("""
            BEGIN;
            CREATE TABLE IF NOT EXISTS `summary` (
                `id`                  INTEGER PRIMARY KEY AUTOINCREMENT,
                `vs_id`               INTEGER NOT NULL,
                `stage`               VARCHAR(8) NOT NULL,
                `temperature`         DOUBLE PRECISION NOT NULL,
                `pressure`            DOUBLE PRECISION NOT NULL,
                `pH`                  DOUBLE PRECISION NOT NULL,
                `log_fO2`             DOUBLE PRECISION NOT NULL,
                `log_activity_water`  DOUBLE PRECISION NOT NULL,
                `ionic_strength`      DOUBLE PRECISION NOT NULL,
                `tds_mass`            DOUBLE PRECISION NOT NULL,
                `solution_mass`       DOUBLE PRECISION NOT NULL,
                `charge_imbalance`    DOUBLE PRECISION NOT NULL,
                `extended_alkalinity` DOUBLE PRECISION,
                `initial_affinity`    DOUBLE PRECISION,
                `log_xi`              DOUBLE PRECISION,
                FOREIGN KEY (`vs_id`) REFERENCES `vs`(`id`)
            );

            CREATE TABLE IF NOT EXISTS `elements` (
                `id`           INTEGER PRIMARY KEY AUTOINCREMENT,
                `vs_id`        INTEGER NOT NULL,
                `name`         VARCHAR(2) NOT NULL,
                `log_molality` DOUBLE PRECISION NOT NULL,
                FOREIGN KEY (`vs_id`) REFERENCES `vs`(`id`)
            );

            CREATE TABLE IF NOT EXISTS `aqueous_species` (
                `id`           INTEGER PRIMARY KEY AUTOINCREMENT,
                `vs_id`        INTEGER NOT NULL,
                `name`         VARCHAR(2) NOT NULL,
                `log_molality` DOUBLE PRECISION NOT NULL,
                `log_activity` DOUBLE PRECISION NOT NULL,
                FOREIGN KEY (`vs_id`) REFERENCES `vs`(`id`)
            );

            -- DGM: We might want to split this table into two, one for pure phases and one
            --      for solid solutions
            CREATE TABLE IF NOT EXISTS `solid_phases` (
                `id`           INTEGER PRIMARY KEY AUTOINCREMENT,
                `vs_id`        INTEGER NOT NULL,
                `type`         VARCHAR(16) NOT NULL,
                `name`         VARCHAR(32) NOT NULL,
                `end_member`   VARCHAR(32),
                `log_qk`       DOUBLE PRECISION NOT NULL,
                `log_moles`    DOUBLE PRECISION,
                FOREIGN KEY (`vs_id`) REFERENCES `vs`(`id`)
            );

            CREATE TABLE IF NOT EXISTS `gases` (
                `id`           INTEGER PRIMARY KEY AUTOINCREMENT,
                `vs_id`        INTEGER NOT NULL,
                `name`         VARCHAR(2) NOT NULL,
                `log_fugacity` DOUBLE PRECISION NOT NULL,
                FOREIGN KEY (`vs_id`) REFERENCES `vs`(`id`)
            );
            COMMIT;
        """)

    def prepare_table(self,
                      table: str,
                      columns: list[str],
                      foreign_keys: list[tuple[str, str, str]] | None = None) -> None:

        if foreign_keys:
            columns.extend(['FOREIGN KEY (`{0}`) REFERENCES `{1}`(`{2}`)'.format(*foreign) for foreign in foreign_keys])

        query = f'CREATE TABLE IF NOT EXISTS `{table}` ({', '.join(columns)})'

        with self.conn as conn:
            conn.execute(query)

    def insert_vs_point(self, problem: Problem, exit_code: int) -> int:
        start = datetime.datetime.now()
        row: dict[str, Any] = problem.to_row()
        row['exit_code'] = exit_code
        row['create_date'] = datetime.datetime.now()
        id = self.insert_dict('vs', row)
        stop = datetime.datetime.now()
        # print('insert_vs_point: ', stop - start)
        return id

    def insert_summary(self, vs_id: int, point: model.Result, conn: sqlite3.Connection | None = None):
        if conn is None:
            conn = self.conn

        point.vs_id = vs_id
        query = """
            INSERT INTO `summary` (
                `vs_id`,
                `stage`,
                `temperature`,
                `pressure`,
                `pH`,
                `log_fO2`,
                `log_activity_water`,
                `ionic_strength`,
                `tds_mass`,
                `solution_mass`,
                `charge_imbalance`,
                `extended_alkalinity`,
                `initial_affinity`,
                `log_xi`
            ) VALUES (
                :vs_id,
                :stage,
                :temperature,
                :pressure,
                :pH,
                :log_fO2,
                :log_activity_water,
                :ionic_strength,
                :tds_mass,
                :solution_mass,
                :charge_imbalance,
                :extended_alkalinity,
                :initial_affinity,
                :log_xi
            )
        """
        conn.execute(query, asdict(point))

    def insert_elements(self, vs_id: int, elements: list[model.Element], conn: sqlite3.Connection | None = None):
        if conn is None:
            conn = self.conn

        for element in elements:
            element.vs_id = vs_id

        query = 'INSERT INTO `elements` (`vs_id`, `name`, `log_molality`) VALUES (:vs_id, :name, :log_molality)'
        conn.executemany(query, map(asdict, elements))

    def insert_aqueous_species(self,
                               vs_id: int,
                               aqueous_species: list[model.AqueousSpecies],
                               conn: sqlite3.Connection | None = None):
        if conn is None:
            conn = self.conn

        for species in aqueous_species:
            species.vs_id = vs_id

        query = """
            INSERT INTO `aqueous_species` (
                `vs_id`, `name`, `log_molality`, `log_activity`
            ) VALUES (
                :vs_id, :name, :log_molality, :log_activity
            )
        """
        conn.executemany(query, map(asdict, aqueous_species))

    def insert_solid_phases(self,
                            vs_id: int,
                            solid_phases: list[model.SolidPhase],
                            conn: sqlite3.Connection | None = None):
        if conn is None:
            conn = self.conn

        for phase in solid_phases:
            phase.vs_id = vs_id

        query = """
            INSERT INTO `solid_phases` (
                `vs_id`, `type`, `name`, `end_member`, `log_qk`, `log_moles`
            ) VALUES (
                :vs_id, :type, :name, :end_member, :log_qk, :log_moles
            )
        """
        conn.executemany(query, map(asdict, solid_phases))

    def insert_gases(self, vs_id: int, gases: list[model.Gas], conn: sqlite3.Connection | None = None):
        if conn is None:
            conn = self.conn

        for gas in gases:
            gas.vs_id = vs_id

        query = 'INSERT INTO `gases` (`vs_id`, `name`, `log_fugacity`) VALUES (:vs_id, :name, :log_fugacity)'
        conn.executemany(query, map(asdict, gases))

    def insert_es_point(self, vs_id: int, point: model.Result):
        start = datetime.datetime.now()
        with self.conn as conn:
            self.insert_summary(vs_id, point, conn=conn)
            self.insert_elements(vs_id, point.elements, conn=conn)
            self.insert_aqueous_species(vs_id, point.aqueous_species, conn=conn)
            self.insert_solid_phases(vs_id, point.solid_phases, conn=conn)
            self.insert_gases(vs_id, point.gases, conn=conn)
        stop = datetime.datetime.now()
        # print("insert_es_point: ", stop - start)

    def insert_dict(self, table: str, data: dict[str, Any], conn: sqlite3.Connection | None = None) -> int:
        if conn is None:
            conn = self.conn

        columns: list[str] = []
        keys: list[str] = []
        values: list[Any] = []
        for key, value in data.items():
            columns.append(f'`{key}`')
            keys.append(f'?')
            values.append(value)

        query = f'INSERT INTO `{table}` ({', '.join(columns)}) VALUES ({', '.join(keys)})'

        cursor = conn.execute(query, values)
        if cursor.lastrowid is None:
            raise EleanorException('failed to get last row id after insert')
        return cursor.lastrowid

    def insert_result(self, result: Result):
        start = datetime.datetime.now()
        problem, es3, es6, exit_code = result
        id = self.insert_vs_point(problem, exit_code)
        if es3 is not None:
            self.insert_es_point(id, es3)
        if es6 is not None:
            self.insert_es_point(id, es6)
        stop = datetime.datetime.now()
        # print("insert_result: ", stop - start)

    def insert_results(self, results: list[Result]):
        start = datetime.datetime.now()
        vs_sample: dict[str, Any] = {}
        for problem, *_ in results:
            vs_sample.update(problem.to_row())

        self.expand_table('vs', vs_sample)

        for result in results:
            self.insert_result(result)
        stop = datetime.datetime.now()
        print("insert_results: ", stop - start)

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
