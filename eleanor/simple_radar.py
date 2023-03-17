# ###
# ### Radar
# ### Simple visualization of the orders run by the helmsman
# ### 39A Team 0.

import os
import matplotlib
import re
import sys
import time
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn_extra.cluster import KMedoids
from scipy.stats import kde

# ### custom packages

from .hanger.db_comms import establish_database_connection, retrieve_combined_records
from .hanger.db_comms import get_column_names
from .hanger import radar_tools
from .hanger.data0_tools import determine_species_set
from .hanger.radar_tools import get_continuous_cmap


def Radar(camp, x_sp, y_sp, z_sp='#000000', thought_process='', x_rng=None,
          y_rng=None, ord_id=None, limit=None, where=None, transparent=False,
          out_path='.'):
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
    :param x_rng: range on x_axis (min, max)
    :type x_rng: list of floats
    :param y_rng: range on y_axis (min, max)
    :type y_rng: list of floats
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
    """
    print(x_sp)
    print(y_sp)
    print(z_sp)
    # ###  ploting
    font = {'family': 'andale mono', 'size': 10}
    matplotlib.rc('font', **font)
    matplotlib.rcParams['axes.edgecolor'] = '#000000'
    matplotlib.rcParams['axes.linewidth'] = 0.5
    matplotlib.rcParams['axes.labelsize'] = 8
    matplotlib.rcParams['axes.titlesize'] = 12
    matplotlib.rcParams['figure.titlesize'] = 8
    matplotlib.rcParams['xtick.color'] = '#000000'
    matplotlib.rcParams['ytick.color'] = '#000000'
    matplotlib.rcParams['axes.labelcolor'] = '#000000'
    matplotlib.rcParams['legend.frameon'] = False
    matplotlib.rcParams['savefig.transparent'] = transparent


    def print_where(where):
        if where:
            a = where.split(' ')
            for _ in list(range(5, len(a)))[::5]:
                a.insert(_, '\n.                  ')
            return ' '.join(a) + '\n'
        else:
            return where

    def plt_set(ax, df, x, y, mk, cmap=None, sz=10, fc='white', ec='black', lw=0.5):
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

    def process_eq(equation):
        """
        Extract species {} from variables that include an 'equation'
        """
        new_sp = equation.split('=')[1].strip()
        sql_columns = re.findall('\{(.*?)\}', new_sp)
        return sql_columns

    def solve_eq(df, eq):
        """
        Processing equations in the called species, adding new species to df.
        """
        new_var = s.split('=')[0].strip()
        the_math = s.split('=')[1].strip()
        new_var = new_var.replace('{', '').replace('}', '')
        the_math = the_math.replace('{', 'df["').replace('}', '"]')
        df[new_var] = eval(the_math)
        if re.findall('[<>]|[<>]=|==|!=', z_sp):
            df.loc[df[new_var] == True, new_var] = "#ff0000"
            df.loc[df[new_var] == False, new_var] = "#79baf7"
        return df

    if type(ord_id) == int:
        # ### convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]

    # ### process species
    add_sp = []
    math_sp = []
    x_plt = x_sp.split('=')[0].strip()
    if '=' in x_sp:
        add_sp = add_sp + process_eq(x_sp)
        math_sp = math_sp + [x_sp]
    else:
        add_sp = add_sp + [x_plt]

    y_plt = y_sp.split('=')[0].strip()
    if '=' in y_sp:
        add_sp = add_sp + process_eq(y_sp)
        math_sp = math_sp + [y_sp]
    else:
        add_sp = add_sp + [y_plt]

    if re.findall('^\#', z_sp):
        fig_name = f'fig/{x_plt}_{y_plt}.png'

    else:
        z_plt = z_sp.split('=')[0].strip()
        if '=' in z_sp:
            add_sp = add_sp + process_eq(z_sp)
            math_sp = math_sp + [z_sp]
        else:
            add_sp = add_sp + [z_plt]
        fig_name = f'fig/{x_plt}_{y_plt}_{z_plt}.png'

    es3_cols = [_[:-3] for _ in set(add_sp) if '_e3' in _]
    es6_cols = [_[:-3] for _ in set(add_sp) if '_e6' in _]
    vs_cols = [_[:-2] for _ in set(add_sp) if '_v' in _]

    if 'ord' not in vs_cols:
        vs_cols = ['ord'] + vs_cols

    with camp.working_directory():
        # ### grab orders, concatinating the dataframe, 1 record retrieved per
        # ### ord_id.
        if ord_id:
            df_list = []
            for order in ord_id:
                df = retrieve_combined_records('.', vs_cols, es3_cols, es6_cols,
                                               limit=limit, where=where, ord_id=order)
                df_list.append(df)
            df = pd.concat(df_list)
        else:
            df = retrieve_combined_records('.', vs_cols, es3_cols, es6_cols,
                                           limit=limit, where=where)

        print(len(df))
        # ### Add new df columns where math is detected
        for s in math_sp:
            df = solve_eq(df, s)

        # ### process plot
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5, 9), tight_layout=True)  # figsize=(5, 9)

        if re.findall('^#', z_sp):
            ax1.scatter(x_plt, y_plt, data=df, facecolors=z_sp,
                        marker='o', alpha=1, edgecolor=None, s=3, linewidth=0)

        else:
            # df = df.sort_values(by=z_plt, ascending=False,
            #                     na_position='first'
            #                     )
            df = df.sample(frac=1)

            if re.findall('[<>]|[<>]=|==|!=', z_sp):
                cb = ax1.scatter(x_plt, y_plt, c=z_plt,
                                 data=df, marker='o', alpha=1, edgecolor=None,
                                 s=2, linewidth=0, label=z_plt
                                 )
            else:
                hex_list = radar_tools.blu_to_orng
                cmap = get_continuous_cmap(hex_list)
                cb = ax1.scatter(x_plt, y_plt, c=z_plt,
                                 data=df, cmap=cmap, facecolors='black',
                                 marker='o', alpha=1, edgecolor=None,
                                 s=2, linewidth=0, label=z_plt
                                 )
                fig.colorbar(cb, ax=ax1)

        if x_rng:
            ax1.set_xlim(x_rng)
        if y_rng:
            ax1.set_ylim(y_rng)
        ax1.set_xlabel(x_plt)
        ax1.set_ylabel(y_plt)
        ax2.axis('off')
        date = time.strftime("%Y-%m-%d", time.gmtime())
        add_text = '\n'.join([f"campaign: {camp.name}",
                              f"data: {date}", f"n = {len(df)}",
                              f"thouhts: {print_where(thought_process)}",
                              f"x = {x_sp}",
                              f"y = {y_sp}",
                              f"z = {z_sp}",
                              f"sql 'where' claus: {print_where(where)}",
                              f"sql limit: {limit}"
                              ])
        ax2.text(0.0, .9, add_text, ha="left", va='top', fontsize=6)
        print(f'wrote {fig_name}')
        plt.savefig(fig_name, dpi=600)


