"""
 data0 analysis tools
 Tucker Ely
 April 8th 2020
"""
import math
import re
import pandas as pd

from os.path import dirname, abspath, realpath, join

from .tool_room import grab_str


DATA_PATH = join(abspath(join(dirname(realpath(__file__)), '..')), 'data')
SLOP_DF = pd.read_csv(join(DATA_PATH, 'test_worm_data.csv'), index_col=0)

def species_info(sp):
    """
    in:
        species name in worm slop file 'SLOP_DF'
    out:
        dict['ele'] = sto containing elements in species
    """
    comp_dict = {}
    formula_ox = SLOP_DF['formula_ox'][sp]
    for _ in formula_ox.split():
        front = (re.sub(r'[-+][0-9]{0,2}', '', _))
        if re.findall('^[A-Za-z]', front):
            front = '1{}'.format(front)
        sto, ele = re.findall(r'([0-9+\.]{1,}|[A-Za-z]+)', front)
        comp_dict[ele] = sto
    return comp_dict


def determine_ele_set(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded elements
        :param path: campaign huffer path to test.3o file
        :type path: str
            :return: list of elements

    """
    elements = []
    grab_ele = False
    with open('{}test.3o'.format(path), 'r') as f:
        for line in f:
            if '           --- Elemental Composition of the Aqueous Solution ---' in line:
                grab_ele = True
            elif grab_ele and re.findall('^     [A-Z]', line):

                if float(line.split()[1]) == 0.0:
                    # element not loaded (ie. Cl). this shows up in
                    # the eq3 element set even if set to 0.
                    pass
                else:
                    elements.append(grab_str(line, 0))
            elif '--- Numerical Composition of the Aqueous Solution ---' in line:
                return [_ for _ in elements if _ not in ['O', 'H']]


def determine_species_set(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded species
        separated into their groups (elements, aqueous, solids, solid solutions, and gases)
        :param path: campaign huffer path to test.3o file

        :return:
            list of elements,
            list of aqueous species,
            list of solids
            list of solid solutions
            list of gases

    """
    suppress = []

    elements = []
    aqueous_sp = []
    solids = []
    solid_solutions = []
    gases = []

    with open('{}test.3o'.format(path), 'r') as f:
        lines = f.readlines()

        # gather suppress info from near the top of the
        for i in range(len(lines)):
            if ' * Alter/suppress options' in lines[i]:
                # number of suppression options
                supp_n = int(lines[i + 1].split()[-1])
                # print(supp_n)
                for j in range(1, supp_n + 1):
                    suppress.append(lines[i + 2 * j][12:].strip())
                break

        # search for all other info from teh bottom of the file
        for i in range(len(lines) - 1, 0, -1):
            # find the beginning of the print section for the final system composition.
            if ' Done. Hybrid Newton-Raphson iteration converged in ' in lines[i]:
                break

        # now count forward in lines against to read the system composition
        while i < len(lines):

            if re.findall('^\n', lines[i]):
                i += 1

            elif '           --- Elemental Composition of the Aqueous Solution ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    ele = lines[i][:13].strip()
                    if ele not in ['O', 'H']:
                        if float(lines[i].split()[1]) == 0.0:
                            # element not loaded (ie. Cl). this shows up in
                            # the eq3 element set even if set to 0.
                            pass
                        else:
                            elements.append(ele)
                        i += 1
                    else:
                        i += 1

            elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    aqueous_sp.append(lines[i][:26].strip())
                    i += 1

                # this fictive aq species shows up in the aqueous block
                aqueous_sp.remove('O2(g)')

            elif '           --- Saturation States of Pure Solids ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    solids.append(lines[i][:26].strip())
                    i += 1

            elif '--- Saturation States of Solid Solutions ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    solid_solutions.append(lines[i][:26].strip())
                    i += 1

            elif '--- Fugacities ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    gases.append(lines[i][:26].strip())
                    i += 1

                break

            else:
                i += 1

    # without knowing which lists contain the suppressions, they all must be searched
    elements = [_ for _ in elements if _ not in suppress]
    aqueous_sp = [_ for _ in aqueous_sp if _ not in suppress]
    solids = [_ for _ in solids if _ not in suppress]
    solid_solutions = [_ for _ in solid_solutions if _ not in suppress]
    gases = [_ for _ in gases if _ not in suppress]

    return elements, aqueous_sp, solids, solid_solutions, gases


def determine_loaded_sp(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded species,
        which includes all non-basis blocks from the data0 (aq solids, gases, etc.)
        :param path: campaign huffer path to test.3o file
        :return: list of loaded species

    """
    loaded_sp = []
    with open('{}test.3o'.format(path), 'r') as f:
        lines = f.readlines()
        grab_loaded_sp = False
        for _ in range(len(lines)):
            # ## search for loaded species.
            # These only appear if verbose 'v' is set with local_3i.write() above
            if ' --- Listing of Species and Reactions ---' in lines[_]:
                grab_loaded_sp = True
            elif ' - - BEGIN ITERATIVE CALCULATIONS  - - - ' in lines[_]:
                break
            elif grab_loaded_sp and '------------------' in lines[_]:
                # ## the two options below avoid the 'BEGIN ITERATIVE . .'
                # ## which is also caught with the above string.
                if '1.000' in lines[_ + 2]:
                    # ## exclude basis species
                    # ## grab full string (with spaces) after the stoichiometry
                    # ## this correctly differentiates solid solution end-members
                    # ## from their stand alone counterparts ie: 'CA-SAPONITE'
                    # ## vs 'CA-SAPONITE (SAPONITE)'
                    loaded_sp.append(lines[_ + 2].split('1.000  ')[-1].strip())
                elif 'is a strict' in lines[_ + 2]:
                    # ## grabs basis species
                    loaded_sp.append(
                        lines[_ + 2].split(' is a strict ')[0].strip())

        # ## O2(g) shows up as a strict basis species, and again with the gasses
        # ## so its basis form is removed here. Also, H2O shows up 2 times, and
        # ## regardless is separately tracked via the aH2O variable.
        loaded_sp = [_ for _ in loaded_sp if _ != 'H2O' and _ != 'O2(g)']

        # alter loaded_sp to reflect correct search names required for 6o
        aq_and_s = [_ for _ in loaded_sp if ' (' not in _]
        ss_and_gas = [_ for _ in loaded_sp if ' (' in _]
        gas = [_.split(' (')[0] for _ in ss_and_gas if '(Gas)' in _]
        ss = [_.split(' (')[1].strip(')(') for _ in ss_and_gas if '(Gas)' not in _]

        sp_names = aq_and_s + gas + list(set(ss))

    return sp_names


# def basis_to_ele_dict(slopfile):
#     """
#         Determine species-element relationships via a WORM slop.csv file.
#         :param slop_file: campaign huffer path of test.3o
#         :return: list of loaded species
#     """
#     df = pd.read_csv('/Users/tuckerely/NPP_dev/0_slop_OBIGT_Data0/{}'.format(slopfile),
#                      index_col=0)
#     basis_df = df[df['tag'] == 'basis']


def data0_suffix(T, P):
    """
    organizes the construction of multiple data0 files, each with a small t range, at constant
    pressure. The family of data0s this function refers to, are built one at a time by Grayson's
    worm code, and then stored appropriately in the the db folder. They are intended for spot
    calculations, and not suitable for 6i runs which explore dT, as each only covers a small T
    range.

    T, P = 3i/6i file T and P
    return appropriate data0 suffix

    T is indicated by the first of the 3 suffix characters.
    P is indicated by the second two
    """

    char = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b',
            'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
            'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.join([i, j]))
    # ## by using 'floor' below. the correct file is returned for T near the file cutoffs
    # ## for example, T = 7.99 (P=1), does in fact call the data0.002 file. The data0 files
    # ## themselves overlap in their lowest and highest values for consecutive files.
    t_char = char[math.floor(T / data0_system_T_interval)]
    tp_char = '{}{}'.format(t_char, dualchar[math.floor(P / data0_system_P_interval)])

    return tp_char


def data0_TP(suffix):
    """
    reutrn T/P range of a data0 file given its suffix
    """
    t = suffix[0]
    p = suffix[1:]
    char = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b',
            'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
            'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    t_pos = char.index(t)
    t_rng = [t_pos * data0_system_T_interval, t_pos * data0_system_T_interval + 7]
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.join([i, j]))

    p_pos = dualchar.index(p)
    p_val = p_pos * data0_system_P_interval

    return t_rng, p_val
