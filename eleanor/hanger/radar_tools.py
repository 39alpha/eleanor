""" radar tools functions used for visualizing vs and es data"""

import os
import re
import sys
import time
import numpy as np
import pandas as pd

import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.colors import LinearSegmentedColormap

# custom packages
from .db_comms import *
from .tool_room import *
from .db_comms import establish_database_connection, retrieve_combined_records
# from .radar_tools import get_continuous_cmap


def Radar(camp, x_sp, y_sp, z_sp, description, ord_id=None, limit=1000, where=None,
          transparent=True, add_analytics=None):
    """
    Plots 3 dimensions from vs and es camp databases
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
    :param ord_id: order number of interest
    :type ord_id: can by one order (as int) or list of orders.
    :param limit: NOT WORKING number of sample points to limit plotting to
        order calls can be very large. Set limit to -1 for all.
    :type limit: int
    :param where: end statement for sql call to limit parameter space search
        region
    :type where: str
    :param transparent: make background on figure transparent?
    :type transparent: boolean
    :param add_analytics: NOT WORKING add mean line and standard deviations's to plot
    :type add_analytics: str
    """

    def plt_set(ax, df, x, y, mk, cmap=None, sz=10, fc='white', ec='black',
                lw=0.5):
        """
        plot subset of marhys database with style (mk=marker, sz=marker size,
            fc=face color, ec=edge color, lw-edge line width)

        The subset plotted is the group (groupby), within the column (col_name) on
            the dataframe df.

        z order refers to the plotting layer relative to other groups which may
            be plotted ont the same ax, which is established outside this
            function prior to its first calling.
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

    # error check arguments
    if not ord_id:
        sys.exit('please supply order id, or list of order ids to be plotted')

    if isinstance(ord_id, int):
        # convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]

    # extract species {} from x_sp, y_sp, and z_sp strings
    all_sp = [x_sp, y_sp, z_sp]
    full_call = ' '.join(all_sp)
    es_sp = [_[:-2] for _ in set(re.findall('\\{([^ ]*_e)\\}', full_call))]
    vs_sp = [_[:-2] for _ in set(re.findall('\\{([^ ]*_v)\\}', full_call))]
    if len(vs_sp) == 0:
        # ### need at least one vs
        vs_sp = ['T_cel']

    with camp.working_directory():
        # compile useful plotting information specific to the loaded campaign
        # species associated with this campaign, as per the huffer 3o.
        # elements, aqueous_sp, solids, solid_solutions, gases = determine_species_set(path='huffer/')

        #  columns contained in the vs and es table for loaded campaign
        conn = establish_database_connection(camp)
        # vs_col_names = get_column_names(conn, 'vs')
        # es_col_names = get_column_names(conn, 'es6')

        # grab orders, concatenating the dataframe, 1 record retrieved per
        # ord_id.
        df_list = []
        for order in ord_id:

            df = retrieve_combined_records(conn, vs_sp, es_sp, limit=None, ord_id=order,
                                           where=where)
            df_list.append(df)

        conn.close()

        df = pd.concat(df_list)

        # process x, y and z, adding new df columns where math is detected
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

        # ploting
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


def hide_current_axis(*args, **kwds):
    plt.gca().set_visible(False)


def group_by_solids(conn, camp_name, ord_id):
    """
    Determine each unique combination of precipitates in a order (ord_id)
    """
    lines = grab_lines(os.path.join(PWD, '{}_huffer'.format(camp_name), 'test.3o'))
    solids = []
    solid_solutions = []

    for _ in range(len(lines)):
        if re.findall('^\n', lines[_]):
            pass

        elif '           --- Saturation States of Pure Solids ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  # signals the end of the solid solutions block
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x

        elif '           --- Saturation States of Solid Solutions ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  # signals the end of the solid solutions block
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x

    all_precip = [_ for _ in solids + solid_solutions]
    # if _ != camp.tm]  # list of all possible precipaiutes, excluing the target mineral, which is in all files.

    # retrieve record of all_precip columns from postgres table 'camp.name', for order # 'ord_id'
    solids_sql = ",".join([f'"{_}"' for _ in all_precip])
    all_rec = retrieve_postgres_record(conn,
                                       'select {} from {}_es where ord = {}'.format(solids_sql, camp_name, ord_id))

    # find unique co-precipitation combinations
    solid_combinations = []  # build list for precipitation combinations

    for _ in all_rec:
        ind = []
        for x in range(len(_)):
            if _[x] > 0:
                ind.append(x)

        # grab index of values over 0,
        solid_combinations.append([all_precip[i] for i in ind])

    # unique mineral co-precipiation occrrances in  order # ord_id
    unique_combinations = [list(x) for x in set(tuple(x) for x in solid_combinations) if list(x) != []] + ['']

    # dictionary of unique mineral combinations, with an int index to reference color
    # this random association between the names and the color, once established here, presists.
    combo_dict = {}
    for _ in range(len(unique_combinations)):
        # z_dict['miner_set_name'] = index
        combo_dict['_'.join(unique_combinations[_])] = _

    return combo_dict


def solid_groups(conn, pwd, camp_name, ord_id, out='assemblages'):
    """
    color plot points based on the solids present, with
    each unique combination of precipiotates getting its own color
    and/or its own unique marker.
    ord_id = order #
    """
    # determine list of all solids in ss columns
    lines = grab_lines(os.path.join(pwd, '{}_huffer'.format(camp_name), 'test.3o'))
    solids = []
    solid_solutions = []

    for _ in range(len(lines)):
        if re.findall('^\n', lines[_]):
            pass
        elif '           --- Saturation States of Pure Solids ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  # signals the end of the solid solutions block
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x
        elif '           --- Saturation States of Solid Solutions ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  # signals the end of the solid solutions block
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x

    all_precip = [_ for _ in solids + solid_solutions]

    if out == 'phases':
        # only the list of solids is wanted
        return all_precip

    if out == 'assemblages':
        # assemblage names are wanted in conjunction with a specifc ord_id in camp_name

        # retrieve ss postgres record
        solids_sql = ",".join([f'"{_}"' for _ in all_precip])
        all_rec = retrieve_postgres_record(conn,
                                           'select {} from {}_es where ord = {}'.format(solids_sql, camp_name, ord_id))

        # find unique co-precipitation combinations
        # build list for precipitation combinations
        solid_combinations = []
        for _ in all_rec:
            ind = []
            for x in range(len(_)):
                if _[x] >= 0:
                    # if affinity >= 0 ie precipitation either happend or
                    # would have if precip was turned on.
                    ind.append(x)
            # grab index of values over 0,
            solid_combinations.append([all_precip[i] for i in ind])
        # unique mineral co-precipiation occrrances in  order # ord_id
        unique_combinations = [list(x) for x in set(tuple(x) for x in solid_combinations) if list(x) != []] + ['']

        # dictionary of unique mineral combinations, with an int index
        # to reference color. This random association between the names
        # and the color, once established here, presists.
        combo_dict = {}
        for _ in range(len(unique_combinations)):
            # z_dict['miner_set_name'] = index
            combo_dict['_'.join(unique_combinations[_])] = _

        # generate color index as the combintion of minerals names precipiated
        z_ind = ['_'.join(_) for _ in solid_combinations]

        return combo_dict


def plt_grid(df, ):

    grid = sns.PairGrid(data=df, color='blue', height=4, layout_pad=1.5)


def check_data0s_loaded():
    """
    what data1 files are currently active in eq3_68.0a/db
    """
    file_name, file_list = read_inputs('data1', 'EQ3_6v8.0a/db', str_loc='prefix')

    suf_list = [_[-3:] for _ in file_list if _.startswith('EQ3_6v8.0a/db/data1')]

    # for _ in suf_list

    plt.figure()
    plt.subplot(111)

    for _ in suf_list:
        t_rng, p_val = data0_TP(_)
        plt.plot(t_rng, [p_val, p_val], color='black', linewidth=0.1)

    plt.xlabel('T (˚C)')
    plt.ylabel('P (bars)')

    plt.title('data0 family coverage\n(∆P = descrete 0.5 bars)\n∆T = 7C contineuous')

    plt.show()


def get_continuous_cmap(hex_list, float_list=None):
    # https://towardsdatascience.com/beautiful-custom-colormaps-with-matplotlib-5bab3d1f0e72
    """
    Create and return a color map that can be used in heatmap figures. If :code:`float_list` is
    not provided, then the color map graduates linearly between each color in :code:`hex_list`.
    If :code:`float_list` is provided, then each each color in :code:`hex_list` is mapped to the
    respective location in :code:`float_list`.

    :param hex_list: hex-code strings
    :type hex_list: list
    :param float_list: Floating-point values between 0 and 1 with the same length as
                        :code:`hex_list`. Must start with 0 and end with 1.
    :type float_list: list

    :return: A color map
    :rtype: matplotlib.colors.LinearSegmentedColormap
    """

    rgb_list = [rgb_to_dec(hex_to_rgb(i)) for i in hex_list]
    if isinstance(float_list, list):
        float_list = list(np.linspace(0, 1, len(rgb_list)))

    cdict = dict()
    for num, col in enumerate(['red', 'green', 'blue']):
        col_list = [[float_list[i], rgb_list[i][num], rgb_list[i][num]] for i in range(len(float_list))]
        cdict[col] = col_list
    cmp = matplotlib.colors.LinearSegmentedColormap('my_cmp', segmentdata=cdict, N=256)
    return cmp


def hex_to_rgb(value):
    '''
    Converts hex to rgb colours
    value: string of 6 characters representing a hex colour.
    Returns: list length 3 of RGB values'''
    value = value.strip("#")  # removes hash symbol if present
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))


def rgb_to_dec(value):
    '''
    Converts rgb to decimal colours (i.e. divides each value by 256)
    value: list (length 3) of RGB values
    Returns: list (length 3) of decimal values'''
    return [v / 256 for v in value]


color_dict = {'1': ['#E76F51', '#264653', '#2A9D8F', '#F4A261', '#E9C46A', '#100B00', '#A5CBC3',
                    '#3B341f', '#2F004F'],
              '2': ['#ff0000', '#ffa500', '#ffff00', '#008000', '#0000ff', '#4b0082', '#000000'],
              '3': ['#7CEA9C', '#F433AB', '#2E5EAA', '#593959', '#F0C808', '#DD1C1A', '#F05365',
                    '#FF9B42', '#B2945B', '#000000', '#FF0000', '#FFA500', '#FFFF00', '#008000',
                    '#0000FF', '#4B0082'],
              '4': ['#79baf7', '#ff0000', '#000000']
              }

BIG_PALETTE1 = ['#7CEA9C', '#F433AB', '#2E5EAA', '#593959', '#F0C808', '#DD1C1A', '#F05365',
                '#FF9B42', '#B2945B', '#000000', '#FF0000', '#FFA500', '#FFFF00', '#008000',
                '#0000FF', '#4B0082']

BIG_PALETTE2 = ['#ff0000', '#4F8BEB']

BLU_GREN = ['#7CEA9C', '#00B2CA']

BLU_PNK = ['#F433AB', '#00B2CA']

RAINBOW_BLK = LinearSegmentedColormap.from_list("mycmap", ["#020004", "#75228f", "#3e53d2",
                                                           "#4eb01f", "#ffd805", "#fd9108",
                                                           "#dd2823"])

RAINBOW = LinearSegmentedColormap.from_list("mycmap", ["#75228f", "#3e53d2", "#4eb01f",
                                                       "#ffd805", "#fd9108", "#dd2823"])

blu_to_orng = ["#47eaff", "#2bbae0", "#2f8fd1", "#3363c2", "#3a0ca3",
               "#9d2a52", "#ff4800", "#ff7900", "#ffa224", "#ffcb47"]
