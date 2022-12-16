"""The Navigator is the main tool to construct orders for the Helmsman to distribute"""
# Navigator.py
# Generates orders (sets of points in VS) to be stored in VS
# postgresql database. These orders are to be managed by the
# helmsman at her leisure.
# Tucker Ely and then 39Alpha
# October 6nd 2020 and then Dec 12th 2021

from sqlite3.dbapi2 import Error
import uuid
import random
import os, sys
import time

import numpy as np
import pandas as pd

# loaded campagin
# import eleanor.campaign as campaign

from .hanger.eq36 import eq3
from .hanger import db_comms
from .hanger.tool_room import mk_check_del_directory, grab_lines, WorkingDirectory
from .hanger.data0_tools import determine_species_set
from .hanger.data0_tools import determine_ele_set, determine_loaded_sp, species_info
from .hanger.data0_tools import SLOP_DF, TPCurve

# ### temporary fix.
mw = {'O': 15.99940,
      'C': 12.01100,
      'S': 32.06600,
      'Ca': 40.07800,
      'K': 39.09830,
      'Fe': 55.84700,
      'Mg': 24.30500,
      'Na': 22.98977,
      'Si': 28.08550,
      'O': 15.99940,
      'H': 1.00794,
      'P': 30.97362,
      'Sr': 87.62000,
      'Cl': 35.45270,
      'F': 18.99840,
      'Br': 79.90400,
      'B': 10.81000}
basis_mw = {
    "HCO3-": 3 * mw['O'] + mw['H'] + mw['C'],
    "O2": 2 * mw['O'],
    "Na+": mw['Na'],
    "Mg+2": mw['Mg'],
    "Ca+2": mw['Ca'],
    "K+": mw['K'],
    "Sr+2": mw['Sr'],
    "Cl-": mw['Cl'],
    "SO4-2": mw['S'] + 4 * mw['S'],
    "Br-": mw['Br'],
    "F-": mw['F'],
    "B(OH)3": mw['B'] + 3 * mw['O'] + 3 * mw['H']
}


def Navigator(this_campaign, quiet=False):
    """
    The Navigator decides where to go (see what we did there), given the
    praticulars of the loaded Campaign. The Navigator drafts an order,
    which contain a collection of modeling sample points, and stores them in
    the VS (Variable Space) table of the loaded campaign's SQL database.

    Each line in the VS table (which is a vs point in n dimensiopns) contains
    enough information to define a closed chemical system in those n dimensions
    and thus contains enough information to execute eq3 and eq6, depending on
    the praticulars of the loaded campaign.

    Currently only two VS point distributions are supported.
    (1) :param:`'this_campaign.distro'` == 'BF'
        Brute Force, which calculates evenily spaced points for all non-fixed
        dimensions.

    (2) :param:`'this_campaign.distro'` == 'random'
        Which randomily selects points for the non-fixed dimensions.

    :param this_campaign: loaded campaign
    :type this_campaign: :class:`Campaign` instance

    """

    # Enter the Campaigns env
    with this_campaign.working_directory():
        if not quiet:
            print(f'Preparing order for campagin {this_campaign.name}.\n')

        conn = db_comms.establish_database_connection(this_campaign)

        # determine campaign status in sql database.
        # If VS/ES tables already exist, then dont touch them,
        # just determine the next new order number.
        # If no tables exists for the campaign, then set order number to 1.
        order_number = db_comms.get_order_number(conn, this_campaign)
        file_number = db_comms.get_file_number(conn, this_campaign, order_number)

        # run huffer to initiate VS/ES if no tables exist
        if order_number == 1:
            # new campaign
            huffer(conn, this_campaign, quiet=quiet)

        # Grab non O/H elements and species data from the verbose huffer test.3o files
        elements = determine_ele_set(path="huffer/")

        # Current order birthday
        date = time.strftime("%Y-%m-%d", time.gmtime())

        # Generate orders
        if this_campaign.distro == 'random':
            orders = random_uniform_order(this_campaign, date, order_number, file_number,
                                          this_campaign.reso, elements, quiet=quiet)

        elif this_campaign.distro == 'BF':
            orders = brute_force_order(this_campaign, date, order_number, file_number, elements,
                                       quiet=quiet)

        # Send dataframe containing new orders to postgres database
        orders_to_sql(conn, 'vs', order_number, orders, quiet=quiet)

        conn.close()

        if not quiet:
            print('The Navigator has completed her task.')
            print('   While she detected no "obvious" faults,')
            print('   she notes that you may have fucked up')
            print('   repeatedly in ways she couldnt anticipate.\n')


def huffer(conn, camp, quiet=False):
    """
    The huffer runs test 3i files to determine the loaded elements and species
    for said campaign, and to check for obvious user erros given system
    configuration.

    The huffer also establishes the VS (variable space, input) and ES
    (equilibrium space, output) tables in the campaign SQL database.
    These are only set up the first time a campaign is run. Subsequent
    calls to the same campaign simply generate new sequentially numberd orders.

    :param conn: sql database connnection
    :type conn: :class: sqlite3.Connection

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    """
    if not quiet:
        print('Running the Huffer.')

    mk_check_del_directory("huffer")
    with WorkingDirectory('huffer'):
        [T], [P], [curve] = TPCurve.sample(camp.tp_curves, 1)

        state_dict = {}
        for _ in camp.vs_state.keys():
            if _ == 'fO2':
                if type(camp.vs_state['fO2']) == str:
                    # ### sp constraint
                    state_dict[_] = camp.vs_state[_]
                else:
                    state_dict[_] = np.mean(camp.vs_state[_])
            else:
                state_dict[_] = np.mean(camp.vs_state[_])

        state_dict['T_cel'] = T
        state_dict['T_bar'] = P

        basis_dict = {}
        for _ in camp.vs_basis.keys():
            basis_dict[_] = np.mean(camp.vs_basis[_])

        # ### huffer run on unsuppressed (aq species) file, to get complete es table columns, should
        # ### different orders of the same campaign use different suppress_aq lists.
        camp.local_3i.write('test.3i', state_dict, basis_dict, camp.cb, [], output_details='v')
        data1_file = os.path.realpath(os.path.join(camp.data1_dir, curve.data1file))
        out, err = eq3(data1_file, 'test.3i')

        try:
            _ = grab_lines('test.3o')
        except FileNotFoundError:
            raise Error("The huffer failed. Figure your shit out.")

        elements, sp, solids, ss, gasses = determine_species_set()
        # elements = determine_ele_set()

        # New VS table based on vs_state and vs_basis
        db_comms.create_vs_table(conn, camp, elements)

        # Determine column names of the ES table
        # sp_names, ss_names = determine_loaded_sp()

        # Build the ES tables (es3 and es6)
        db_comms.create_es_tables(conn, camp, sp + solids, ss, gasses, elements)

    if not quiet:
        print('   Huffer complete.\n')


def random_uniform_order(camp, date, ord, file_number, order_size, elements, precision=6,
                         quiet=False):
    """
    Generate randomily spaced points in VS

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param date: birthdate of order
    :type data: str

    :param ord: the order id, relative to other orders issued for the loaded campagin
    :type ord: int

    :param file_number: the file number to start from
    :type file_number: int

    :param order_size: number of vs points in current order
    :type order_size: int

    :param elements: list of loaded element, excepting O and H
    :type elements: list

    :param precision: number of digits recorded in vs table
    :type precision: int

    :return: dataframe containing all vs points
    :rtype: :class:'pandas.core.frame.DataFrame'

    """
    if not quiet:
        print('Generating order #{} via random_uniform.'.format(ord))

    df = pd.DataFrame()
    df = build_admin_info(camp, df, ord, file_number, order_size, date)

    if camp.target_rnt.items() != {}:
        for reactant, [rtype, morr, rkb1] in camp.target_rnt.items():
            # morr, mols of reactant avaialbe for titration
            if isinstance(morr, list):
                df[f'{reactant}_morr'] = [float(np.round(random.uniform(*morr), precision))
                                          for i in range(order_size)]
            else:
                df[f'{reactant}_morr'] = float(np.round(morr, precision))

            if isinstance(rkb1, list):
                df[f'{reactant}_rkb1'] = [float(np.round(random.uniform(*rkb1), precision))
                                          for i in range(order_size)]
            else:
                df[f'{reactant}_rkb1'] = float(np.round(rkb1, precision))

    # add vs_state dimensions to orders
    for key, value in camp.vs_state.items():
        if key == 'P_bar':
            continue
        if key == 'T_cel':
            df['T_cel'], df['P_bar'], curves = TPCurve.sample(camp.tp_curves, order_size)
            df['data1'] = [curve.data1file for curve in curves]
        if key == 'fO2' and type(value) == str:
            # ### fO2 slaved to species, stand in 0.0
            df[key] = 0.0
        elif isinstance(value, list):
            df[key] = [float(np.round(random.uniform(*value), precision))
                       for i in range(order_size)]
        else:
            df[key] = float(np.round(value, precision))

    dbasis = build_basis(camp, precision, order_size)

    # build basis into main df
    df = pd.concat([df, dbasis], axis=1)

    df = calculate_ele_totals(df, elements, order_size, precision)

    return df

def brute_force_order(camp, date, ord, file_number, elements, precision=6, quiet=False):
    """
    Generate evenily spaced points in VS

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param date: birthdate of order
    :type data: str

    :param ord: the order id, relative to other orders issued for the loaded campagin
    :type ord: int

    :param file_number: the file number to start from
    :type file_number: int

    :param elements: list of loaded element, excepting O and H
    :type elements: list

    :param precision: number of digits recorded in vs table
    :type precision: int

    """
    raise NotImplementedError(
        '''
        With the move to general data0/data1 handling, we aren't sure how we want
        to implement evenly-spaced VS points in the T-S subspace.
        '''
    )

def build_basis(camp, precision, n):
    """
    build basis vs of len = n.
    This is its own function, so that it can iterated over in later versions,
    where we anticipate wanting to pre-optimize basis selection with rejection
    sampling.

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param precision: number of decimal places to round log floats
    :type precision: int

    :return: dataframe with all basis species dimensions for all vs points
    :rtype: :class:'pandas.core.frame.DataFrame'

    """
    df = pd.DataFrame()
    for _ in camp.vs_basis.keys():
        if isinstance(camp.vs_basis[_], list):
            vals = [float(np.round(random.uniform(camp.vs_basis[_][0],
                                                  camp.vs_basis[_][1]),
                                   precision))
                    for i in range(n)]
            df['{}'.format(_)] = vals
        else:
            vals = np.round(camp.vs_basis[_], precision)
            df['{}'.format(_)] = [float(vals) for i in range(n)]
    return df


def build_admin_info(camp, df, ord, file_number, order_size, date):
    """
    Construct the 'admin_info' into dataframe

    :param camp: loaded campaign
    :type camp: :class:`Campaign` instance

    :param df: dataframe, either empty, or with some columns apready in place
    :type df: :class:'pandas.core.frame.DataFrame'

    :param file_number: the file number to start from
    :type file_number: int

    :param order_size: number of vs points in current order
    :type order_size: int

    :param date: birthdate of order
    :type data: str

    :return: dataframe with all admin info columns added
    :rtype: :class:'pandas.core.frame.DataFrame'

    """

    df['uuid'] = [uuid.uuid4().hex for _ in range(order_size)]
    df['camp'] = camp.name
    df['file'] = list(range(file_number, file_number + order_size))
    df['ord'] = ord
    df['birth'] = date
    df['cb'] = camp.cb
    df['code'] = 0  # custom exit codes

    return df


def calculate_ele_totals(df, elements, order_size, precision):
    """
    Calculate element totals, as multiple VS species may
    contain the same element.

    :param df: dataframe with all state and basis dimensions
    :type df: :class:'pandas.core.frame.DataFrame'

    :param elements: list of loaded element, excepting O and H
    :type elements: list

    :param order_size: number of vs points in current order
    :type order_size: int

    :param precision: number of decimal places to round log floats
    :type precision: int

    :return: dataframe with all BF dimenions for all vs points
    :rtype: :class:'pandas.core.frame.DataFrame'
    """
    ele_totals = {}

    for _ in elements:
        ele_totals[_] = [0] * order_size

    for _ in elements:
        # for a given element present in the campaign
        local_vs_sp = []
        for b in list(SLOP_DF.index):
            # for species listed/constrained in vs
            sp_dict = species_info(b)  # keys = constiuent elements, values= sto
            if _ in sp_dict.keys():
                # if element _ in vs species, store in
                # local_vs_sp as ['vs sp name',
                # sto_of_element_in_sp]
                local_vs_sp.append([b, sp_dict[_]])

        # build total element molality column into VS df
        for b in local_vs_sp:
            # for each species b in loaded data0 that contins target element _,
            # identify the ones that are loaded in vs (list(df.columns)).
            if '{}'.format(b[0]) in list(df.columns):
                # basis is present in campaign, so add its molalities
                # to element total
                ele_totals[_] = ele_totals[_] + float(b[1]) * (10 ** df['{}'.format(b[0])])

        df['{}'.format(_)] = np.round(np.log10(ele_totals[_]), precision)
    return df


def orders_to_sql(conn, table, ord, df, quiet=False):
    """
    Write dataframe 'df' to sql 'table' for order number 'ord' on
    connection 'conn'

    :param conn: sql database connnection
    :type conn: :class: sqlite3.Connection

    :param table: sql table name
    :type table: str

    :param ord: order number
    :type ord: int

    :param df: pandas Dataframe containing the orders
    :type df: :class: pandas.core.frame.DataFrame

    """
    if not quiet:
        print(f'Writing order #{ord} to table {table}')

    df.to_sql(table, con=conn, if_exists='append', index=False)
    conn.commit()
    conn.close()

    if not quiet:
        print("  Orders written.\n")

