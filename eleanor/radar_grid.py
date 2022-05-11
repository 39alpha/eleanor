# ###
# ### Radar
# ### Controls the visualization fo the orders run by the helmsman
# ### Tucker Ely, Douglas G. Moore, Cole Mathis

import math
import matplotlib
import re
import sys
import time
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# ### custom packages
from .hanger.db_comms import establish_database_connection, retrieve_combined_records
from .hanger.db_comms import get_column_names
from .hanger import radar_tools
from .hanger.data0_tools import determine_species_set
from .hanger.radar_tools import get_continuous_cmap
from .hanger.radar_tools import hide_current_axis
from .hanger.radar_tools import color_dict


def Radar_Grid(camp, vars, color_condition, description, ord_id=None, limit=1000, where=None, 
               add_analytics=False):
    """
    Plots 3 dimenions from vs and es camp databases
    :param camp: campaign
    :type camp: Class instance
    :param vars: es, vs, and math variables to become grid axes
    :type vars: list of strings
    :param color_condition: ['type', 'condition']
    :type color_condition: [str, str/list]
        for example:
            ['grid', ['CO2_e', 'Ca_e']] cresate a 3 by 3 color grid on CO2 and Ca.
            ['color', 'black'].         makes all markers black.
            ['solid', '{CO2_e} > -2.5'] bimodal (false: red, ture: blue) for condition.
            ['order'].  categorize on order
    :param description: notes on data to show beneath image
    :type description: str
    :param ord_id: order number of interest
    :type ord_id: can by one order (as int) or list of orders.
    :param limit: UNBUILT numebr of sample points to limit plotting to
        order calls can be very large. Set limit to -1 for all.
    :type limit: int
    :param where: end statement for sql call to limit parameter space search
        region
    :type where: str
    :param add_analytics: UNBUILT add mean line and sd's to plot
    :type add_analytics: str
    """
    # ### error check arguments
    if not ord_id:
        sys.exit('check docstring for arguments')
    if type(ord_id) == int:
        # ### convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]

    all_sp = vars
    full_call = ' '.join(all_sp)
    es_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_e)\}', full_call))]
    vs_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_v)\}', full_call))]

    # ### extract species {} from x_sp, y_sp, and z_sp strings
    if color_condition[0] in ['solid', 'species']:
        # ### capture extra species stached in color conditions, so that they appear in df
        col_es = [_[:-2] for _ in set(re.findall('\{([^ ]*_e)\}', color_condition[1]))]
        col_vs = [_[:-2] for _ in set(re.findall('\{([^ ]*_v)\}', color_condition[1]))]
        es_sp = list(set(es_sp + col_es))
        vs_sp = list(set(vs_sp + col_vs))

    if color_condition[0] == 'ord':
        vs_sp = list(set(vs_sp + ['ord']))

    if len(vs_sp) == 0:
        # ### need at least one vs
        vs_sp = ['T_cel']

    with camp.working_directory():
        # ### compile usefull plotting information specific to the loaded campaign
        # ### species assciated with this campaign, as per the huffer 3o.
        elements, aqueous_sp, solids, solid_solutions, gases = determine_species_set(path='huffer/')

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
        df = pd.concat(df_list)
        conn.close()

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

        # ### process color choice
        if color_condition[0] == 'grid':
            df['x_coarse'] = pd.qcut(df[color_condition[1][0]], 3, labels=['a', 'b', 'c'])
            df['y_coarse'] = pd.qcut(df[color_condition[1][1]], 3, labels=['a', 'b', 'c'])
            # ### all unique combinations of x_coarse and y_coarse
            df['color'] = df['x_coarse'].astype(str) + df['y_coarse'].astype(str)
            df.drop(['x_coarse', 'y_coarse'], axis=1, inplace=True)
            palette = {
                 'ac': "#f7e14f", 'bc': "#ff8c00", 'cc': "#e60000",  # hot tones  (light to dark)
                 'ab': "#c2c0c0", 'bb': "#5e5d5d", 'cb': "#000000",  # greyscale  (light to dark)
                 'aa': "#3ad4f2", 'ba': "#146ee3", 'ca': "#1c0069"  # cold tones (light to dark)
                 }
        elif color_condition[0] == 'ord':
            palette = dict(zip(ord_id, color_dict['5'][:len(ord_id)]))
            print(palette)
            df['color'] = df['ord_v']

        elif color_condition[0] == 'color':
            # palette = {True: color_condition[1]}
            # df['color'] = True
            df['color'] = color_condition[1]

        elif color_condition[0] in ['species', 'solid']:
            the_math = color_condition[1].replace('{', 'df["').replace('}', '"]')
            df['color'] = eval(the_math)
            palette = {True: "#ff0000", False: "#79baf7"}


        # ### PMH
        df['color'] = df['color'].mask((df['magnetite_e'] > 0) & (df['hematite_e'] > 0), '#EA1515')

        # ### PM
        df['color'] = df['color'].mask((df['magnetite_e'] > 0) & (df['hematite_e'] < 0), '#9A28CF')

        # ### PH
        df['color'] = df['color'].mask((df['magnetite_e'] < 0) & (df['hematite_e'] > 0), '#3ACF28')

        # ### blue passes through as Py only

        # df.drop(['magnetite_e', 'hematite_e'], axis=1, inplace=True)

        # ### gitd plots all_sp as axes, which does nto include any speicexs required to determine color
        grid = sns.PairGrid(data=df, hue='color', vars=all_sp,  # hue_order=[False, True],
                            # palette=palette,
                            height=4,
                            layout_pad=1.5)
        # grid.map_upper(sns.kdeplot,  alpha=0.6, levels=10, thresh=0.05, linewidth=0.1)
        grid.map_lower(plt.scatter, alpha=0.5, edgecolor=None, s=3, linewidth=0)
        grid.map_diag(plt.hist, bins=40)
        # grid.map_diag(sns.kdeplot, fill=False, alpha=0.2, levels=1, thresh=0.05)      # conditions for test 6 and first big Py plot
        grid.map_upper(hide_current_axis)

        # ### build local labels for every plot
        col_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L',
                     'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X',
                     'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH',
                     'AI', 'AJ', 'AK']

        xlabels, ylabels, xticks, yticks = [], [], [], []
        for ax in grid.axes[-1, :]:
            xlabel = ax.xaxis.get_label_text()
            xlabels.append(xlabel)
            xtick = ax.get_xticklabels()
            xticks.append(xtick)

        for ax in grid.axes[:, 0]:
            ylabel = ax.yaxis.get_label_text()
            ylabels.append(ylabel)
            ytick = ax.get_yticklabels()
            yticks.append(ytick)

        for i in range(len(xlabels)):
            for j in range(len(ylabels)):
                if i != j:
                    grid.axes[j, i].xaxis.set_label_text(xlabels[i])
                    # grid.axes[j, i].set_xticklabels(xticks[i])
                    grid.axes[j, i].yaxis.set_label_text(ylabels[j])
                    # grid.axes[j, i].set_yticklabels(yticks[j])
                    yrng = grid.axes[j, i].get_ylim()
                    xrng = grid.axes[j, i].get_xlim()
                    grid.axes[j, i].plot([-10000, 10000], [-10000, 10000], color='#fa70ec', linewidth=0.4)

                    # ### set 0-lines for solids to make it easier to differentiate affinity from moles
                    if xlabels[i][:-2] in solids or solid_solutions:
                        grid.axes[j, i].plot([0, 0], [-100, 100], color='#fa70ec', linewidth=0.4)
                    if ylabels[j][:-2] in solids or solid_solutions:
                        grid.axes[j, i].plot([-100, 100], [0, 0], color='#fa70ec', linewidth=0.4)
                    grid.axes[j, i].set_ylim(yrng)
                    grid.axes[j, i].set_xlim(xrng)

                if i == j:
                    grid.axes[j, i].text(0.1, 0.5, xlabels[i], fontsize=30, fontweight='bold',
                                         horizontalalignment='left',
                                         verticalalignment='center',
                                         transform=grid.axes[j, i].transAxes)

                # ### col numbers
                if j == len(ylabels) - 1:
                    grid.axes[j, i].text(0.5, -0.3, str(i), fontsize=60, fontweight='bold',
                                         fontfamily='Arial Black',
                                         horizontalalignment='center',
                                         verticalalignment='top',
                                         transform=grid.axes[j, i].transAxes)
                # ### row numbers
                if i == 0:
                    grid.axes[j, i].text(-0.3, 0.5, col_names[j], fontsize=60, fontweight='bold',
                                         fontfamily='Arial Black',
                                         horizontalalignment='right', verticalalignment='center',
                                         transform=grid.axes[j, i].transAxes)

        plt.subplots_adjust(top=0.96)
        plt.subplots_adjust(bottom=0.1)
        plt.subplots_adjust(left=0.1)

        date = time.strftime("%Y-%m-%d", time.gmtime())
        add_text = '\n'.join([f"campaign: {camp.name}      order/s: {ord_id}       n = {len(df)}       date: {date}",
                              f"sql 'where' constraint: {where}          color constraint: {color_condition}",
                              f"notes: {description}"])
        grid = grid.fig.suptitle(add_text, fontsize=20)
        fig_name = 'fig/test_grid.png'
        print(f'wrote {fig_name}')
        plt.savefig(fig_name, dpi=400)
