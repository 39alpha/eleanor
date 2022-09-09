""" radar tools functions used for visualizing vs and es data"""
import os
import re
import time
import numpy as np
import pandas as pd

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# custom packages
from .db_comms import establish_database_connection, retrieve_combined_records, retrieve_records

def Radar(camp, x_sp, y_sp, z_sp,
          savename=None,notes="",
          ord_id=None, limit=1000,
          where=None, transparent=True):
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
    :param notes: notes on data to show beneath image
    :type notes: str
    :param ord_id: order number(s) of interest
    :type ord_id: can by one order (as int) or list of orders.
    :param limit: number of sample points per order to limit plotting to
        order calls can be very large.
    :type limit: int
    :param where: end statement for sql call to limit parameter space search
        region
    :type where: str
    :param transparent: make background on figure transparent?
    :type transparent: boolean
    :param savename: Name of file for saving (stays in the campaign/fig/) directory.
                    (.jpeg, .png, .svg supported)
    :type savename: str
    """
    # plotting Parameters
    font = {'size': 11}
    matplotlib.rc('font', **font)
    matplotlib.rcParams['axes.edgecolor'] = '#000000'
    matplotlib.rcParams['axes.linewidth'] = 0.5
    matplotlib.rcParams['axes.labelsize'] = 10
    matplotlib.rcParams['axes.titlesize'] = 10
    matplotlib.rcParams['figure.titlesize'] = 10
    matplotlib.rcParams['xtick.color'] = '#000000'
    matplotlib.rcParams['ytick.color'] = '#000000'
    matplotlib.rcParams['axes.labelcolor'] = '#000000'
    matplotlib.rcParams['legend.frameon'] = False
    matplotlib.rcParams['savefig.transparent'] = transparent

    # Handle optional arguments
    all_orders=False
    if type(ord_id) == int:
        # convert to list of 1, if a single order number is supplied
        ord_id = [ord_id]
    if ord_id is None:
        all_orders = True

    # extract species {} from x_sp, y_sp, and z_sp strings
    all_sp = [x_sp, y_sp, z_sp]
    full_call = ' '.join(all_sp)
    es_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_e)\}', full_call))]
    vs_sp = [_[:-2] for _ in set(re.findall('\{([^ ]*_v)\}', full_call))]
    if len(vs_sp) == 0:
        # need at least one vs
        vs_sp = ['T_cel']

    with camp.working_directory():
        # columns contained in the vs and es table for loaded campaign
        conn = establish_database_connection(camp)
        # if we're getting all orders get the list of unique order IDs
        if all_orders:
            ord_ids = retrieve_records(conn, "SELECT id FROM orders")[0]
            ord_id = [o for o in ord_ids]
        # grab orders, concatenating the DataFrame, 1 record retrieved per
        # order
        df_list = []
        for order in ord_id:
            print(vs_sp, es_sp)
            df = retrieve_combined_records(conn, vs_sp, es_sp, 
                                           limit=limit, 
                                           ord_id=order,
                                           where=where)
            df_list.append(df)

        conn.close()

        df = pd.concat(df_list)

        # process x, y and z, adding new df columns where math is detected
        for s in range(len(all_sp)):
            if '=' in all_sp[s]:
                # equation detected, new math column desired
                new_var = all_sp[s].split('=')[0].strip()
                the_math = all_sp[s].split('=')[1].strip()
                all_sp[s] = new_var.replace('{', '').replace('}', '')
                the_math = the_math.replace('{', 'df["').replace('}', '"]')
                df[new_var] = eval(the_math)
            else:
                all_sp[s] = all_sp[s].replace('{', '').replace('}', '')

        # process plot
        if z_sp == '':
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(3.5, 5), tight_layout=True)
            ax1.scatter(all_sp[0],
                        all_sp[1],
                        data=df,
                        facecolors='black',
                        marker='o',
                        alpha=0.7,
                        edgecolor=None,
                        s=4,
                        linewidth=0)
            ax1.xlabel(all_sp[0])
            ax1.ylabel(all_sp[1])

        else:
            # with z_sp as color
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(3.5, 5), tight_layout=True)
            hex_list = BLU_TO_ORG
            cmap = get_continuous_cmap(hex_list)
            df = df.sort_values(by=all_sp[2], ascending=False, na_position='first')
            cb = ax1.scatter(all_sp[0],
                             all_sp[1],
                             c=all_sp[2],
                             data=df,
                             cmap=cmap,
                             facecolors='black',
                             marker='o',
                             alpha=0.7,
                             edgecolor=None,
                             s=4,
                             linewidth=0,
                             label=all_sp[2])
            print(all_sp[0])
            ax1.set_xlabel(all_sp[0])
            ax1.set_ylabel(all_sp[1])

        fig.colorbar(cb, ax=ax1)

        # lower ax is for notes and data
        ax2.axis('off')
        date = time.strftime("%Y-%m-%d", time.gmtime())
        order_string = " ".join([str(o) for o in ord_id])
        all_text = [f"campaign: {camp.name}",
                    f"order(s): {order_string}",
                    f"date: {date}",
                    f"n = {len(df)}",
                    f"x: {x_sp}",
                    f"y: {y_sp}",
                    f"color: {z_sp}"]
        if where:
            all_text.append(f"sql 'where' clause: {where}")
        all_text.append(f"notes: {notes}")
        add_text = '\n'.join(all_text)

        ax2.text(0.0, 0.9, add_text, ha="left", va='top', fontsize=10)
        if not savename:
            savename = "plot.svg"
        fig_name = os.path.join('fig', savename)
        # print(f'wrote {fig_name}')
        plt.savefig(fig_name, dpi=400)

def hide_current_axis(*args, **kwds):
    plt.gca().set_visible(False)

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
    if type(float_list) != list:
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



# ###############################  Color ################################
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
BLU_TO_ORG = ["#47eaff", "#2bbae0", "#2f8fd1", "#3363c2", "#3a0ca3",
                 "#9d2a52", "#ff4800", "#ff7900", "#ffa224", "#ffcb47"]