"""The Navigator is the main tool to construct orders for the Helmsman to distribute.
   It generates orders- sets of points in the variable space (VS) which are stored in the table
   `VS` in the SQLight DB. These orders are to be managed by the Helmsmen at her leisure.
"""
# Tucker Ely and then 39Alpha
# October 6nd 2020 and then Dec 12th 2021

from sqlite3.dbapi2 import Error
import sys
import uuid
import random
import itertools
import re
import os
import time

import numpy as np
import pandas as pd

# loaded campagin
# import eleanor.campaign as campaign

from .hanger.eq36 import eq3
from .hanger import db_comms
from .hanger.db_comms import get_column_names
from .hanger.tool_room import mk_check_del_directory, grab_lines
from .hanger.data0_tools import determine_ele_set, data0_suffix, determine_loaded_sp, species_info
from .hanger.data0_tools import SLOP_DF


def Navigator(this_campaign):
    """ Main function of the navigator. The Navigator generates samples in the variable space for
        the Helmsmen to run when needed. While the Navigator generates data it tests one run, for
        quality control using the huffer to ensure at least some of the samples will run in EQ3/6

        :param this_campaign: A campaign object which defines the variable space for the Helmsman,
        see Campaign.py for more details.
    """

    # Enter the Campaigns env
    with this_campaign.working_directory():
        print('Preparing Orders from campagin {}.\n'.format(this_campaign.name))

        conn = db_comms.establish_database_connection(this_campaign)

        # Determine campaign status in postgres database.
        # If VS/ES tables already exist, then dont touch them,
        # just determine the next new order number.
        # If no tables exists for the campaign, then run the
        # huffer to initiate VS/ES, and set order number to 1.
        order_number = db_comms.get_order_number(conn, this_campaign)

        if order_number == 1:
            # new campaign
            huffer(conn, this_campaign)

        # grab needed species and element data from huffer test.3o files
        elements = determine_ele_set(path="huffer/")
        # sp_names = determine_loaded_sp(path =  "huffer/")

        # current order birthday
        date = time.strftime("%Y-%m-%d", time.gmtime())

        # Generate orders. This can be altered later to call a variety of
        # functions that yeild different VS point distributions.
        if this_campaign.distro == 'random':
            orders = random_uniform_order(this_campaign, date, order_number,
                                          this_campaign.reso, elements)

        elif this_campaign.distro == 'BF':
            orders = brute_force_order(conn, this_campaign, date, order_number, elements)

        # Send dataframe containing new orders to postgres database
        orders_to_sql(conn, 'vs', order_number, orders)

        conn.close()

        print(' The Navigator has done her job.')
        print('   While she detected no "obvious" faults,')
        print('   she notes that you may have fucked up')
        print('   repeatedly, but the QA code required to')
        print('   detect your fuck ups has not been written.\n')

def huffer(conn, camp):
    """
    The huffer performs steps required to initiate a new campaign.
    It is only run to initiate a new campaign, and not to initiate
    new orders on an existing campaign. This is becuase the VS and
    ES only need to be set up once per campaign. Any information
    that may be needed throughout the life of a campign which the
    huffer might provide, is stored in the huffers folder.

    (1) Test instantiated 3i file for errors.
    (2) Determine the correct varaibels for vs and es
        tables given loaded species.
    (3) Establish dynamically accessed data0's (not yet built)

    """
    print('Running the Huffer.')

    # build huffer directory and step in
    mk_check_del_directory("huffer")  # build test directory
    mk_check_del_directory("fig")  # build figure directory

    os.chdir("huffer")  # step into directory

    # build test.3i file from mean vlaues for each variable that is
    # set to a range in the new campaign.
    state_dict = {}
    for _ in camp.vs_state.keys():
        state_dict[_] = np.mean(camp.vs_state[_])

    basis_dict = {}
    for _ in camp.vs_basis.keys():
        basis_dict[_] = np.mean(camp.vs_basis[_])

    # (1) build and run test.3i
    print('\n Processing test.3i.')

    # select proper data0
    suffix = data0_suffix(state_dict['T_cel'], state_dict['P_bar'])

    # build 'verbose' 3i, with solid solutions on. cb defaults to H+ jsut for
    # huffer.
    camp.local_3i.write(
        'test.3i', state_dict, basis_dict, 'H+', output_details='v')
    data1_file = os.path.join(camp.data0_dir, "data1." + suffix)
    out, err = eq3(data1_file, 'test.3i')

    try:
        # if 3o is generated
        _ = grab_lines('test.3o')
    except FileNotFoundError:
        raise Error("The huffer didn't make the .3o file, figure your shit out.")

    # Run QA on 3i
    elements = determine_ele_set()

    # estalibsh new table based on vs_state and vs_basis
    db_comms.create_vs_table(conn, camp, elements)

    # (2) build state_space for es table
    # list of loaded aq, solid, and gas species to be appended
    sp_names = determine_loaded_sp()

    # estalibsh new ES table based on loaded species.
    db_comms.create_es_table(conn, camp, sp_names, elements)

    os.chdir('..')

    print('\n Huffer complete.\n')

# ##################    postgres table functions   ####################
def orders_to_sql(conn, table, ord, df):
    """
    Write pandas dataframe 'df' to sql 'table' on connection'conn.'
    """
    print('Attempting to write order # {}'.format(ord))
    print('  to sql table {}'.format(table))
    print('  . . . ')

    df.to_sql(table, con=conn, if_exists='append', index=False)  # , index_label = "uuid")
    conn.commit()
    conn.close()

    print("  Orders writen.\n")

# #############################    Order forms    ##############################

def brute_force_order(conn, camp, date, order_number, elements):
    """
    Generate randomily distributed points in VS to be managed
    by the helmsman as a sinlge 'order'
    ### (1) determin brute force dimensions, then calculate into order

    ### (2) add 6i rnt info
    ### (2) add state
    ### (3) add basis
    """

    print('Generating order # {} via brute_force_order().'.format(order_number))

    # (1) add BF_var dimensions to order
    # calculate order size, warn user, then proceded:
    BF_vars = {}  # brute force variables

    for _ in camp.target_rnt.keys():
        if isinstance(camp.target_rnt[_][1], (list)):
            BF_vars['"{}_morr"'.format(_)] = camp.target_rnt[_][1]
        if isinstance(camp.target_rnt[_][2], (list)):
            BF_vars['"{}_rkb1"'.format(_)] = camp.target_rnt[_][2]

    for _ in camp.vs_state.keys():
        if isinstance(camp.vs_state[_], (list)):
            BF_vars[_] = camp.vs_state[_]

    for _ in camp.vs_basis.keys():
        # cycle through basis species
        if isinstance(camp.vs_basis[_], list):
            BF_vars[_] = camp.vs_basis[_]

    # warn user of dataframe size to be built
    order_size = camp.reso**len(BF_vars)
    # print("Order size: " + str(order_size))
    if order_size > 100000:
        answer = input('\n\n The brute force method will generate {} \n\
                        VS samples. Thats pretty fucking big.\n\
                        Are you sure you want to proceed? (Y E S/N)\n'.format(order_size))
        if answer == 'Y E S':
            pass
        else:
            sys.exit("ABORT !")

    df = process_BF_vars(BF_vars, camp.reso)
    # value precision in postgres table
    precision = 6
    # unique id column. also sets row length, to which all
    # following constants will follow
    df['uuid'] = [uuid.uuid4().hex for _ in range(order_size)]
    df['camp'] = camp.name
    # file name numbers
    df['file'] = list(range(order_size))
    df['ord'] = order_number
    df['birth'] = date
    # run codes.  This variable houses error codes once the orders
    # of been executed
    df['code'] = 0

    # (2) add vs_rnt dimensions to orders
    for _ in camp.target_rnt.keys():
        # handle morr
        if isinstance(camp.target_rnt[_][1], (list)):
            vals = [float(np.round(random.uniform(camp.target_rnt[_][1][0],
                    camp.target_rnt[_][1][1]), precision)) for i in
                    range(order_size)]
            df['{}_morr'.format(_)] = vals

        else:
            # _ is fixed value. n = order_size is automatic for a
            # constant given existing df length
            df['{}_morr'.format(_)] = float(np.round(camp.target_rnt[_][1],
                                                     precision))

        # handle rkb1
        if isinstance(camp.target_rnt[_][2], (list)):
            pass
        else:
            # is fixed value. n = order_size is automatic for a
            # constant given existing df length
            df['{}_rkb1'.format(_)] = float(np.round(camp.target_rnt[_][2],
                                                     precision))

    # (3) add fixed vs_state dimensions to orders
    for _ in camp.vs_state.keys():
        if isinstance(camp.vs_state[_], (list)):
            pass
        else:
            # is fixed value. n = order_size is automatic for a constant
            # given existing df length
            df['{}'.format(_)] = float(np.round(camp.vs_state[_], precision))

    # (4) add fixed vs_basis dimensions to orders
    for _ in camp.vs_basis.keys():
        # cycle through basis species
        if isinstance(camp.vs_basis[_], list):
            pass
        else:
            # is fixed value. n = order_size is automatic for a constant
            # given existing df length
            vals = np.round(camp.vs_basis[_], precision)
            df['{}'.format(_)] = float(vals)
    # stack df's together
    # calculate element totals columns
    # aqueous element totals. vs point-local dictionary
    ele_totals = {}
    for _ in elements:
        ele_totals[_] = [0] * order_size

    # build element totals one element at a time, as multiple vs spcies may
    # contain the same element.

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
                # technical note: recalculating the amount of "O" present by evaluating
                # the postgres database in psql with
                #     ( select (4*10^"SO4-2" + 3*10^"HCO3-"
                #      + 3*10^"B(OH)3" + 2*10^"SiO2" + 4*10^"HPO4-2"
                #      + 3*10^"NO3-"), 10^"O" from teos_cal_2_vs;)
                # reveals potential machine errror magnitudes. as the element totals calculated
                # in the lines immediately preceduing this comment are off by +- 10^-7->10^-9
                # from the psql derived totals. THis is problematic given that I do evalute element
                # totals across 10^-7 --> 10^-9  concentrations. I imagine thaty i can decrese
                # this error by not moving between log and normal so many times.

        df['{}'.format(_)] = np.round(np.log10(ele_totals[_]), precision)

    # reorder columns to match VS table
    cols = get_column_names(conn, 'vs')
    df = df[cols]

    print('  Order # {} established (n = {})\n'.format(order_number, order_size))

    return df

def process_BF_vars(BF_vars, reso):
    """
    create dataframe containing all brute force samples
    """
    # TODO: Check this against old method
    all_ranges = []
    for this_var in BF_vars:
        # want reso = number of sample poiunts to capture min and max values
        # hence manipulation of the max value
        min_val = BF_vars[this_var][0]  # -8
        max_val = BF_vars[this_var][1]  # -6
        # step = (max_val - min_val) / (reso - 1)
        this_range = np.linspace(min_val, max_val, num=reso)
        all_ranges.append(this_range)
    grid = np.array([np.array(i) for i in itertools.product(*all_ranges)])
    # grid  = grid.reshape(-1)
    # grid = np.mgrid[all_ranges]

    return pd.DataFrame(grid, columns=list(BF_vars.keys()))

def random_uniform_order(camp, date, order_number, order_size, elements, threshold_cb=0.001):
    """
    Generate randomily sampled points in VS to be managed by the
    helmsman as a sinlge 'order'
    ### (1) add info to all runs
    ### (2) add 6i rnt info
    ### (2) add state
    ### (3) add basis
    """

    print('Generating order # {} via random_uniform.'.format(order_number))
    # value precision in postgres table
    precision = 6

    # (1) add run info to orders
    df = pd.DataFrame()
    # unique id column. also sets row length, to which all
    # following constants will follow
    df['uuid'] = [uuid.uuid4().hex for _ in range(order_size)]
    df['camp'] = camp.name
    # file name numbers
    df['file'] = list(range(order_size))
    df['ord'] = order_number
    df['birth'] = date
    # run codes.  This variable houses error codes once the orders
    # of been executed
    df['code'] = 0

    # (2) add vs_rnt dimensions to orders
    for _ in camp.target_rnt.keys():
        # handle morr
        if isinstance(camp.target_rnt[_][1], (list)):
            # _ is range, thus make n=order_size random choices within
            # range
            vals = [float(np.round(random.uniform(camp.target_rnt[_][1][0],
                                                  camp.target_rnt[_][1][1]),
                                   precision)) for i in
                    range(order_size)]

            df['{}_morr'.format(_)] = vals
        else:
            # _ is fixed value. n = order_size is automatic for a
            # constant given existing df length
            df['{}_morr'.format(_)] = float(np.round(camp.target_rnt[_][1], precision))

        # handle rkb1
        if isinstance(camp.target_rnt[_][2], (list)):
            # is range, thus make n=order_size random choices within
            # range
            vals = [float(np.round(random.uniform(camp.target_rnt[_][2][0],
                    camp.target_rnt[_][2][1]), precision)) for i in
                    range(order_size)]
            df['{}_rkb1'.format(_)] = vals

        else:
            # is fixed value. n = order_size is automatic for a
            # constant given existing df length
            df['{}_rkb1'.format(_)] = float(np.round(camp.target_rnt[_][2],
                                            precision))

    # (3) add vs_state dimensions to orders
    
    for _ in camp.vs_state.keys():
        if isinstance(camp.vs_state[_], (list)):
            if _ == "P_bar":
                # P is limited to data0 step size (currently 0.5 bars)
                P_options = [_ / 2 for _ in list(range(int(2 * camp.vs_state[_][0]),
                                                       int(2 * camp.vs_state[_][1])))]

                vals = [random.choice(P_options) for i in range(order_size)]
            else:
                # is range, thus make n=order_size random choices within range
                vals = [float(np.round(random.uniform(camp.vs_state[_][0],
                                                      camp.vs_state[_][1]),
                                       precision))
                        for i in range(order_size)]
            df['{}'.format(_)] = vals

        else:
            # is fixed value. n = order_size is automatic for a constant
            # given existing df length
            df['{}'.format(_)] = float(np.round(camp.vs_state[_], precision))


    # (4) add vs_basis dimensions to orders. The array to be added to the order
    # is built in stages here, to reduce all samoles to a charge imbalance that
    # is realistically managed by cb.
    def build_basis(camp, precision, n):
        """
        build basis vs of len = n.
        THis is a function so that it can be iterable, unlike the other
        vs dimensions, becuase we want to build it in stages after removeing
        rows that are too far from charge balance for any one species to
        realistically adust.
        """
        dlocal = pd.DataFrame()
        for _ in camp.vs_basis.keys():
            # cycle through basis species
            if isinstance(camp.vs_basis[_], list):
                # is range, thus make n=order_size random choices within range
                vals = [float(np.round(random.uniform(camp.vs_basis[_][0],
                                                      camp.vs_basis[_][1]),
                                       precision))
                        for i in range(n)]
                dlocal['{}'.format(_)] = vals
            else:
                # is fixed value. n = order_size is automatic for a constant
                # given existing df length
                vals = np.round(camp.vs_basis[_], precision)
                dlocal['{}'.format(_)] = float(vals)
        return dlocal

    def calculate_charge_imbalance(camp, key_charge, arr):
        n = len(arr)
        new_arr = np.array([0.0] * n)
        for sp in key_charge.keys():
            sp_idx = list(camp.vs_basis.keys()).index(sp)
            new_arr += key_charge[sp] * arr[:, sp_idx]
        return new_arr

    # determine species to measure for charge imbalance
    key_charge = {}  # dict of basis (keys) charges (values)
    for sp in camp.vs_basis.keys():
        explode = re.split(r'([\-+])', sp)
        if len(explode) == 1 or sp == 'H+':
            # no charge
            pass
        elif explode[-1] == '':
            # -1 or +1
            if explode[-2] == '+':
                key_charge[sp] = 1
            elif explode[-2] == '-':
                key_charge[sp] = -1
        elif '-' in explode:
            # <= -2
            key_charge[sp] = -int(explode[-1])
        else:
            # >= +2
            key_charge[sp] = int(explode[-1])

    # build first df of correct length
    dbasis = build_basis(camp, precision, order_size)

    # convert to natural array for removal of rows
    arr = 10**np.array(dbasis)

    # ### calcuate imbalance of each sample.
    d_cb = calculate_charge_imbalance(camp, key_charge, arr)

    # molal cutoff gor +- charge imbalance.
    

    # cycle through arr rows, removing those that violate charge imbalance
    # threshold identified in d_cb
    for _ in list(reversed(range(len(arr)))):
        # remove rows from arr in reverse order that violate
        # charge balance tolerance. first pass.
        if abs(d_cb[_]) > threshold_cb:
            arr = np.delete(arr, _, 0)

    print(f'filling order (n = {order_size}) up based on charge ')
    print(f'    imbalance threshold: {threshold_cb}')
    while len(arr) < order_size:
        print(f'order lenth = {len(arr)}')
        # calculate some more sample points, rebuild dbasis to fill to order size
        new_dbasis = build_basis(camp, precision, order_size)
        new_arr = 10**np.array(new_dbasis)
        d_cb = calculate_charge_imbalance(camp, key_charge, new_arr)
        for _ in list(reversed(range(len(new_arr)))):
            if abs(d_cb[_]) > threshold_cb:
                new_arr = np.delete(new_arr, _, 0)

        # add new_dbasis to dbasis
        arr = np.vstack((arr, new_arr))

    arr = arr[:order_size]  # snip excess

    d_cb = calculate_charge_imbalance(camp, key_charge, arr)

    # build new df from arr, columns = camp.vs_basis.keys()
    # which assumes I left all basis columns in, even those not
    # manipulated by
    dbasis = pd.DataFrame(np.log10(arr), columns=camp.vs_basis.keys())

    # build basis into main df
    df = pd.concat([df, dbasis], axis=1)
    # df.vstack = pd.DataFrame(arr, columns=camp.vs_basis.keys())

    # now chose charge balance
    if camp.cb == 'dynamic':
        # select for speices opposit charge movement
        # key_charge.keys() is ajusted here to remove species
        # known to be problamatic for cb (ie, alot of the element mass)
        # is in neutral sp (e, C, S, N)
        max_keys = df[key_charge.keys()].idxmax(axis=1)
        df['cb'] = max_keys
    else:
        df['cb'] = camp.cb

    # calculate element totals columns
    # aqueous element totals. vs point-local dictionary
    ele_totals = {}
    for _ in elements:
        ele_totals[_] = [0] * order_size

    # build element totals one element at a time, as multiple vs spcies may
    # contain the same element.
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

                # technical note: recalculating the amount of "O" present by evaluating
                # the postgres database in psql with
                #     ( select (4*10^"SO4-2" + 3*10^"HCO3-"
                #      + 3*10^"B(OH)3" + 2*10^"SiO2" + 4*10^"HPO4-2"
                #      + 3*10^"NO3-"), 10^"O" from teos_cal_2_vs;)
                # reveals potential machine errror magnitudes. as the element totals calculated
                # in the lines immediately preceduing this comment are off by +- 10^-7->10^-9
                # from the psql derived totals. THis is problematic given that I do evalute
                # element totals across 10^-7 --> 10^-9  concentrations. I imagine thaty i can
                # decrese this error by not moving between log and normal so many times.

        df['{}'.format(_)] = np.round(np.log10(ele_totals[_]), precision)

    print('  Order # {} established (n = {})\n'.format(order_number, order_size))

    return df
