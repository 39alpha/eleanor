import multiprocessing
import os
import time

from .campaign import Campaign
from .hanger.data0_tools import determine_species_set
from .hanger.db_comms import establish_database_connection, get_column_names, retrieve_records
from .sailor import sailor
from .yeoman import yeoman


def Helmsman(camp: Campaign,
             ord_id: int | None = None,
             num_cores: int | None = os.cpu_count(),
             keep_every_n_files: int = 100,
             quiet: bool = False,
             no_progress: bool = False):
    """
    Keeping with the naval terminology: The Navigator charts where to go.
    Then the helmsman guides the ship there, using sailors to do the necessary work.

    Navigator decides the region of parameter space to be explored, by issuing orders that are
    written in the `vs` (variable space) table. Each order contains a collections of discrete
    `vs` points distributed about the parameter space. The dimensions of the parameter space
    are (temperature, pressure, total C, total Fe, `etc`., depending on the constraints issued
    in the campaign json).

    The goal of the helmsman is to solve for the equilibrium behavior of each of these points
    distributed about the variable space (`vs`).

    The Helmsman does this by spawning a small number of sailors (with number of sailors
    determined by system capabilities), assigning each a `vs` point that they will thermodynamic
    'solve' in succession until all points have been solved.

    Each vs point assigned to a sailor, contains enough information to define a closed
    thermodynamic system. The sailor employs EQ3/6 to determine the equilibrium
    characteristic of the system defined by the `vs` point, thus generating an associated point
    in the equilibrium space (`es6`) table.

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param ord_id: order number
    :type ord_id: int
    """

    with camp.working_directory():
        conn = establish_database_connection(camp)

        elements, aq_sp, solids, ss, gasses = determine_species_set(path='huffer/')

        ss_kids = []
        if len(ss) > 0:
            ss_kids = camp.representative_data0.solid_solution_end_members(ss, solids)

        # retrieve issued order 'ord_id'
        order_query = ('SELECT * FROM `vs` WHERE `code` = 0 '
                       'AND `uuid` NOT IN (SELECT `uuid` FROM `es6`)')
        if ord_id is not None:
            order_query += f' AND `ord` = {ord_id}'
        rec = retrieve_records(conn, order_query)
        vs_col_names = get_column_names(conn, 'vs')

        es3_col_names = get_column_names(conn, 'es3')
        es6_col_names = get_column_names(conn, 'es6')

        conn.close()

    if len(rec) == 0:
        msg = "The Helmsman found no unexecuted points"
        if ord_id is not None:
            msg += f" for order {ord_id}"
        print(msg)
        return

    date = time.strftime("%Y-%m-%d", time.gmtime())

    start = time.time()  # for diagnostic times
    if not quiet:
        if ord_id is None:
            print(f"Processing all unfullfiled orders ({len(rec)} points)")
        else:
            print(f"Processing Order {ord_id} ({len(rec)} points)")

    scratch_path = os.path.join(camp.campaign_dir, 'scratch')

    queue_manager = multiprocessing.Manager()
    vs_queue = queue_manager.Queue()
    es3_queue = queue_manager.Queue()
    es6_queue = queue_manager.Queue()

    if num_cores is None or num_cores == 1:
        for r in rec:
            sailor(camp, scratch_path, vs_queue, es3_queue, es6_queue, date, r, elements, solids, ss, ss_kids,
                   vs_col_names, es3_col_names, es6_col_names, keep_every_n_files)
        keep_running_yeoman = multiprocessing.Value('b', False)
        yeoman(camp, keep_running_yeoman, vs_queue, es3_queue, es6_queue, len(rec), no_progress)

    elif num_cores > 1:
        keep_running_yeoman = multiprocessing.Value('b', True)
        yeoman_process = multiprocessing.Process(target=yeoman,
                                                 args=(camp, keep_running_yeoman, vs_queue, es3_queue, es6_queue,
                                                       len(rec), no_progress))
        yeoman_process.start()
        with multiprocessing.Pool(processes=num_cores) as pool:
            _ = pool.starmap(
                sailor,
                zip([camp] * len(rec), [scratch_path] * len(rec), [vs_queue] * len(rec), [es3_queue] * len(rec),
                    [es6_queue] * len(rec), [date] * len(rec), rec, [elements] * len(rec), [solids] * len(rec),
                    [ss] * len(rec), [ss_kids] * len(rec), [vs_col_names] * len(rec), [es3_col_names] * len(rec),
                    [es6_col_names] * len(rec), [keep_every_n_files] * len(rec)))

        with keep_running_yeoman.get_lock():
            keep_running_yeoman.value = False

        yeoman_process.join()

    if not quiet:
        if ord_id is None:
            print('\nOrder(s) complete.')

            print(f'        total time: {round(time.time() - start, 3)}')
            print(f'        time/point: {round((time.time() - start) / len(rec), 3)}')
        else:
            print(f'\nOrder {ord_id} complete.')

            print(f'        total time: {round(time.time() - start, 3)}')
            print(f'        time/point: {round((time.time() - start) / len(rec), 3)}')

            conn = establish_database_connection(camp)
            order_query = ('SELECT code, COUNT(*) FROM vs GROUP BY code'
                           f'WHERE ord = {ord_id}')
            rec = retrieve_records(conn, order_query)
            conn.close()
            print(rec)
            print('\n')
