""" radar tools functions used for visualizing vs and es data"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap


def get_continuous_cmap(hex_list, float_list=None):
    """
    Create and return a color map that can be used in heatmap figures. If :code:`float_list` is
    not provided, then the color map graduates linearly between each color in :code:`hex_list`.
    If :code:`float_list` is provided, then each each color in :code:`hex_list` is mapped to the
    respective location in :code:`float_list`.

    See: https://towardsdatascience.com/beautiful-custom-colormaps-with-matplotlib-5bab3d1f0e72

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

    cdict: dict = {}
    for num, col in enumerate(['red', 'green', 'blue']):
        col_list = [[float_list[i], rgb_list[i][num], rgb_list[i][num]] for i in range(len(float_list))]
        cdict[col] = col_list
    cmp = LinearSegmentedColormap('my_cmp', segmentdata=cdict, N=256)
    return cmp


def hex_to_rgb(value):
    '''
    Converts hex to rgb colours
    value: string of 6 characters representing a hex colour.
    Returns: list length 3 of RGB values'''
    value = value.strip("#")
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))


def rgb_to_dec(value):
    '''
    Converts rgb to decimal colours (i.e. divides each value by 256)
    value: list (length 3) of RGB values
    Returns: list (length 3) of decimal values'''
    return [v / 256 for v in value]


color_dict = {
    '1': ['#E76F51', '#264653', '#2A9D8F', '#F4A261', '#E9C46A', '#100B00', '#A5CBC3', '#3B341f', '#2F004F'],
    '2': ['#ff0000', '#ffa500', '#ffff00', '#008000', '#0000ff', '#4b0082', '#000000'],
    '3': [
        '#7CEA9C', '#F433AB', '#2E5EAA', '#593959', '#F0C808', '#DD1C1A', '#F05365', '#FF9B42', '#B2945B', '#000000',
        '#FF0000', '#FFA500', '#FFFF00', '#008000', '#0000FF', '#4B0082'
    ],
    '4': ['#79baf7', '#ff0000', '#000000']
}

BIG_PALETTE1 = [
    '#7CEA9C', '#F433AB', '#2E5EAA', '#593959', '#F0C808', '#DD1C1A', '#F05365', '#FF9B42', '#B2945B', '#000000',
    '#FF0000', '#FFA500', '#FFFF00', '#008000', '#0000FF', '#4B0082'
]

BIG_PALETTE2 = ['#ff0000', '#4F8BEB']

BLU_GREN = ['#7CEA9C', '#00B2CA']

BLU_PNK = ['#F433AB', '#00B2CA']

RAINBOW_BLK = LinearSegmentedColormap.from_list(
    "mycmap", ["#020004", "#75228f", "#3e53d2", "#4eb01f", "#ffd805", "#fd9108", "#dd2823"])

RAINBOW = LinearSegmentedColormap.from_list("mycmap",
                                            ["#75228f", "#3e53d2", "#4eb01f", "#ffd805", "#fd9108", "#dd2823"])

blu_to_orng = [
    "#47eaff", "#2bbae0", "#2f8fd1", "#3363c2", "#3a0ca3", "#9d2a52", "#ff4800", "#ff7900", "#ffa224", "#ffcb47"
]
