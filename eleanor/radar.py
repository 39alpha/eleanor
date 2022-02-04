# ###
# ### Radar
# ### Controls the visualization fo the orders run by the helmsman
# ### Tucker Ely, Douglas G. Moore, Cole Mathis

import sys
# import os
# import time
# import multiprocessing
# import re
# import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ### custom packages

from .hanger.db_comms import establish_database_connection, retrieve_combined_records
from .hanger.db_comms import get_column_names
from .hanger.data0_tools import determine_species_set
# from .hanger.tool_room import WorkingDirectory

# import eleanor.campaign as campaign

def Radar(camp, ord_id=None, limit=1000):
    """ what does radar do?

    :param ord_id: order numebr of interest, can by one order (as int) or list of orders.
    :param limit: numebr of sample points to limit plotting to
        order calls can be very large. Set limit to -1 for all.

    """

    x_sp, y_sp, z_sp = ['H+_e', 'CO2_e', '']

    if not ord_id:
        sys.exit('please suplly order id, or list of order ids to be plotted')
    if type(ord_id) == int:
        # ### convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]

    with camp.working_directory():

        # ### compile usefull plotting information specific to the loaded campaign

        # ### species assciated with this campaign, as per the huffer 3o.
        elements, aqueous_sp, solids, solid_solutions, gases = determine_species_set(path='huffer/')

        # ### columns contained int eh vs and es table for loaded campaign
        conn = establish_database_connection(camp)
        vs_col_names = get_column_names(conn, 'vs')
        es_col_names = get_column_names(conn, 'es')

        # ### grab orders, concatinating the dataframe, 1 record retrieved per
        # ### ord_id.
        df_list = []

        where_constrain = 'CO2_e > -2.5'

        for order in ord_id:
            df = retrieve_combined_records(conn, vs_col_names, es_col_names, limit, ord_id=order,
                                           where_constrain=where_constrain)
            df_list.append(df)

        conn.close()

        df = pd.concat(df_list)

        if z_sp == '':
            plt.scatter(df[x_sp], df[y_sp], facecolors='black', marker='o',
                        alpha=0.3, edgecolor=None, s=4, linewidth=0)

            # plt.xlim([1, 14])
            # plt.ylim([-1.8, 1])
            plt.xlabel(x_sp)
            plt.ylabel(y_sp)

        if where_constrain is not None:
            plt.title(f'{camp.name}   ord {ord_id}   n = {len(df)}\n where {where_constrain}')
        else:
            plt.title(f'{camp.name}   ord {ord_id}   n = {len(df)}')
        plt.show()

def plot_xy_dots():
    pass
