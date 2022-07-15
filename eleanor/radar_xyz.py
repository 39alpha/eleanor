# ###
# ### Radar
# ### Controls the visualization fo the orders run by the helmsman
# ### Tucker Ely, Douglas G. Moore, Cole Mathis

import matplotlib
import re
import sys
import time
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn_extra.cluster import KMedoids

# ### custom packages

from .hanger.db_comms import establish_database_connection, retrieve_combined_records
from .hanger.db_comms import get_column_names
from .hanger import radar_tools
from .hanger.data0_tools import determine_species_set
from .hanger.radar_tools import get_continuous_cmap
# from .hanger.tool_room import WorkingDirectory

# import eleanor.campaign as campaign

# ### make Radar a class, then add methods for
#    def to_mpl
#    def to_vega

def Radar(camp, x_sp, y_sp, z_sp, description, ord_id=None, limit=1000, where=None, 
          transparent=True, add_analytics=None):
    """
    Plots 3 dimenions from vs and es camp databases
    :param camp: campaign
    :type camp: Class instance
    :param x_sp: x variable,
    :type x_sp: str
    :param y_sp: y variable,
    :type y_sp: str
    :param z_sp: z variable,
    :type z_sp: str
    :param description: notes on data to show beneath image
    :type description: str
    :param ord_id: order numebr of interest
    :type ord_id: can by one order (as int) or list of orders.
    :param limit: UNBUILT numebr of sample points to limit plotting to
        order calls can be very large. Set limit to -1 for all.
    :type limit: int
    :param where: end statement for sql call to limit parameter space search
        region
    :type where: str
    :param transparent: make backgroun on figure transparent?
    :type transparent: boolean
    :param add_analytics: UNBUILT add mean line and sd's to plot
    :type add_analytics: str
    """

    def plt_set(ax, df, x, y, mk, cmap=None, sz=10, fc='white', ec='black',
                lw=0.5):
        """
        plot subset of marhys database with style (mk=marker, sz=marker size,
            fc=face color, ec=edge color, lw-edge line width)

        The subset plotted is the group (groupby), within the column (col_name) on
            the datafram df.

        z order refers to the plotting layer relative to other groups which may
            be plotted ont the same ax, which is exstablished outside this
            function prioir to its first calling.
        """
        ax.scatter(x,
                   y,
                   s=sz,
                   marker=mk,
                   cmap=cmap,
                   linewidth=lw,
                   facecolors=fc,
                   edgecolors=ec,
                   data=df
                   # zorder=zorder
                   )

    def calculate_medoids(df, n=5, ax=None, x_sp=None, y_sp=None):
        if x_sp:
            x_idx = list(df.keys()).index(x_sp)
        if y_sp:
            y_idx = list(df.keys()).index(y_sp)

        X = np.array(df)
        cobj = KMedoids(n_clusters=5).fit(X)
        print(cobj.inertia_)
        sys.exit()

        if ax:
            # seeking plot
            labels = cobj.labels_
            unique_labels = set(labels)
            colors = [
                plt.cm.Spectral(each) for each in np.linspace(0, 1, len(unique_labels))
            ]

            for k, col in zip(unique_labels, colors):
                class_member_mask = labels == k
                xy = X[class_member_mask]
                ax.plot(
                    xy[:, x_idx],
                    xy[:, y_idx],
                    "o",
                    markerfacecolor=tuple(col),
                    markeredgecolor=None,
                    markersize=1,
                )
            ax.plot(
                cobj.cluster_centers_[:, x_idx],
                cobj.cluster_centers_[:, y_idx],
                "o",
                markerfacecolor="black",
                markeredgecolor=None,
                markersize=6,
            )
        return pd.DataFrame(cobj.cluster_centers_, columns=df.keys())

    # ### error chekc arguments
    if not ord_id:
        sys.exit('please supply order id, or list of order ids to be plotted')
    if type(ord_id) == int:
        # ### convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]




    # ### extract species {} from x_sp, y_sp, and z_sp strings
    all_sp = [x_sp, y_sp, z_sp]
    full_call = ' '.join(all_sp)
    es_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_e)\}', full_call))]
    vs_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_v)\}', full_call))]
    if len(vs_sp) == 0:
        # ### need at least one vs
        vs_sp = ['T_cel']

    with camp.working_directory():
        # ### compile usefull plotting information specific to the loaded campaign
        # ### species assciated with this campaign, as per the huffer 3o.
        # elements, aqueous_sp, solids, solid_solutions, gases = determine_species_set(path='huffer/')

        # ### columns contained int eh vs and es table for loaded campaign
        conn = establish_database_connection(camp)
        # vs_col_names = get_column_names(conn, 'vs')
        # es_col_names = get_column_names(conn, 'es')

        # ### grab orders, concatinating the dataframe, 1 record retrieved per
        # ### ord_id.
        df_list = []
        for order in ord_id:

            df = retrieve_combined_records(conn, vs_sp, es_sp, limit=None, ord_id=order,
                                           where=where)
            df_list.append(df)

        conn.close()

        df = pd.concat(df_list)

        # ### process x, y and z, adding new df columns where math is detected
        for s in range(len(all_sp)):
            if '=' in all_sp[s]:
                # ### equation detected, new math column desired
                new_var = all_sp[s].split('=')[0].strip()
                the_math = all_sp[s].split('=')[1].strip()
                all_sp[s] = new_var.replace('{', '').replace('}', '')
                the_math = the_math.replace('{', 'df["').replace('}', '"]')
                df[new_var] = eval(the_math)
            else:
                all_sp[s] = all_sp[s].replace('{', '').replace('}', '')

        # ###  ploting
        font = {'family': 'andale mono', 'size': 8}
        matplotlib.rc('font', **font)
        matplotlib.rcParams['axes.edgecolor'] = '#000000'
        matplotlib.rcParams['axes.linewidth'] = 0.5
        matplotlib.rcParams['axes.labelsize'] = 8
        matplotlib.rcParams['axes.titlesize'] = 8
        matplotlib.rcParams['figure.titlesize'] = 8
        matplotlib.rcParams['xtick.color'] = '#000000'
        matplotlib.rcParams['ytick.color'] = '#000000'
        matplotlib.rcParams['axes.labelcolor'] = '#000000'
        matplotlib.rcParams['legend.frameon'] = False
        matplotlib.rcParams['savefig.transparent'] = transparent

        # calculate_medoids(df, n=5)
        

        # ### process plot
        if z_sp == '':
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5, 9), tight_layout=True)
            ax1.scatter(all_sp[0], all_sp[1], data=df, facecolors='black', marker='o',
                        alpha=0.7, edgecolor=None, s=4, linewidth=0)
            ax1.xlabel(all_sp[0])
            ax1.ylabel(all_sp[1])

        else:
            # ### with z_sp as color
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.5, 9), tight_layout=True)

            hex_list = radar_tools.blu_to_orng
            cmap = get_continuous_cmap(hex_list)
            df = df.sort_values(by=all_sp[2], ascending=False, na_position='first')
            cb = ax1.scatter(all_sp[0], all_sp[1], c=all_sp[2],
                             data=df, cmap=cmap, facecolors='black', marker='o',
                             alpha=0.7, edgecolor=None, s=4, linewidth=0,
                             label=all_sp[2])
            ax1.set_xlabel(all_sp[0])
            ax1.set_ylabel(all_sp[1])

            # yrng = ax1.get_ylim()
            # xrng = ax1.get_xlim()
            # ax1.set_ylim([-10, -4])
            # ax1.set_xlim([-10., -4])

            # ax1.plot([-10000, 10000], [-10000, 10000], color='#fa70ec', linewidth=0.4)

        ###  HOTS field data:
        # dg = pd.read_csv('/Users/tuckerely/39A/CarbonState-Space-Reduction/HOTS/Complete_HOTS_all_stations_2022-02-26.csv')
        # dg.drop(dg[dg['DIC_umol'] == -9].index, inplace=True)
        # dg.drop(dg[dg['pH'] == -9].index, inplace=True)
        # plt_set(ax1, dg, 'pH', 'DIC_umol', 'o', cmap=cmap, fc='None', ec='black', lw=0.2, sz=8)

        fig.colorbar(cb, ax=ax1)

        # ### lower ax is for notes and data
        ax2.axis('off')
        date = time.strftime("%Y-%m-%d", time.gmtime())
        add_text = '\n'.join([f"campaign: {camp.name}", f"order/s: {ord_id}",
                              f"data: {date}", f"n = {len(df)}", f"x = {x_sp}",
                              f"y = {y_sp}", f"z = {z_sp}", 
                              f"sql 'where' claus: {where}",
                              f"notes: {description}"])
        ax2.text(0.0, .9, add_text, ha="left", va='top', fontsize=8)

        fig_name = 'fig/test.png'
        print(f'wrote {fig_name}')
        plt.savefig(fig_name, dpi=400)
