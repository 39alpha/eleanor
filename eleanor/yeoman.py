import sqlite3
import time
from multiprocessing import Process
from multiprocessing.sharedctypes import Synchronized
from queue import Queue

import pandas as pd
from tqdm import tqdm

from .problem import Problem
from .typing import Float


class Yeoman(object):
    path: str
    conn: sqlite3.Connection

    def __init__(self, path: str | None):
        if path is None:
            path = 'campaign.sql'

        self.path = path
        self.conn = sqlite3.connect(path)

    def fork(self, *args) -> Process:

        def proc(*args) -> None:
            self.conn.close()
            child = type(self)(self.path)
            return child.run(*args)

        yeoman = Process(target=proc, args=args)
        yeoman.start()
        return yeoman

    def run(self,
            keep_running: Synchronized,
            vs_queue: Queue,
            es3_queue: Queue,
            es6_queue: Queue,
            num_points: int,
            show_progress: bool = False) -> None:
        WRITE_EVERY_N = 100
        vs_n_written = 0

        es3_df_list: list[dict[str, Float]] = []
        es6_df_list: list[dict[str, Float]] = []
        vs_list: list[tuple[str, int]] = []

        if num_points <= WRITE_EVERY_N:
            write_all_at_once = True
        else:
            write_all_at_once = False

        if not write_all_at_once and show_progress:
            progress = tqdm(total=num_points)

        while keep_running.value:
            # Get the current size
            current_q_size = vs_queue.qsize()

            if current_q_size < WRITE_EVERY_N and not write_all_at_once:
                time.sleep(0.1)
            elif current_q_size == num_points and write_all_at_once:
                # Get everything written
                # Get VS Points
                while not vs_queue.empty():
                    vs_line = vs_queue.get_nowait()
                    vs_list.append(vs_line)
                    vs_queue.task_done()
                vs_n_written = len(vs_list)
                if vs_n_written != 0:
                    rows = []
                    for exit_code, problem in vs_list:
                        row = problem.to_row()
                        row['exit_code'] = exit_code
                        rows.append(row)
                    pd.DataFrame(rows).to_sql('vs', self.conn, if_exists='append', index=False)
                vs_list = []
                # Get ES3 points
                while not es3_queue.empty():
                    es3_df = es3_queue.get_nowait()
                    es3_df_list.append(es3_df)
                    es3_queue.task_done()
                # Write ES3 table
                if len(es3_df_list) != 0:
                    total_es3_df = pd.DataFrame(es3_df_list)
                    total_es3_df.to_sql('es3', self.conn, if_exists='append', index=False)
                    es3_df_list = []
                # Get ES6 points
                while not es6_queue.empty():
                    es6_df = es6_queue.get_nowait()
                    es6_df_list.append(es6_df)
                    es6_queue.task_done()
                # Write ES6 table
                if len(es6_df_list) != 0:
                    total_es6_df = pd.DataFrame(es6_df_list)
                    total_es6_df.to_sql('es6', self.conn, if_exists='append', index=False)
                    es6_df_list = []
            elif not write_all_at_once and current_q_size > WRITE_EVERY_N:
                # Get VS batch
                while len(vs_list) < WRITE_EVERY_N:
                    vs_line = vs_queue.get_nowait()
                    vs_list.append(vs_line)
                    vs_queue.task_done()

                # Write batch to VS table
                vs_n_written = len(vs_list)
                if vs_n_written != 0:
                    rows = []
                    for exit_code, problem in vs_list:
                        row = problem.to_row()
                        row['exit_code'] = exit_code
                        rows.append(row)
                    pd.DataFrame(rows).to_sql('vs', self.conn, if_exists='append', index=False)
                vs_list = []

                # Get ES6 batch
                current_es6_q_size = es6_queue.qsize()
                while len(es6_df_list) < current_es6_q_size:
                    es6_df = es6_queue.get_nowait()
                    es6_df_list.append(es6_df)
                    es6_queue.task_done()

                # Write batch to ES3 table
                if len(es3_df_list) != 0:
                    total_es3_df = pd.DataFrame(es3_df_list)
                    total_es3_df.to_sql('es3', self.conn, if_exists='append', index=False)
                    es3_df_list = []

                # Get ES3 batch
                current_es3_q_size = es3_queue.qsize()
                while len(es3_df_list) < current_es3_q_size:
                    es3_df = es3_queue.get_nowait()
                    es3_df_list.append(es3_df)
                    es3_queue.task_done()

                # Write batch to ES6 table
                if len(es6_df_list) != 0:
                    total_es6_df = pd.DataFrame(es6_df_list)
                    total_es6_df.to_sql('es6', self.conn, if_exists='append', index=False)
                    es6_df_list = []

                if show_progress:
                    progress.update(vs_n_written)

        # Clean up the last batch
        # Get remaining vs lines
        while not vs_queue.empty():
            vs_line = vs_queue.get_nowait()
            vs_list.append(vs_line)
            vs_queue.task_done()
        vs_n_written = len(vs_list)
        if vs_n_written != 0:
            rows = []
            for exit_code, problem in vs_list:
                row = problem.to_row()
                row['exit_code'] = exit_code
                rows.append(row)
            pd.DataFrame(rows).to_sql('vs', self.conn, if_exists='append', index=False)

        while not es3_queue.empty():
            es3_df = es3_queue.get_nowait()
            es3_df_list.append(es3_df)
            es3_queue.task_done()
        # Write batch to ES table
        if len(es3_df_list) != 0:
            total_es3_df = pd.DataFrame(es3_df_list)
            total_es3_df.to_sql('es3', self.conn, if_exists='append', index=False)

        while not es6_queue.empty():
            es6_df = es6_queue.get_nowait()
            es6_df_list.append(es6_df)
            es6_queue.task_done()
        # Write batch to ES table
        if len(es6_df_list) != 0:
            total_es6_df = pd.DataFrame(es6_df_list)
            total_es6_df.to_sql('es6', self.conn, if_exists='append', index=False)

        if not write_all_at_once and show_progress:
            progress.update(vs_n_written)
