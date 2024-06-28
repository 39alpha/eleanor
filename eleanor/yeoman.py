import time
from multiprocessing.sharedctypes import Synchronized
from queue import Queue

import pandas as pd
from tqdm import tqdm

from .hanger.db_comms import establish_database_connection, execute_vs_exit_updates


def yeoman(db_path: str,
           keep_running: Synchronized,
           write_vs_q: Queue,
           write_es3_q: Queue,
           write_es6_q: Queue,
           num_points: int,
           no_progress: bool = False) -> None:
    conn = establish_database_connection(db_path)
    WRITE_EVERY_N = 100
    vs_n_written = 0

    es3_df_list = []
    es6_df_list = []
    vs_list = []

    if num_points <= WRITE_EVERY_N:
        write_all_at_once = True
    else:
        write_all_at_once = False

    if not write_all_at_once and not no_progress:
        progress = tqdm(total=num_points)

    while keep_running.value:
        # Get the current size
        current_q_size = write_vs_q.qsize()

        if current_q_size < WRITE_EVERY_N and not write_all_at_once:
            time.sleep(0.1)

        elif current_q_size == num_points and write_all_at_once:
            # Get everything written
            # Get VS Points
            while not write_vs_q.empty():
                vs_line = write_vs_q.get_nowait()
                vs_list.append(vs_line)
                write_vs_q.task_done()
            # Get ES3 points
            while not write_es3_q.empty():
                es3_df = write_es3_q.get_nowait()
                es3_df_list.append(es3_df)
                write_es3_q.task_done()
            # Write ES3 table
            if len(es3_df_list) != 0:
                total_es3_df = pd.concat(es3_df_list, ignore_index=True)
                total_es3_df.to_sql('es3', conn, if_exists='append', index=False)
                es3_df_list = []
            # Get ES6 points
            while not write_es6_q.empty():
                es6_df = write_es6_q.get_nowait()
                es6_df_list.append(es6_df)
                write_es6_q.task_done()
            # Write ES6 table
            if len(es6_df_list) != 0:
                total_es6_df = pd.concat(es6_df_list, ignore_index=True)
                total_es6_df.to_sql('es6', conn, if_exists='append', index=False)
                es6_df_list = []
                # Write VS lines
                execute_vs_exit_updates(conn, vs_list)
                vs_list = []

        elif not write_all_at_once and current_q_size > WRITE_EVERY_N:
            # Get VS batch
            while len(vs_list) < WRITE_EVERY_N:
                vs_line = write_vs_q.get_nowait()
                vs_list.append(vs_line)
                write_vs_q.task_done()
            # Write batch to VS table
            execute_vs_exit_updates(conn, vs_list)
            vs_n_written = len(vs_list)

            vs_list = []
            # Get ES6 batch
            current_es6_q_size = write_es6_q.qsize()
            while len(es6_df_list) < current_es6_q_size:
                es6_df = write_es6_q.get_nowait()
                es6_df_list.append(es6_df)
                write_es6_q.task_done()

            # Write batch to ES3 table
            if len(es3_df_list) != 0:
                total_es3_df = pd.concat(es3_df_list, ignore_index=True)
                total_es3_df.to_sql('es3', conn, if_exists='append', index=False)
                es3_df_list = []

            # Get ES3 batch
            current_es3_q_size = write_es3_q.qsize()
            while len(es3_df_list) < current_es3_q_size:
                es3_df = write_es3_q.get_nowait()
                es3_df_list.append(es3_df)
                write_es3_q.task_done()

            # Write batch to ES6 table
            if len(es6_df_list) != 0:
                total_es6_df = pd.concat(es6_df_list, ignore_index=True)
                total_es6_df.to_sql('es6', conn, if_exists='append', index=False)
                es6_df_list = []

            if not no_progress:
                progress.update(vs_n_written)

    # Clean up the last batch
    # Get remaining vs lines
    while not write_vs_q.empty():
        vs_line = write_vs_q.get_nowait()
        vs_list.append(vs_line)
        write_vs_q.task_done()
    # Write last batch to VS table
    execute_vs_exit_updates(conn, vs_list)
    vs_n_written = len(vs_list)

    while not write_es3_q.empty():
        es3_df = write_es3_q.get_nowait()
        es3_df_list.append(es3_df)
        write_es3_q.task_done()
    # Write batch to ES table
    if len(es3_df_list) != 0:
        total_es3_df = pd.concat(es3_df_list, ignore_index=True)
        total_es3_df.to_sql('es3', conn, if_exists='append', index=False)

    while not write_es6_q.empty():
        es6_df = write_es6_q.get_nowait()
        es6_df_list.append(es6_df)
        write_es6_q.task_done()
    # Write batch to ES table
    if len(es6_df_list) != 0:
        total_es6_df = pd.concat(es6_df_list, ignore_index=True)
        total_es6_df.to_sql('es6', conn, if_exists='append', index=False)

    if not write_all_at_once and not no_progress:
        progress.update(vs_n_written)

    return None
