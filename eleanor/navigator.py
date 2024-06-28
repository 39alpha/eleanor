"""The Navigator is the main tool to construct orders for the Helmsman to distribute"""

import os
import random
import sys
import time
import uuid
from sqlite3.dbapi2 import Error

import numpy as np
import pandas as pd

from .config import Config
from .hanger import db_comms
from .hanger.tool_room import WorkingDirectory, ensure_directory
from .kernel.interface import AbstractKernel


def Navigator(this_campaign, config: Config, kernel: AbstractKernel, quiet=False):
    """
    The Navigator decides where to go (see what we did there), given the
    praticulars of the loaded Campaign. The Navigator drafts an order,
    which contain a collection of modeling sample points, and stores them in
    the VS (Variable Space) table of the loaded campaign's SQL database.

    Each line in the VS table (which is a vs point in n dimensions) contains
    enough information to define a closed chemical system in those n dimensions
    and thus contains enough information to execute eq3 and eq6, depending on
    the praticulars of the loaded campaign.

    Currently only one VS point distributions is supported.
    :param: `'this_campaign.distro'` == 'random'
    Which randomly selects points for the non-fixed dimensions.

    :param: this_campaign: loaded campaign
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

        # Always run the huffer. This is necessary because the huffer is responsible for ensuring that the DB
        # structure is sound.
        elements, aqueous_species, solids, solid_solutions, _, gases = kernel.prime()

        # New VS table based on vs_state and vs_basis
        db_comms.create_or_expand_vs_table(conn, this_campaign, elements)

        # Build the ES tables (es3 and es6)
        if not this_campaign.SS:
            solid_solutions = []

        db_comms.create_es_tables(conn, this_campaign, aqueous_species, solids, solid_solutions, gases, elements)

        # Current order birthday
        date = time.strftime("%Y-%m-%d", time.gmtime())

        # Generate orders
        if this_campaign.distro == 'random':
            orders = random_uniform_order(this_campaign,
                                          date,
                                          order_number,
                                          file_number,
                                          this_campaign.reso,
                                          elements,
                                          quiet=quiet)

        else:
            err_message = (f'vs_distro: {this_campaign.distro} is not', 'supported at this time. Only "random"')
            raise Error(err_message)

        # Send dataframe containing new orders to postgres database
        orders_to_sql(conn, 'vs', order_number, orders, quiet=quiet)

        conn.close()

        if not quiet:
            nav_success_message = ('The Navigator has completed her task.\n'
                                   'It detected no "obvious" faults.\n'
                                   'Note that you may have fucked up\n'
                                   'repeatedly in myriad and unimaginable ways.\n')
            print(nav_success_message)


def random_uniform_order(camp, date, ord, file_number, order_size, elements, precision=6, quiet=False):
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

    d0 = camp.representative_data0

    df = pd.DataFrame()
    df = build_admin_info(camp, df, ord, file_number, order_size, date, quiet=quiet)

    if camp.target_rnt.items() != {}:
        for reactant, [rtype, morr, rkb1] in camp.target_rnt.items():
            # morr, mols of reactant avaialbe for titration
            if isinstance(morr, list):
                df[f'{reactant}_morr'] = [float(np.round(random.uniform(*morr), precision)) for i in range(order_size)]
            else:
                df[f'{reactant}_morr'] = float(np.round(morr, precision))

            if isinstance(rkb1, list):
                df[f'{reactant}_rkb1'] = [float(np.round(random.uniform(*rkb1), precision)) for i in range(order_size)]
            else:
                df[f'{reactant}_rkb1'] = float(np.round(rkb1, precision))

    # add vs_state dimensions to orders
    for key, value in camp.vs_state.items():
        if key == 'P_bar':
            continue
        if key == 'T_cel':
            df['T_cel'], df['P_bar'], curves = TPCurve.sample(camp.tp_curves, order_size)
            df['data1'] = [curve.data1file for curve in curves]
        if key == 'fO2' and isinstance(camp.vs_state['fO2'], str):
            df[key] = camp.vs_state['fO2']

        elif isinstance(value, list):
            df[key] = [float(np.round(random.uniform(*value), precision)) for i in range(order_size)]
        else:
            df[key] = float(np.round(value, precision))

    dbasis = build_basis(camp, precision, order_size)

    # build basis into main df
    df = pd.concat([df, dbasis], axis=1)
    df = calculate_ele_totals(d0, df, elements, order_size, precision)

    return df


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
    for k in camp.vs_basis.keys():
        if isinstance(camp.vs_basis[k], list):
            vals = [
                float(np.round(random.uniform(camp.vs_basis[k][0], camp.vs_basis[k][1]), precision)) for i in range(n)
            ]
            df['{}'.format(k)] = vals
        else:
            val = float(np.round(camp.vs_basis[k], precision))
            df['{}'.format(k)] = [val for _ in range(n)]
    return df


def build_admin_info(camp, df, ord, file_number, order_size, date, quiet=False):
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

    :param quiet: suppress console output
    :type quiet: bool

    :return: dataframe with all admin info columns added
    :rtype: :class:'pandas.core.frame.DataFrame'

    """
    if not quiet:
        print("Order size: ", order_size)

    df['uuid'] = [uuid.UUID(int=random.getrandbits(128)).hex for _ in range(order_size)]
    df['camp'] = camp.name
    df['file'] = list(range(file_number, file_number + order_size))
    df['ord'] = ord
    df['birth'] = date
    df['cb'] = camp.cb
    df['code'] = 0  # custom exit codes

    if not quiet:
        print(df)

    return df


def calculate_ele_totals(d0, df, elements, order_size, precision):
    """
    Calculate element totals, as multiple VS species may
    contain the same element.

    :param d0: the campaign's representative Data0 file
    :type d0: eleanor.hanger.eq36.data0.Data0

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

    for e in elements:
        ele_totals[e] = [0] * order_size

    for e in elements:
        # for a given element present in the campaign
        local_vs_sp = []
        for b in d0.species_names:
            # for species listed/constrained in vs
            sp_dict = d0[b].composition
            if e in sp_dict.keys():
                # if element _ in vs species, store in
                # local_vs_sp as ['vs sp name',
                # sto_of_element_in_sp]
                local_vs_sp.append([b, sp_dict[e]])

        # build total element molality column into VS df
        for b in local_vs_sp:
            # for each species b in loaded data0 that contins target element _,
            # identify the ones that are loaded in vs (list(df.columns)).
            if f'{b[0]}' in list(df.columns):
                # basis is present in campaign, so add its molalities
                # to element total
                ele_totals[e] = ele_totals[e] + float(b[1]) * (10**df['{}'.format(b[0])])

        df[f'm_{e}'] = np.round(np.log10(ele_totals[e]), precision)
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

    if len(df) == 0:
        # TODO: Not sure if this is the  correct way to exit the code. Its just the one I know.
        sys.exit(' Orders dataframe is empty. WTF?')
    if not quiet:
        print(f'Writing order #{ord} to table {table}')
    df.to_sql(table, con=conn, if_exists='append', index=False)
    conn.commit()
    conn.close()

    if not quiet:
        print("  Orders written.\n")
