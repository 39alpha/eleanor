import os
import re
import shutil
from os.path import join, realpath
from queue import Queue
from typing import Any

import numpy as np
import pandas as pd

from .campaign import Campaign
from .exceptions import EleanorException, EleanorFileException, RunCode
from .hanger.eq36 import eq3, eq6
from .hanger.tool_room import WorkingDirectory, grab_float, grab_lines, grab_str, mine_pickup_lines, mk_check_directory


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
    :type keep_every_n_files: int
    """

    def __init__(self, scratch_dir: str, order: int, file: int, keep_every_n_files: int):
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


def sailor(camp: Campaign,
           scratch_path: str,
           vs_queue: Queue,
           es3_queue: Queue,
           es6_queue: Queue,
           date: str,
           dat: list,
           elements: list[str],
           solids: list[str],
           ss: list[str],
           ss_kids: list[str],
           vs_col_names: list[str],
           es3_col_names: list[str],
           es6_col_names: list[str],
           keep_every_n_files: int = 10000) -> None:
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
        for name in camp.target_rnt.keys():
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

        if camp.data1_dir is None:
            raise EleanorException('campaign does not have a data1 directory path')

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


def mine_3o(camp: Campaign, date: str, elements: list[str], solids: list[str], ss: list[str], ss_kids: list[str],
            file: str, master_dict: dict[str, Any], col_names: list[str]) -> pd.DataFrame:
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

    build_dict: dict[str, list[int | float | str]] = {k: [] for k in col_names}
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
                # eq/kg.H2O
                build_dict['charge_imbalance_eq'] = [grab_float(lines[i], -1)]

            elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    if grab_str(lines[i + x], 0) != 'O2(g)':
                        # '******' shows up with species are less than -99999.0 which signifies that it was suppressed.

                        # -3 is log molality
                        if '****' in grab_str(lines[i + x], -3):
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -3)]

                        # -1 position is log activity,
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
                        # '******'' fills in the value region for numbers lower than -999.9999. Replace with boundary
                        # condition log Q/K
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
                    # log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # '******' fills in the value region for numbers lower than -999.9999. Replace with boundary
                        # condition
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
                            # '******'' fills in the value region for numbers lower than -999.9999. Replace with
                            # boundary condition
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

        # Reorganize columns to match es table
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


def mine_6o(camp: Campaign, date: str, elements: list[str], solids: list[str], ss: list[str], ss_kids: list[str],
            file: str, master_dict: dict[str, int | float | str], col_names: list[str]) -> pd.DataFrame:
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
    build_dict: dict[str, list] = {k: [] for k in col_names}
    build_dict['extended_alk'] = [np.nan]  # undefined for systems over 50 in EQ36 output

    for _ in solids + ss + ss_kids:
        build_dict[f'm_{_}'] = [0.0]  # mols precip must be preset, as its field is not inculsive

    try:
        lines = grab_lines(file)  # 6o file

        run_code = RunCode.NOT_RUN
        search_for_xi = False
        for i in range(len(lines) - 1, 0, -1):
            # Search from bottom of file
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
            # `run_code has not be altered, therefore unknown error

            # build_df = pd.DataFrame.from_dict(build_dict)
            raise EleanorException('no reaction path termination status found', code=RunCode.FILE_ERROR_6O)

        # Populate the ES table
        if camp.target_rnt != {}:
            for i in range(len(lines)):
                if '   Affinity of the overall irreversible reaction=' in lines[i]:
                    # the first instance of this line is xi = 0.0
                    # (initial disequilibria with target mineral)
                    build_dict["initial_aff"] = [grab_float(lines[i], -2)]
                    break
        else:
            build_dict["initial_aff"] = [0.0]

        # Search from beginning of last xi step (set in last_xi_step_begins) grab xi_max. since initial index contains
        # log Xi.
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
                    # Limited salinity sought
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
                # Actual charge imbalance eq/kg.H2O
                build_dict['charge_imbalance_eq'] = [grab_float(lines[i + 2], -2)]

            # elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
            #     x = 4
            #     while not re.findall('^\n', lines[i + x]):
            #         if grab_str(lines[i + x], 0) != 'O2(g)':
            #             # -1 position is log activity, -3 is log molality
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
                        # '******' shows up with species are less than -99999.0 which signifies that it was suppressed.

                        # -3 is log molality
                        if '****' in grab_str(lines[i + x], -3):
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [-99999.0]
                        else:
                            build_dict[f'm_{grab_str(lines[i + x], 0)}'] = [grab_float(lines[i + x], -3)]

                        # -1 position is log activity,
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
                            # Two blank lines signifies end of block
                            break

                        elif re.findall('^\n', lines[i + x]):
                            # Single blank lines separate solids from solid slutions reporting
                            parent = None
                            x += 1

                        elif re.findall('^ [^ ]', lines[i + x]):
                            # Pure phases and solid solutions parents
                            parent = lines[i + x][:25].strip()
                            build_dict[f'm_{lines[i + x][:25].strip()}'] = [grab_float(lines[i + x], -3)]
                            x += 1

                        elif re.findall('^   [^ ]', lines[i + x]):
                            # Solid solution endmember. Grab with parent association
                            kid = lines[i + x][:25].strip()
                            build_dict[f'm_{kid}_{parent}'] = [grab_float(lines[i + x], -3)]
                            kid = None
                            x += 1

                        else:
                            x += 1

            elif '--- Saturation States of Pure Solids ---' in lines[i]:
                x = 4
                while not re.findall('^\n', lines[i + x]):
                    # log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # '******'' fills in the value region for numbers lower than -999.9999. Replace with boundary
                        # condition
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
                    # log Q/K
                    if re.findall(r'\*{4}$', lines[i + x]):
                        # '******' fills in the value region for numbers lower than -999.9999. Replace with boundary
                        # condition
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
                            # '******'' fills in the value region for numbers lower than -999.9999. Replace with
                            # boundary condition
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
        raise EleanorFileException(e, code=RunCode.NO_6O_FILE)


def reset_sailor(paths: SailorPaths, vs_queue: Queue, uuid: str, code: RunCode) -> None:
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
