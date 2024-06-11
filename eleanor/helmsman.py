import multiprocessing
import numpy as np
import os
import pandas as pd
import re
import shutil
import sys
import time

from enum import IntEnum
from os.path import join, realpath
from tqdm import tqdm

from .exceptions import EleanorException, EleanorFileException, RunCode
from .hanger.db_comms import execute_vs_exit_updates
from .hanger.db_comms import establish_database_connection, retrieve_records, get_column_names
from .hanger.eq36 import eq3, eq6
from .hanger.data0_tools import determine_species_set
from .hanger.tool_room import mk_check_directory, mine_pickup_lines, grab_float
from .hanger.tool_room import grab_lines, grab_str, determine_ss_kids, WorkingDirectory


def Helmsman(camp, ord_id=None, num_cores=os.cpu_count(), keep_every_n_files=100, quiet=False, no_progress=False):
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
            ss_kids = determine_ss_kids(camp, ss, solids)

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

    if num_cores == 1:
        for r in rec:
            sailor(camp, scratch_path, vs_queue, es3_queue, es6_queue, date, r, elements, solids, ss, ss_kids,
                   vs_col_names, es3_col_names, es6_col_names, keep_every_n_files)
        keep_running_yoeman = multiprocessing.Value('b', False)
        yoeman(camp, keep_running_yoeman, vs_queue, es3_queue, es6_queue, len(rec), no_progress)

    elif num_cores > 1:
        keep_running_yoeman = multiprocessing.Value('b', True)
        yoeman_process = multiprocessing.Process(target=yoeman,
                                                 args=(camp, keep_running_yoeman, vs_queue, es3_queue, es6_queue,
                                                       len(rec), no_progress))
        yoeman_process.start()
        with multiprocessing.Pool(processes=num_cores) as pool:
            _ = pool.starmap(
                sailor,
                zip([camp] * len(rec), [scratch_path] * len(rec), [vs_queue] * len(rec), [es3_queue] * len(rec),
                    [es6_queue] * len(rec), [date] * len(rec), rec, [elements] * len(rec), [solids] * len(rec),
                    [ss] * len(rec), [ss_kids] * len(rec), [vs_col_names] * len(rec), [es3_col_names] * len(rec),
                    [es6_col_names] * len(rec), [keep_every_n_files] * len(rec)))

        with keep_running_yoeman.get_lock():
            keep_running_yoeman.value = False

        yoeman_process.join()

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


class SailorPaths(object):
    """
    A simple class for managing a sailor's various file paths

    :param scratch_dir: the scratch directory in which to create order directories
    :type scratch_dir: str
    :param order: the order number the sailor will process
    :type order: int
    :param file: the file number the sailor will process
    :type file: int
    :param keep_every_n_files: keep every n (multiple) files. This is used internally to determine
                               whether or not the sailor's files will be kept after the sailor
                               completes its work
    :type keep_every_n_files: bool
    """

    def __init__(self, scratch_dir, order, file, keep_every_n_files):
        self.scratch_dir = scratch_dir
        self.order = order
        self.file = file
        self.keep_every_n_files = keep_every_n_files

    @property
    def name(self):
        """
        The sailor's file number as a string

        :rtype: str
        """
        return '{}'.format(self.file)

    @property
    def directory(self):
        """
        The sailor's working directory as a string

        :rtype: str
        """
        order = 'order_{}'.format(self.order)
        return os.path.join(self.scratch_dir, order, self.name)

    @property
    def keep(self):
        """
        Whether or not the sailor's files should be kept after it finishes its work.

        :rtype: bool
        """
        return self.keep_every_n_files > 0 and self.file % self.keep_every_n_files == 0

    @property
    def threei(self):
        """
        The name of the sailor's 3i file.

        :rtype: str
        """
        return self.name + '.3i'

    @property
    def threeo(self):
        """
        The name of the sailor's 3o file.

        :rtype: str
        """
        return self.name + '.3o'

    @property
    def threep(self):
        """
        The name of the sailor's 3p file.

        :rtype: str
        """
        return self.name + '.3p'

    @property
    def sixi(self):
        """
        The name of the sailor's 6i file.

        :rtype: str
        """
        return self.name + '.6i'

    @property
    def sixo(self):
        """
        The name of the sailor's 6o file.

        :rtype: str
        """
        return self.name + '.6o'

    def create_directory(self):
        mk_check_directory(self.directory)


def sailor(camp,
           scratch_path,
           vs_queue,
           es3_queue,
           es6_queue,
           date,
           dat,
           elements,
           solids,
           ss,
           ss_kids,
           vs_col_names,
           es3_col_names,
           es6_col_names,
           keep_every_n_files=10000):
    """
    Each sailor manages the execution of all geochemically model steps associated
    with a single vs point in the Variable Space (`vs`).
    These steps included:

    (1) build 3i
    (2) run 3i
    (3) build 6i
    (4) run 6i
    (5) mine 6o

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param scratch_path: local directory path for the current order
    :type scratch_path: str

    :param vs_queue: a waiting list of lines that need to be written to vs table
    :type vs_queue: class 'multiprocessing.managers.AutoProxy[Queue]

    :param es3_queue: a queue of pandas data frames that need to be written to es3 table
    :type es3_queue: class 'multiprocessing.managers.AutoProxy[Queue]

    :param es6_queue: a queue of pandas data frames that need to be written to es6 table
    :type es6_queue: class 'multiprocessing.managers.AutoProxy[Queue]

    :param date: birthdate of order
    :type data: str

    :param dat: all vs specific data need by the sailor to complete mission.
    :type dat: list

    :param elements: list of loaded element, excepting O and H
    :type elements: list of strings

    :param ss: list of loaded solid solutions
    :type ss: list of strings

    :param ss_kids: the endmemebr phase names associated with loaded solid solutions
    :type ss_kids: list of strings

    :param vs_col_names: column headers in vs table. If a value in the eq3/6 run files is not in
                         the column names, then it is not captured.
    :type vs_col_names: list of strings

    :param es_col_names: column headers in es table. If a value in the eq3/6 run files is not in
                         the column names, then it is not captured.

    :type es_col_names: list of strings

    :param keep_every_n_files: keep every n (multiple) files. All run files get deleted after being
                               processed into the VS/ES sql database, as they are collectively very
                               large. A subset of files can be kept here for later manual
                               inspection. This argument allows you to keep the raw data eq3/6 for a
                               subset of runs so that you can evaluate the output directly. the sql
                               codes grab a lot of the eq3.6 run information, but not all of it. If
                               this argument is less than 1, then no files are kept.
    :type keep_every_n_files: int
    """

    master_dict = {}
    for i, j in zip(vs_col_names, dat):
        master_dict[i] = j

    state_dict = {}
    for i in camp.vs_state:
        state_dict[i] = master_dict[i]

    if isinstance(camp.vs_state['fO2'], str):
        state_dict['fO2'] = camp.vs_state['fO2']

    basis_dict = {}
    for i in camp.vs_basis:
        basis_dict[i] = master_dict[i]

    rnt_dict = {}
    if camp.target_rnt != {}:
        rnt_keys = list(camp.target_rnt.keys())
        for i in range(len(rnt_keys)):
            name = rnt_keys[i]
            rnt_type = camp.target_rnt[name][0]
            morr = master_dict['{}_morr'.format(name)]
            rkb1 = master_dict['{}_rkb1'.format(name)]
            rnt_dict[name] = [rnt_type, morr, rkb1]

    paths = SailorPaths(scratch_path, master_dict['ord'], master_dict['file'], keep_every_n_files)

    paths.create_directory()
    with WorkingDirectory(paths.directory):
        camp.local_3i.write(paths.threei,
                            state_dict,
                            basis_dict,
                            master_dict['cb'],
                            camp.suppress_sp,
                            output_details='n')

        data1_file = realpath(join(camp.data1_dir, master_dict['data1']))

        try:
            eq3(data1_file, paths.threei)

            pickup = mine_pickup_lines('.', paths.threep, 's')

            camp.local_6i.write(paths.sixi, rnt_dict, pickup, state_dict['T_cel'])
            eq6(data1_file, paths.sixi)

            threeodf = mine_3o(camp, date, elements, solids, ss, ss_kids, paths.threeo, master_dict, es3_col_names)
            sixodf = mine_6o(camp, date, elements, solids, ss, ss_kids, paths.sixo, master_dict, es6_col_names)

            es3_queue.put_nowait(threeodf)
            es6_queue.put_nowait(sixodf)

            return reset_sailor(paths, vs_queue, master_dict['uuid'], RunCode.SUCCESS)
        except EleanorException as e:
            return reset_sailor(paths, vs_queue, master_dict['uuid'], e.code)


def mine_3o(camp, date, elements, solids, ss, ss_kids, file, master_dict, col_names):
    """
    open and mine the eqe output file ('file'.3o) for all of the run information
    with associated columns in the es3 table.

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param date: birthdate of order
    :type data: str

    :param elements: list of loaded element, excepting O and H
    :type elements: list of strings

    :param ss: list of loaded solid solutions
    :type ss: list of strings

    :param file: 'file'.6o file name
    :type file: str

    :param build_dict: all vs specific data needed by the sailor to complete mission.
    :type build_dict: dictionary

    :param col_names: ES table columns
    :type col_names: list of strings
    """

    build_dict = {k: [] for k in col_names}
    build_dict['extended_alk'] = [np.nan]  # undefined for systems over 50 in EQ36 output

    try:
        lines = grab_lines(file)

        run_code = RunCode.NOT_RUN
        if 'Normal exit' not in lines[-1]:
            raise EleanorException('eq3 terminated early', code=RunCode.EQ3_EARLY_TERMINATION)
        else:
            run_code = RunCode.SUCCESS

        for i in range(len(lines)):
            if re.findall('^\n', lines[i]):
                pass

            elif ' Temperature=' in lines[i]:
                build_dict['T_cel'] = [grab_float(lines[i], -2)]

            elif ' Pressure=' in lines[i]:
                build_dict['P_bar'] = [grab_float(lines[i], 1)]

            elif ' --- Elemental Composition' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if grab_str(lines[i + x], 0) in elements:
                        # log molality
                        this_dat = [np.round(np.log10(grab_float(lines[i + x], -1)), 6)]
                        build_dict['m_{}'.format(grab_str(lines[i + x], 0))] = this_dat
                        x += 1
                    else:
                        x += 1

            elif ' NBS pH scale         ' in lines[i]:
                build_dict['pH'] = [grab_float(lines[i], -4)]

            elif '                Log oxygen fugacity=' in lines[i]:
                build_dict['fO2'] = [grab_float(lines[i], -1)]

            elif '              Log activity of water=' in lines[i]:
                build_dict['a_H2O'] = [grab_float(lines[i], -1)]

            elif '                 Ionic strength (I)=' in lines[i]:
                build_dict['ionic'] = [grab_float(lines[i], -2)]

            elif '                 Solutes (TDS) mass=' in lines[i]:
                build_dict['tds'] = [grab_float(lines[i], -2)]

            elif '              Aqueous solution mass=' in lines[i]:
                build_dict['soln_mass'] = [grab_float(lines[i], -2)]

            elif '           --- Extended Total Alkalinity ---' in lines[i]:
                build_dict['extended_alk'] = [grab_float(lines[i + 2], 0)]

            elif '         Charge imbalance=' in lines[i]:
                # ### eq/kg.H2O
                build_dict['charge_imbalance_eq'] = [grab_float(lines[i], -1)]

            elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if grab_str(lines[i + x], 0) != 'O2(g)':
                        # ### ****** shows up with species are less than -99999.0
                        # ### which signifies that it was suppressed.

                        # ### -3 is log molality
                        if '****' in grab_str(lines[i + x], -3):
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -3)]

                        # ### -1 position is log activity,
                        if '****' in grab_str(lines[i + x], -1):
                            build_dict[f'a_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'a_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -1)]
                        x += 1
                    else:
                        x += 1

            elif '--- Saturation States of Pure Solids ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # ## '******'' fills in the value region for numbers
                        # ## lower than -999.9999. Replace with boundary condition
                        # ## log Q/K
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                        x += 1
                    elif 'None' not in lines[i + x]:
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(lines[i + x][31:44])]
                        x += 1
                    else:
                        x += 1

            elif camp.SS and ' --- Saturation States of Solid Solutions ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    # ## log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # ## '******' fills in the value region for numbers
                        # ## lower than -999.9999. Replace with boundary condition
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                        x += 1
                    elif 'None' not in lines[i + x]:
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(lines[i + x][44:55])]
                        x += 1
                    else:
                        x += 1

            elif '    --- Fugacities ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if 'None' not in lines[i + x]:  # log f
                        if re.findall(r'\*{4}', lines[i + x]):
                            # ## '******'' fills in the value region for numbers
                            # ## lower than -999.9999. Replace with boundary condition
                            build_dict[f'f_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                            x += 1
                        else:
                            build_dict[f'f_{grab_str(lines[i + x], 0)}'] = [float(lines[i + x][28:41])]
                            x += 1
                    else:
                        x += 1
                break

        build_dict['uuid'] = [master_dict['uuid']]
        build_dict['ord'] = [master_dict['ord']]
        build_dict['file'] = [master_dict['file']]
        build_dict['run'] = [date]

        # reorganize columns to match es table
        columns_to_remove = set()
        for key, value in build_dict.items():
            if len(value) == 0:
                columns_to_remove.add(key)
        kept_columns = []
        for column in col_names:
            if column not in columns_to_remove:
                kept_columns.append(column)
        for key in columns_to_remove:
            del build_dict[key]

        build_df = pd.DataFrame.from_dict(build_dict)
        return build_df[kept_columns]
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_3O_FILE)


def mine_6o(camp, date, elements, solids, ss, ss_kids, file, master_dict, col_names):
    """
    open and mine the eq6 output file ('file'.6o) for all of the run information
    with associated columns in the ES table.

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param date: birthdate of order
    :type data: str

    :param elements: list of loaded element, excepting O and H
    :type elements: list of strings

    :param ss: list of loaded solid solutions
    :type ss: list of strings

    :param file: 'file'.6o file name
    :type file: str

    :param build_dict: all vs specific data needed by the sailor to complete mission.
    :type build_dict: dictionary

    :param col_names: ES table columns
    :type col_names: list of strings
    """
    build_dict = {k: [] for k in col_names}
    build_dict['extended_alk'] = [np.nan]  # undefined for systems over 50 in EQ36 output

    for _ in solids + ss + ss_kids:
        build_dict[f'm_{_}'] = [0.0]  # mols precip must be preset, as its field is not inculsive

    try:
        lines = grab_lines(file)  # 6o file

        run_code = RunCode.NOT_RUN
        search_for_xi = False
        for i in range(len(lines) - 1, 0, -1):
            # ## search from bottom of file
            if '---  The reaction path has terminated early ---' in lines[i]:
                raise EleanorException('eq6 reaction path terminated early', code=RunCode.EQ6_EARLY_TERMINATION)
            elif '---  The reaction path has terminated normally ---' in lines[i]:
                run_code = RunCode.SUCCESS
                # Healthy file. Search for index of the last xi step
                search_for_xi = True
            elif search_for_xi and '                Log Xi=' in lines[i]:
                # The first appearance of this, when searching from the bottom
                # is the final EQ step of interest for populating ES.
                last_xi_step_begins = i  # grab index for later.
                break

        if run_code == RunCode.NOT_RUN:
            # run code has not be altered, therefore unknown error
            # build_df = pd.DataFrame.from_dict(build_dict)
            raise EleanorException('no reaction path termination status found', code=RunCode.FILE_ERROR_6O)

        # populate ES table
        if camp.target_rnt != {}:
            for i in range(len(lines)):
                if '   Affinity of the overall irreversible reaction=' in lines[i]:
                    # the first instance of this line is xi = 0.0
                    # (initial disequilibria with target mineral)
                    build_dict["initial_aff"] = [grab_float(lines[i], -2)]
                    break
        else:
            build_dict["initial_aff"] = [0.0]

        # search from beginning of last xi step (set in last_xi_step_begins)
        # grab xi_max. since initial index contains log Xi.
        build_dict['xi_max'] = [grab_float(lines[last_xi_step_begins], -1)]

        for i in range(last_xi_step_begins, len(lines)):
            if re.findall('^\n', lines[i]):
                pass

            elif ' Temperature=' in lines[i]:
                build_dict['T_cel'] = [grab_float(lines[i], -2)]

            elif ' Pressure=' in lines[i]:
                build_dict['P_bar'] = [grab_float(lines[i], -2)]

            elif ' --- Elemental Composition' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if grab_str(lines[i + x], 0) in elements:
                        # log molality
                        this_dat = [np.round(np.log10(grab_float(lines[i + x], -1)), 6)]
                        build_dict['m_{}'.format(grab_str(lines[i + x], 0))] = this_dat
                        x += 1
                    else:
                        x += 1

            elif ' NBS pH scale         ' in lines[i]:
                build_dict['pH'] = [grab_float(lines[i], -4)]

            elif '                Log oxygen fugacity=' in lines[i]:
                build_dict['fO2'] = [grab_float(lines[i], -1)]

            elif '              Log activity of water=' in lines[i]:
                build_dict['a_H2O'] = [grab_float(lines[i], -1)]

            elif '                 Ionic strength (I)=' in lines[i]:
                build_dict['ionic'] = [grab_float(lines[i], -2)]

            elif '                 Solutes (TDS) mass=' in lines[i]:
                tds = grab_float(lines[i], -2)
                if len(camp.salinity) > 0:
                    # ### limited salinity sought
                    if tds > max(camp.salinity) or tds < min(camp.salinity):
                        raise EleanorException('total disolved solute is outside salinity window',
                                               code=RunCode.OUTSIDE_SALINITY_WINDOW)
                    else:
                        build_dict['tds'] = [tds]
                else:
                    build_dict['tds'] = [tds]

            elif '              Aqueous solution mass=' in lines[i]:
                build_dict['soln_mass'] = [grab_float(lines[i], -2)]

            elif '           --- Extended Total Alkalinity ---' in lines[i]:
                build_dict['extended_alk'] = [grab_float(lines[i + 2], 0)]

            elif '        --- Aqueous Solution Charge Balance ---' in lines[i]:
                # ### Actual charge imbalance eq/kg.H2O
                build_dict['charge_imbalance_eq'] = [grab_float(lines[i + 2], -2)]

            # elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
            #     x = 4
            #     while not re.findall('^\n', lines[i + x]):
            #         if grab_str(lines[i + x], 0) != 'O2(g)':
            #             # ### -1 position is log activity, -3 is log molality
            #             build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [grab_float(
            #                 lines[i + x], -3)]
            #             build_dict[f'a_{grab_str(lines[i + x], 0)}'] = [grab_float(
            #                 lines[i + x], -1)]
            #             x += 1
            #         else:
            #             x += 1

            elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if grab_str(lines[i + x], 0) != 'O2(g)':
                        # ### ****** shows up with species are less than -99999.0
                        # ### which signifies that it was suppressed.

                        # ### -3 is log molality
                        if '****' in grab_str(lines[i + x], -3):
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -3)]

                        # ### -1 position is log activity,
                        if '****' in grab_str(lines[i + x], -1):
                            build_dict[f'a_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'a_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -1)]
                        x += 1
                    else:
                        x += 1

            elif '--- Summary of Solid Phases (ES) ---' in lines[i]:
                x = 4
                parent = None
                kid = None
                if 'None' not in lines[i + x]:

                    while True:
                        if re.findall('^\n', lines[i + x]) and re.findall('^\n', lines[i + x + 1]):
                            # ### two blank lines signifies end of block
                            break

                        elif re.findall('^\n', lines[i + x]):
                            # ### single blank lines separate solids from solid slutions reporting
                            parent = None
                            x += 1

                        elif re.findall('^ [^ ]', lines[i + x]):
                            # ### pure phases and solid solutions parents
                            parent = lines[i + x][:25].strip()
                            build_dict[f'm_{lines[i + x][:25].strip()}'] = [grab_float(lines[i + x], -3)]
                            x += 1

                        elif re.findall('^   [^ ]', lines[i + x]):
                            # ### solid solution endmember. Grab with parent association
                            kid = lines[i + x][:25].strip()
                            build_dict[f'm_{kid}_{parent}'] = [grab_float(lines[i + x], -3)]
                            kid = None
                            x += 1

                        else:
                            x += 1

            elif '--- Saturation States of Pure Solids ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    # ## log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # ## '******'' fills in the value region for numbers
                        # ## lower than -999.9999. Replace with boundary condition
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                        x += 1
                    elif 'None' not in lines[i + x]:
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(lines[i + x][31:44])]
                        x += 1
                    else:
                        x += 1

            elif camp.SS and ' --- Saturation States of Solid Solutions ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    # ## log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # ## '******' fills in the value region for numbers
                        # ## lower than -999.9999. Replace with boundary condition
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                        x += 1
                    elif 'None' not in lines[i + x]:
                        build_dict[f'qk_{lines[i + x][:30].strip()}'] = [float(lines[i + x][44:55])]
                        x += 1
                    else:
                        x += 1

            elif '    --- Fugacities ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):

                    if 'None' not in lines[i + x]:  # log f
                        if re.findall(r'\*{4}', lines[i + x]):
                            # ## '******'' fills in the value region for numbers
                            # ## lower than -999.9999. Replace with boundary condition
                            build_dict[f'f_{lines[i + x][:30].strip()}'] = [float(-999.9999)]
                            x += 1
                        else:
                            build_dict[f'f_{grab_str(lines[i + x], 0)}'] = [float(lines[i + x][28:41])]
                            x += 1
                    else:
                        x += 1
                break

        build_dict['uuid'] = [master_dict['uuid']]
        build_dict['ord'] = [master_dict['ord']]
        build_dict['file'] = [master_dict['file']]
        build_dict['run'] = [date]

        build_df = pd.DataFrame.from_dict(build_dict)

        build_df = build_df[col_names]

        return build_df
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_6O_fILE)


def yoeman(camp, keep_running, write_vs_q, write_es3_q, write_es6_q, num_points, no_progress=False):
    """
    Collecting each sailors df output, and then writing it in
    bulk to sql

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param keep_running: should the yoeman continue to run (ie. is there shit
                         left to write to the VS/ES)
    :type keep_running: multiprocessing.value boolean

    :param write_vs_q: queue of lines waiting to be written to vs table
    :type write_vs_q: queue.Queue

    :param write_es6_q: queue of DataFrames waiting to be written to vs table
    :type write_es6_q: queue.Queue

    :param num_points: number of vs points in the order
    :type num_points: int
    """
    conn = establish_database_connection(camp)
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


def six_o_data_to_sql(conn, table, df):
    """
    Commit the 6o DataFrame to sql

    :param conn: sql database connection
    :type conn: :class: sqlite3.Connection

    :param table: name of sql table
    :type table: str

    :param df: DataFrame contain the 6o information to written to the es table
    :type df: 'pandas.core.frame.DataFrame'

    """
    df.to_sql(table, conn, if_exists='append', index=False)


def reset_sailor(paths, vs_queue, uuid, code):
    """
    The sailor is finished, for better or worse. Close up shop.

    (1) Report to vs table 'camp_name' via server connection 'conn' the
        exit 'code' for 'file' with unique vs_table id 'uuid'.
    (2) Step back into order folder 'order_path' for next vs point.

    :param paths: path to order folder
    :type paths: SailorPaths

    :param vs_queue: a waiting list of lines that need to be written to vs table
    :type vs_queue: class 'multiprocessing.managers.AutoProxy[Queue]

    :param uuid: 'Universally Unique IDentifier'
    :type uuid: str

    :param code: custom exit codes describing eq3/6 errors
    :type code: int

    :param delete_local: do you want to keep the local folder full of the eq3/6 files?
    :type delete_local: boolean

    """
    # This only takes like 1e-5 seconds even with the put
    this_point = (int(code), uuid)
    vs_queue.put_nowait(this_point)
    if not paths.keep:
        shutil.rmtree(paths.directory)
