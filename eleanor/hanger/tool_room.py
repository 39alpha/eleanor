""" The tool room module contains functions and variables
related to running and manipulating EQ3/6.
This file is my attempt to stremaline the development
process, as the functions contained herein are
commonily duplicated between projects. """

# tool_room
# Developed by Tucker Ely
# 2018-
# General EQ3/6 dependencies
# Adapted by 39A 2021

import os
import sys
import re
import numpy as np
import hashlib

from enum import IntEnum

from .constants import *  # noqa (F403)

from eleanor.exceptions import RunCode, EleanorFileException

# #################################################################
# ########################  small pieces  #########################
# #################################################################


def read_inputs(file_extension, location, str_loc='suffix'):
    # this function can find all 'file_extension' files in folders downstream from 'location'
    file_name = []  # file names
    file_list = []  # file names with paths

    for root, dirs, files in os.walk(location):
        for file in files:
            if str_loc == 'suffix':
                if file.endswith(file_extension):
                    file_name.append(file)
                    file_list.append(os.path.join(root, file))
            if str_loc == 'prefix':
                if file.startswith(file_extension):
                    file_name.append(file)
                    file_list.append(os.path.join(root, file))
    return file_name, file_list


def mk_check_del_directory(path):
    """
    This code checks for the dir being created, and if it is already
    present, deletes it (with warning), before recreating it
    """
    if not os.path.exists(path):  # Check if the dir is alrady pessent
        os.makedirs(path)  # Build desired output directory


def mk_check_del_file(path):
    #  This code checks for the file being created/moved already exists at the destination.
    #  And if so, delets it.
    if os.path.isfile(path):  # Check if the file is alrady pessent
        os.remove(path)  # Delete file


def ck_for_empty_file(f):
    if os.stat(f).st_size == 0:
        print('file: ' + str(f) + ' is empty.')
        sys.exit()


def format_e(n, p):
    # n = number, p = precisions
    return "%0.*E" % (p, n)


def format_n(n, p):
    # n = number, p = precisions
    return "%0.*f" % (p, n)


def grab_str(line, pos):
    a = str(line)
    b = a.split()
    return b[pos]


def grab_lines(file):
    f = open(file, "r")
    lines = f.readlines()
    f.close()
    return lines


def grab_float(line, pos):
    # grabs the 'n'th string split component of a 'line' as a float.
    a = str(line)
    b = a.split()
    # designed to catch exponents of 3 digits, which are misprinted in EQ3/6 outputs,
    # ommiting the 'E'.
    if re.findall(r'[0-9][-\+][0-9]', b[pos]):
        return 0.000
    else:
        # handle attached units if present (rid of letters) without bothering the E+ in scientific
        # notation if present.
        c = re.findall(r'[0-9Ee\+\.-]+', b[pos])
        return float(c[0])


def mine_pickup_lines(pp, file, position):
    """
    pp = project path
    file = file name

    position = s or d (statis or dynamic).

    check_electrical_imbalance: false (dont check). val = ± imbalance allowed

    A pickup file contains two blocks, allowing the described system
    to be employed in two different ways. The top of a 3p or 6p file
    presents the fluid as a reactant to be reloaded into the reactant block
    of another 6i file. This can also be thought of as the dynamic system/fluid 'd',
    as it is the fluid that is being titrated as a function of Xi.
    The second block, below the reactant pickup lines,
    contains a traditional pickup file. This can also be thought of as a static
    system/fluid 's', as it is the system that is initiated at a fixed mass during a titration.
    """
    try:
        p_lines = grab_lines(os.path.join(pp, file))

        if position == 'd':
            # mine the reactant block (dynamic fluid)
            x = 0
            while not re.findall(r'^\*------------------', p_lines[x]):
                x += 1
            x += 1
            start_sw = x
            while not re.findall(r'^\*------------------', p_lines[x]):
                # replace morr value to excess, so that it can be continuesly titrated in pickup fluid,
                # without exhaustion this is a default standin. note that other codes may alter this
                # later, such as when some limited amount of seawater entrainment is accounted for.
                if re.findall('^      morr=', p_lines[x]):
                    p_lines[x] = p_lines[x].replace('morr=  1.00000E+00', 'morr=  1.00000E+20')
                    x += 1
                else:
                    x += 1

            end_sw = x
            return p_lines[start_sw:end_sw]

        elif position == 's':
            # mine fluid in the 'pickup' position from the bottom of the 3p file
            x = len(p_lines) - 1
            while not re.findall(r'^\*------------------', p_lines[x]):
                x -= 1
            x += 1
            return p_lines[x:]
        else:
            print('Ya fucked up!')
            print('  Pickup file choice not set correctly.')
            print('  must be either "d" (dynamic), referring')
            print('  to the system entered in the reactant block')
            print('  or "s" (static), reffereing to fluid in the ')
            print('  pickup position which exists at a fixed mass.')
            sys.exit()
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.FILE_ERROR_3P)

def log_rng(mid, error_in_frac):
    return [np.log10(mid * _) for _ in [1 - error_in_frac, 1 + error_in_frac]]


def norm_list(data):
    return list((data - np.min(data)) / (np.max(data) - np.min(data)))

# #####################################################################
# ###########################  3i/6i  #################################
# #####################################################################\


class IOPT_1(IntEnum):
    """
    Physical System Model Selection:
    """
    CLOSED_SYS = 0  # Closed system
    TITRATION_SYS = 1  # Titration system
    FLOW_THROUGH_SYS = 2  # Fluid-centered flow-through open system


class IOPT_2(IntEnum):
    """
    Kinetic Mode Selection:
    """
    ARBITRARY_KINETICS = 0  # Reaction progress mode (arbitrary kinetics)
    TRUE_KINETICS = 1  # Reaction progress/time mode (true kinetics)


class IOPT_3(IntEnum):
    """
    Phase Boundary Searches:
    """
    STEP_SIZE_BY_PHASE_BOUNDARIES = 0  # Search for phase boundaries and constrain the step size to match
    SEARCH_PHASE_BOUNDARIES = 1  # Search for phase boundaries and print their locations
    DONT_SEARCH_PHASE_BOUNDARIES = 2  # Don't search for phase boundaries


class IOPT_4(IntEnum):
    """
    Solid Solutions
    """
    IGNORE_SS = 0
    PERMIT_SS = 1


class IOPT_5(IntEnum):
    """
    Clear the ES Solids Read from the INPUT File:
    """
    DONT_CLEAR_SOLIDS = 0
    CLEAR_SOLIDS = 1


class IOPT_6(IntEnum):
    """
    Clear the ES Solids at the Initial Value of Reaction Progress:
    """
    DONT_CLEAR_SOLIDS_AT_INITIAL = 0
    CLEAR_SOLIDS_AT_INITIAL = 1


class IOPT_7(IntEnum):
    """
    Clear the ES Solids at the End of the Run:
    """
    DONT_CLEAR_SOLIDS_AT_END = 0
    CLEAR_SOLIDS_AT_END = 1


class IOPT_9(IntEnum):
    """
    Clear the PRS Solids Read from the INPUT file:
    """
    DONT_CLEAR_PRS_SOLIDS_FROM_INPUT = 0
    CLEAR_PRS_SOLIDS_FROM_INPUT = 1


class IOPT_10(IntEnum):
    """
    Clear the PRS Solids at the End of the Run:
    """
    DONT_CLEAR_PRS_SOLIDS_AT_END = 0
    CLEAR_PRS_SOLIDS_AT_END = 1  # Do it, unless numerical problems cause early termination


class IOPT_11(IntEnum):
    """
    Auto Basis Switching in pre-N-R Optimization
    """
    DONT_PRE_NR_AUTO_BASIS_SWITCH = 0
    PRE_NR_BASIS_SWITCH = 1


class IOPT_12(IntEnum):
    """
    Auto Basis Switching after Newton-Raphson Iteration
    """
    DONT_POST_NR_AUTO_BASIS_SWITCH = 0
    POST_NR_BASIS_SWITCH = 1


class IOPT_13(IntEnum):
    """
    Calculational Mode Selection
    """
    PATH_TRACE = 0  # Normal path tracing
    ECONOMY = 1  # Economy mode (if permissible)
    SUPER_ECONOMY = 2  # Super economy mode (if permissible)


class IOPT_14(IntEnum):
    """
    ODE Integrator Corrector Mode Selection
    """
    STIFF_SIMPLE_CORRECTORS = 0  # Allow Stiff and Simple Correctors
    SIMPLE_CORRECTORS = 1  # Allow Only the Simple Corrector
    STIFF_CORRECTORS = 2  # Allow Only the Stiff Corrector
    NO_CORRECTORS = 3  # Allow No Correctors


class IOPT_15(IntEnum):
    """
    Force the Suppression of All Redox Reactions (NOT IN USE)
    """
    DONT_SUPPRESS_REDOX = 0
    SUPPRESS_REDOX = 1


class IOPT_16(IntEnum):
    """
    BACKUP File Options
    """
    NO_BACKUP_FILE = -1
    WRITE_BACKUP_FILE = 0
    WRITE_SEQUENTIAL_BACKUP_FILE = 1


class IOPT_17(IntEnum):
    """
    PICKUP File Options
    """
    DONT_WRITE_PICKUP = -1
    WRITE_PICKUP = 0


class IOPT_18(IntEnum):
    """
    TAB File Options
    """
    DONT_WRITE_TAB = -1
    WRITE_TAB = 0
    PREPEND_TAB = 1  # Write a TAB file, prepending TABX file data from a previous run


class IOPT_19(IntEnum):
    """
    Advanced EQ3NR PICKUP File Options
    """
    NORMAL_PICKUP = 0
    QZ_DISSOLVE_PICKUP = 1  # Write an EQ6 INPUT file with Quartz dissolving, relative rate law
    ALBITE_DISSOLVE_PICKUP = 2  # Write an EQ6 INPUT file with Albite dissolving, TST rate law
    SIXI_FLUID_1_AS_FLUID_MIX = 3  # default for eleanor


class IOPT_20(IntEnum):
    """
    Advanced EQ6 PICKUP File Options:
    """
    NORMAL_PICKUP = 0
    FLUID_MIXING_PICKUP = 1  # Write an EQ6 INPUT file with Fluid 1 set up for fluid mixing


class IOPG_1(IntEnum):
    """
    Aqueous Species Activity Coefficient Model
    """
    DAVIES = -1
    B_DOT = 0
    PITZER = 1
    HC_DH = 2


class IOPG_2(IntEnum):
    """
    Choice of pH Scale (Rescales Activity Coefficients)
    """
    INTERNAL_PH = -1  # no rescaling
    NBS_PH = 0  # uses the Bates-Guggenheim equation
    MESMER_PH = 1  # numerically, pH = -log m(H+)


class IOPR_1(IntEnum):
    """
    Print All Species Read from the Data File
    """
    DONT_PRINT_DATA_FILE_SP = 0
    PRINT_DATA_FILE_SP = 1


class IOPR_2(IntEnum):
    """
     - Print All Reactions:
    """
    DONT_PRINT_RXNS = 0  # Don't print
    PRINT_ALL_RXNS = 1  # Print the reactions
    PRINT_RXNS_LOGK = 2  # Print the reactions and log K values
    PRINT_RXNS_LOGK_DATA = 3  # Print the reactions, log K values, and associated data


class IOPR_3(IntEnum):
    """
    Print the Aqueous Species Hard Core Diameters
    """
    DONT_PRINT_HARD_DIAMETERS = 0
    PRINT_HARD_DIAMETERS = 1


class IOPR_4(IntEnum):
    """
    Print a Table of Aqueous Species Concentrations, Activities, etc.
    """
    CUT_NEG8 = -3  # Omit species with molalities < 1.e-8
    CUT_NEG12 = -2  # Omit species with molalities < 1.e-12
    CUT_NEG20 = -1  # Omit species with molalities < 1.e-20
    CUT_NEG100 = 0  # Omit species with molalities < 1.e-100
    INCLUDE_ALL_AQ = 1


class IOPR_5(IntEnum):
    """
    Print a Table of Aqueous Species/H+ Activity Ratios
    """
    DONT_PRINT_AQ_OVER_H = 0
    PRINT_CAT_RATIOS = 1  # Print cation/H+ activity ratios only
    PRINT_CAT_AN_RATIOS = 2  # Print cation/H+ and anion/H+ activity ratios
    PRINT_CAT_AN_NU_RATIOS = 3  # Print ion/H+ activity ratios and neutral species activities


class IOPR_6(IntEnum):
    """
    Print a Table of Aqueous Mass Balance Percentages
    """
    DONT_PRINT_AQ_MASS_BAL = -1
    NINTY_NINE_AQ_MASS_BAL = 0  # Print species comprising 99% of mass balance
    PRINT_ALL_SP_MASS_BAL = 1


class IOPR_7(IntEnum):
    """
    Print Tables of Saturation Indices and Affinities
    """
    DONT_PRINT_AFFINITIES = -1
    RID_UNDER_10KCAL_AFFINITIES = 0  # omit phases undersaturated by more than 10 kcal
    PRINT_ALL_AFFINITIES = 1


class IOPR_8(IntEnum):
    """
    Print a Table of Fugacities:
    """
    DONT_PRINT_FUGACITIES = -1
    PRINT_FUGACITIES = 0


class IOPR_9(IntEnum):
    """
    Print a Table of Mean Molal Activity Coefficients
    """
    DONT_PRINT_MEAN_ACTIVITY_COE = 0
    PRINT_MEAN_ACTIVITY_COE = 1


class IOPR_10(IntEnum):
    """
    Print a Tabulation of the Pitzer Interaction Coefficients
    """
    DONT_PRINT_PITZER_INTERACT_COE = 0
    SUMMARY_PITZER_INTERACT_COE = 1
    DETAILED_PITZER_INTERACT_COE = 2


class IOPR_17(IntEnum):
    """
    PICKUP file format ("W" or "D")
    """
    PICKUP_IS_INPUT_FORMAT = 0
    W_FORMAT = 1
    D_FORMAT = 2


class IODB_1(IntEnum):
    """
    Print General Diagnostic Messages:
    """
    DONT_PRINT_DIAG = 0
    PRINT_LEVEL_1_DIAG = 1  # Print Level 1 diagnostic messages
    PRINT_LEVEL_1_2_DIAG = 2  # Print Level 1 and Level 2 diagnostic messages


class IODB_2(IntEnum):
    """
    Kinetics Related Diagnostic Messages:
    """
    DONT_PRINT_KINETIC_DIAG = 0
    PRINT_LEVEL_1_KINETIC_DIAG = 1  # Print Level 1 kinetics diagnostic messages
    PRINT_LEVEL_1_2_KINETIC_DIAG = 2  # Print Level 1 and Level 2 kinetics diagnostic messages


class IODB_3(IntEnum):
    """
    Print Pre-Newton-Raphson Optimization Information:
    """
    DONT_PRINT_PRE_NR_DIAG = 0
    SUMMARY_PRE_NR_DIAG = 1  # Print summary information
    DETAILED_PRE_NR_DIAG = 2  # Print detailed information (including the beta and del vectors)
    MORE_DETAILED_PRE_NR_DIAG = 3  # Print more detailed information (including matrix equations)
    MOST_DETAILED_PRE_NR_DIAG = 4  # Print most detailed information (including activity coefficients)


class IODB_4(IntEnum):
    """
    Print Newton-Raphson Iteration Information:
    """
    DONT_PRINT_NR_INFO = 0
    SUMMARY_NR_INFO = 1  # Print summary information
    DETAILED_NR_INFO = 2  # Print detailed information (including the beta and del vectors)
    MORE_DETAILED_NR_INFO = 3  # Print more detailed information (including the Jacobian)
    MOST_DETAILED_NR_INFO = 4  # Print most detailed information (including activity coefficients)


class IODB_5(IntEnum):
    """
    Print Step-Size and Order Selection:
    """
    DONT_PRINT_STEP_SELECT_INFO = 0  # Don't print
    SUMMARY_STEP_SELECT_INFO = 1  # Print summary information
    DETAILED_STEP_SELECT_INFO = 2  # Print detailed information


class IODB_6(IntEnum):
    """
    Print Details of Hypothetical Affinity Calculations:
    """
    DONT_PRINT_AFFINITY_CALC = 0  # Don't print
    SUMMARY_AFFINITY_CALC = 1  # Print summary information
    DETAILED_AFFINITY_CALC = 2  # Print detailed information


class IODB_7(IntEnum):
    """
    Print General Search (e.g., for a phase boundary) Information:
    """
    DONT_PRINT_PHASE_BOUNDRY_INFO = 0
    SUMMARY_PHASE_BOUNDRY_INFO = 1  # Print summary information


class IODB_8(IntEnum):
    """
    Print ODE Corrector Iteration Information:
    """
    DONT_PRINT_ODE_CORRECTOR = 0
    SUMMARY_ODE_CORRECTOR = 1  # Print summary information
    DETAILED_ODE_CORRECTOR = 2  # Print detailed information (including the betar and delvcr vectors)|


def set_3i_switches(config):
    """
    Set eq3 switches, including:
    iopt model option switches,
    iopg activity coefficient option switches
    iopr print option switches

    :param config: non-default switch values for 3i file
    :type config: dict

    """
    d = {}
    d['iopt_4'] = IOPT_4(config.get('iopt_4', 0))
    d['iopt_11'] = IOPT_11(config.get('iopt_11', 0))
    d['iopt_17'] = IOPT_17(config.get('iopt_17', 0))
    d['iopt_19'] = IOPT_19(config.get('iopt_19', 3))

    if config.get('iopt_19', 3) != 3:
        print('please remove iopt_19 constraint on campaign json')
        print(' "3i settings". iopt_19 = 3 is a default requirement for eleanor.')
        sys.exit()

    d['iopg_1'] = IOPG_1(config.get('iopg_1', 0))
    d['iopg_2'] = IOPG_2(config.get('iopg_2', 0))
    d['iopr_1'] = IOPR_1(config.get('iopr_1', 0))
    d['iopr_2'] = IOPR_2(config.get('iopr_2', 0))
    d['iopr_3'] = IOPR_3(config.get('iopr_3', 0))
    d['iopr_4'] = IOPR_4(config.get('iopr_4', 1))
    d['iopr_5'] = IOPR_5(config.get('iopr_5', 0))
    d['iopr_6'] = IOPR_6(config.get('iopr_6', -1))
    d['iopr_7'] = IOPR_7(config.get('iopr_7', 1))
    d['iopr_8'] = IOPR_8(config.get('iopr_8', 0))
    d['iopr_9'] = IOPR_9(config.get('iopr_9', 0))
    d['iopr_10'] = IOPR_10(config.get('iopr_10', 0))
    d['iopr_17'] = IOPR_17(config.get('iopr_17', 0))
    d['iodb_1'] = IODB_1(config.get('iodb_1', 0))
    d['iodb_3'] = IODB_3(config.get('iodb_3', 0))
    d['iodb_4'] = IODB_4(config.get('iodb_4', 0))
    d['iodb_6'] = IODB_6(config.get('iodb_6', 0))
    return d


def set_6i_switches(config):
    """
    Set eq6 switches, including:
    iopt model option switches,
    iopg activity coefficient option switches
    iopr print option switches

    :param config: non-default switch values for 6i file
    :type config: dict

    """
    d = {}
    d['iopt_1'] = IOPT_1(config.get('iopt_1', 0))
    d['iopt_2'] = IOPT_2(config.get('iopt_2', 0))
    d['iopt_3'] = IOPT_3(config.get('iopt_3', 0))
    d['iopt_4'] = IOPT_4(config.get('iopt_4', 0))
    d['iopt_5'] = IOPT_5(config.get('iopt_5', 0))
    d['iopt_6'] = IOPT_6(config.get('iopt_6', 0))
    d['iopt_7'] = IOPT_7(config.get('iopt_7', 0))
    d['iopt_9'] = IOPT_9(config.get('iopt_9', 0))
    d['iopt_10'] = IOPT_10(config.get('iopt_10', 0))
    d['iopt_11'] = IOPT_11(config.get('iopt_11', 0))
    d['iopt_12'] = IOPT_12(config.get('iopt_12', 0))
    d['iopt_13'] = IOPT_13(config.get('iopt_13', 0))
    d['iopt_14'] = IOPT_14(config.get('iopt_14', 0))
    d['iopt_15'] = IOPT_15(config.get('iopt_15', 0))
    d['iopt_16'] = IOPT_16(config.get('iopt_16', -1))
    d['iopt_17'] = IOPT_17(config.get('iopt_17', 0))
    d['iopt_18'] = IOPT_18(config.get('iopt_18', -1))
    d['iopt_20'] = IOPT_20(config.get('iopt_20', 0))
    d['iopr_1'] = IOPR_1(config.get('iopr_1', 0))
    d['iopr_2'] = IOPR_2(config.get('iopr_2', 0))
    d['iopr_3'] = IOPR_3(config.get('iopr_3', 0))
    d['iopr_4'] = IOPR_4(config.get('iopr_4', 1))
    d['iopr_5'] = IOPR_5(config.get('iopr_5', 0))
    d['iopr_6'] = IOPR_6(config.get('iopr_6', -1))
    d['iopr_7'] = IOPR_7(config.get('iopr_7', 1))
    d['iopr_8'] = IOPR_8(config.get('iopr_8', 0))
    d['iopr_9'] = IOPR_9(config.get('iopr_9', 0))
    d['iopr_10'] = IOPR_10(config.get('iopr_10', 0))
    d['iopr_17'] = IOPR_17(config.get('iopr_17', 1))
    d['iodb_1'] = IODB_1(config.get('iodb_1', 0))
    d['iodb_2'] = IODB_2(config.get('iodb_2', 0))
    d['iodb_3'] = IODB_3(config.get('iodb_3', 0))
    d['iodb_4'] = IODB_4(config.get('iodb_4', 0))
    d['iodb_5'] = IODB_5(config.get('iodb_5', 0))
    d['iodb_6'] = IODB_6(config.get('iodb_6', 0))
    d['iodb_7'] = IODB_7(config.get('iodb_7', 0))
    d['iodb_8'] = IODB_8(config.get('iodb_8', 0))
    return d


def switch_grid_3(three_i_switches):
    """
    build the lines containing switch information for each 3i file
    :param three_i_switches: switch values for 6i file
    :type three_i_switches: dict
    """
    pr = {}

    for _ in three_i_switches:
        # ### add_gap
        pr[_] = ' ' * (2 - len(str(int(three_i_switches[_])))) + str(int(three_i_switches[_]))

    switches = "\n".join(('*               1    2    3    4    5    6    7    8    9   10',
                         f'  iopt1-10=     0    0    0   {pr["iopt_4"]}    0    0    0    0    0    0',
                         f' iopt11-20=    {pr["iopt_11"]}    0    0    0    0    0   {pr["iopt_17"]}    0   {pr["iopt_19"]}    0',
                         f'  iopg1-10=    {pr["iopg_1"]}   {pr["iopg_2"]}    0    0    0    0    0    0    0    0',
                          ' iopg11-20=     0    0    0    0    0    0    0    0    0    0',
                         f' iopr11-20=    {pr["iopr_1"]}   {pr["iopr_2"]}   {pr["iopr_3"]}   {pr["iopr_4"]}   {pr["iopr_5"]}   {pr["iopr_6"]}   {pr["iopr_7"]}   {pr["iopr_8"]}   {pr["iopr_9"]}   {pr["iopr_10"]}',
                         f' iopr11-20=     0    0    0    0    0    0   {pr["iopr_17"]}    0    0    0',
                         f'  iodb1-10=    {pr["iodb_1"]}    0   {pr["iodb_3"]}   {pr["iodb_4"]}    0   {pr["iodb_6"]}    0    0    0    0',
                          ' iodb11-20=     0    0    0    0    0    0    0    0    0    0')) + "\n"
    return switches


def switch_grid_6(six_i_switches):
    """
    build the lines containing switch information for each 3i file
    :param six_i_switches: switch values for 6i file
    :type six_i_switches: dict
    """
    pr = {}

    for _ in six_i_switches:
        # ### add_gap
        pr[_] = ' ' * (2 - len(str(int(six_i_switches[_])))) + str(int(six_i_switches[_]))

    switches = "\n".join(('*               1    2    3    4    5    6    7    8    9   10',
                         f'  iopt1-10=    {pr["iopt_1"]}   {pr["iopt_2"]}   {pr["iopt_3"]}   {pr["iopt_4"]}   {pr["iopt_5"]}   {pr["iopt_6"]}   {pr["iopt_7"]}    0   {pr["iopt_9"]}   {pr["iopt_10"]}',
                         f' iopt11-20=    {pr["iopt_11"]}   {pr["iopt_12"]}   {pr["iopt_13"]}   {pr["iopt_14"]}   {pr["iopt_15"]}   {pr["iopt_16"]}   {pr["iopt_17"]}   {pr["iopt_18"]}    0   {pr["iopt_20"]}',
                         f'  iopr1-10=    {pr["iopr_1"]}   {pr["iopr_2"]}   {pr["iopr_3"]}   {pr["iopr_4"]}   {pr["iopr_5"]}   {pr["iopr_6"]}   {pr["iopr_7"]}   {pr["iopr_8"]}   {pr["iopr_9"]}   {pr["iopr_10"]}',
                         f' iopr11-20=     0    0    0    0    0    0   {pr["iopr_17"]}    0    0    0',
                         f'  iodb1-10=    {pr["iodb_1"]}   {pr["iodb_2"]}   {pr["iodb_3"]}   {pr["iodb_4"]}   {pr["iodb_5"]}   {pr["iodb_6"]}   {pr["iodb_7"]}   {pr["iodb_8"]}    0    0',
                          ' iodb11-20=     0    0    0    0    0    0    0    0    0    0')) + "\n"
    return switches


def build_mineral_rnt(phase, morr, rk1b):
    """
    The function builds a 6i reactant block for mineral 'phase' of type jcode = 0.
    of moles  = morr, and a titration rate relative to xi=1 of rk1b
    """

    # ########### example block ##############
    #   *-----------------------------------------------------------------------------
    # reactant= Quartz
    #    jcode=  0               jreac=  0
    #     morr=  9.40100E+01      modr=  0.00000E+00
    #      nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00
    #     fkrc=  0.00000E+00
    #     nrk1=  1                nrk2=  0
    #     rkb1=  9.40100E-03      rkb2=  0.00000E+00      rkb3=  0.00000E+00

    return '\n'.join(['*-----------------------------------------------------------------------------',  # noqa (E501)
                      f'  reactant= {phase}',
                      '     jcode=  0               jreac=  0',
                      f'      morr=  {format_e(10**morr, 5)}      modr=  0.00000E+00',
                      '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                      '      fkrc=  0.00000E+00',
                      '      nrk1=  1',
                      f'       rk1=  {format_e(rk1b, 5)}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'])  # noqa (E501)


def build_gas_rnt(phase, morr, rk1b):
    """
    build gas reactant block
    """

    # ############ example block ###############
    # *-----------------------------------------------------------------------------
    # reactant= CH4(g)
    # jcode=  4               jreac=  0
    # morr=  1.50000E-03      modr=  0.00000E+00
    # nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00
    # fkrc=  0.00000E+00
    # nrk1=  1                nrk2=  0
    # rkb1=  1.00000E+00      rkb2=  0.00000E+00      rkb3=  0.00000E+00

    return '\n'.join(['*-----------------------------------------------------------------------------',  # noqa (E501)
                      f'  reactant= {phase}',
                      '     jcode=  4               jreac=  0',
                      f'      morr=  {format_e(10**morr, 5)}      modr=  0.00000E+00',
                      '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                      '      fkrc=  0.00000E+00',
                      '      nrk1=  1',
                      f'       rk1=  {format_e(rk1b, 5)}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'])  # noqa (E501)

# #################################################################
# ##########################  classes  ############################
# #################################################################


class Three_i(object):
    """
        Instantiates 3i document template that contains the correct
        format (all run setings).
        Any feature of 6i files can be added to the __init__ function,
        to be made amdendable between campaigns.
    """

    def __init__(self, three_i_switches):
        """
        instantiates three_i constants
        """
        self.switches = three_i_switches
        self.switch_grid = switch_grid_3(three_i_switches)

    def write(self, local_name, v_state, v_basis, cb, suppress_sp, output_details='n'):
        """
        local_name = actual file name
        v_state = dict['state_parameter_name'] = value
        v_basis = dict['basis_species_name']   = value

        output_details = 'n' (normal), 'v' (verbose, for debugging).
            normal = set in campaign via the campaign json

        """

        if output_details == 'v':
            # ### maximal infomration sought from the 3o file (used in huffer)
            self.switches['iopt_4'] = IOPT_4(1)
            self.switches['iopr_1'] = IOPR_1(1)
            self.switches['iopr_2'] = IOPR_2(3)
            self.switches['iopr_4'] = IOPR_4(1)
            self.switches['iopr_5'] = IOPR_5(3)
            self.switches['iopr_6'] = IOPR_6(1)
            self.switches['iopr_7'] = IOPR_7(1)
            self.switches['iopr_9'] = IOPR_9(1)
            self.switches['iodb_1'] = IODB_1(2)
            self.switches['iodb_3'] = IODB_3(4)
            self.switches['iodb_4'] = IODB_4(4)
            self.switches['iodb_6'] = IODB_6(2)

            # ### rebuild local switch_grid
            switch_grid = switch_grid_3(self.switches)

        else:
            switch_grid = self.switch_grid

        with open(local_name, 'w') as build:
            build.write("\n".join(
                ('EQ3NR input file name= local',
                 'endit.',
                 '* Special basis switches',
                 '    nsbswt=   0',
                 # '    nsbswt=   1',
                 # 'species= SO4-2',
                 # '  switch with= HS-',
                 '* General',
                 f'     tempc=  {format_e(v_state["T_cel"], 5)}',
                 '    jpres3=   0',
                 f'     press=  {format_e(v_state["P_bar"], 5)}',
                 '       rho=  1.00000E+00',
                 '    itdsf3=   0',
                 '    tdspkg=  0.00000E+00     tdspl=  0.00000E+00',
                 '    iebal3=   1',
                 f'     uebal= {cb}\n')))

            if type(v_state['fO2']) == str:
                # ### redox set by species
                build.write("\n".join(
                    ('    irdxc3=   1',
                     '    fo2lgi= 0.00000E+00       ehi=  0.00000E+00',
                     f'       pei=  0.00000E+00    uredox= {v_state["fO2"]}',
                     '* Aqueous basis species\n')))
            else:
                build.write("\n".join(
                    ('    irdxc3=   0',
                     f'    fo2lgi= {format_e(v_state["fO2"], 5)}       ehi=  0.00000E+00',
                     '       pei=  0.00000E+00    uredox= None',
                     '* Aqueous basis species\n')))

            for _ in v_basis.keys():
                if _ == 'H+':
                    build.write(f'species= {_}\n   jflgi= 16    covali=  {v_basis[_]}\n')
                else:
                    build.write(f'species= {_}\n   jflgi=  0    covali=  {format_e(10**v_basis[_], 5)}\n')  # noqa (E501)

            build.write("\n".join(
                ('endit.',
                 '* Ion exchangers',
                 '    qgexsh=        F',
                 '       net=   0',
                 '* Ion exchanger compositions',
                 '      neti=   0',
                 '* Solid solution compositions',
                 '      nxti=   0',
                 '* Alter/suppress options\n')))

            # Handle species supressions
            if suppress_sp:
                build.write(f'     nxmod=   {str(len(suppress_sp))}\n')
                for sp in suppress_sp:
                    build.write(f'   species= {sp}\n')
                    build.write('    option= -1              xlkmod=  0.00000E+00\n')
            else:
                build.write('     nxmod=   0\n')
            build.write(switch_grid)
            build.write("\n".join(('* Numerical parameters',
                                   '     tolbt=  0.00000E+00     toldl=  0.00000E+00',
                                   '    itermx=   0',
                                   '* Ordinary basis switches',
                                   '    nobswt=   0',
                                   '* Saturation flag tolerance',
                                   '    tolspf=  0.00000E+00',
                                   '* Aqueous phase scale factor',
                                   '    scamas=  1.00000E+00')))


class Six_i(object):
    """
        file.6i template containing all run settings.
        Any feature of 6i files can be added to the __init__ function,
        to be made amdendable between campaigns
    """

    def __init__(self,
                 six_i_switches,
                 suppress_min=False,  # mineral suppression
                 min_supp_exemp=[],  # exemptions ot mineral suppression
                 ):
        """
        instantiates six_i constants
        """
        self.switches = six_i_switches
        self.switch_grid = switch_grid_6(six_i_switches)
        self.suppress_min = suppress_min
        self.min_supp_exemp = min_supp_exemp


    def write(self, local_name, reactants, pickup_lines, temp, xi_max=100, morr=100,
              mix_dlxprn=1, mix_dlxprl=1, jtemp='0', additional_sw_rxn=False):
        """
        Constructs a 6i file 'local_name' with instantiated constants

        reactants = dictionary of reactant:value pairs. This dictionary has the same structure
            as the camp.target_rnt dict, except it does not contain ranges, as specific values
            on those ranges have already been selected by the navigator function that built
            the VS table.

        pickup_lines = local 3p files lines

        temp = temperature

        output_details = 'm' (minimal), 'n' (normal), 'v' (verbose, for debugging chemical space).
            normal = the instantiation defaults (self.)
        """

        # reactant count
        reactant_n = len([_ for _ in reactants.keys() if reactants[_][0] != 'fixed gas'])

        if jtemp == '0':
            # t constant
            tempcb = temp
            ttk1 = '0.00000E+00'
            ttk2 = '0.00000E+00'

        elif jtemp == '3':
            # fluid mixing desired.
            # this renders temp (target end temp of the reaction) something to be solved for
            # via xi. must check that it is possible (cant reach 25 C of the two fluids being mixed
            # are above that.)

            # tempcb = high T fluid temp. this is listed in the pickup lines about
            # to be attched to the bottom.

            for _ in pickup_lines:
                if '    tempci=  ' in _:
                    tempcb = grab_str(_, -1)

            # temp of fluid 2 (reactant block seawater)
            ttk2 = '2.00000E+00'
            format_e(float(temp), 5)

            # mass ratio fluid 1 to fluid 2 at xi = 1. THis is solved for the desired T_sys = temp
            # T_sys = (T_vfl*ttk1 + Xi*T_sw) / (Xi + ttk1)
            # To get T)sys to taget 'temp' at Xi  = 1:
            #     ttk1 = (T_sw - temp) / (temp - T_vfl)

            ttk1 = '1.00000E+00'
            ttk1 = format_e((float(ttk2) - temp) / (temp - float(tempcb)), 5)

            # reset ximax so the xi_max = 1 lands on correct system temp, given ttk1
            xi_max = 1

        with open(local_name, 'w') as build:
            build.write('\n'.join([
                'EQ3NR input file name= local',
                'endit.',
                f'     jtemp=  {jtemp}',
                f'    tempcb=  {format_e(float(tempcb), 5)}',
                f'      ttk1=  {ttk1}      ttk2=  {ttk2}',
                '    jpress=  0',
                '    pressb=  0.00000E+00',
                '      ptk1=  0.00000E+00      ptk2=  0.00000E+00',
                f'      nrct=  {str(reactant_n)}\n']))

            fixed_gases = {}
            if reactant_n > 0:
                for _ in reactants.keys():
                    if reactants[_][0] == 'ele':
                        build.write(build_special_rnt(_, reactants[_]))
                    elif reactants[_][0] == 'solid':
                        build.write(build_mineral_rnt(_, reactants[_][1], reactants[_][2]))
                    elif reactants[_][0] == 'gas':
                        build.write(build_gas_rnt(_, reactants[_][1], reactants[_][2]))
                    elif reactants[_][0] == 'fixed gas':
                        # incorporated below
                        fixed_gases[_] = reactants[_]

            else:
                # no reactants
                self.iopt1 = ' 0'

            build.write(
                '\n'.join(['*-----------------------------------------------------------------------------',  # noqa (E501)
                           f'    xistti=  0.00000E+00    ximaxi=  {format_e(float(xi_max), 5)}',
                           '    tistti=  0.00000E+00    timmxi=  1.00000E+38',
                           '    phmini= -1.00000E+38    phmaxi=  1.00000E+38',
                           '    ehmini= -1.00000E+38    ehmaxi=  1.00000E+38',
                           '    o2mini= -1.00000E+38    o2maxi=  1.00000E+38',
                           '    awmini= -1.00000E+38    awmaxi=  1.00000E+38',
                           '    kstpmx=        10000',
                           '    dlxprn=  1.00000E+38    dlxprl=  1.00000E+38',
                           '    dltprn=  1.00000E+38    dltprl=  1.00000E+38',
                           '    dlhprn=  1.00000E+38    dleprn=  1.00000E+38',
                           '    dloprn=  1.00000E+38    dlaprn=  1.00000E+38',
                           '    ksppmx=          999',
                           '    dlxplo=  1.00000E+38    dlxpll=  1.00000E+38',
                           '    dltplo=  1.00000E+38    dltpll=  1.00000E+38',
                           '    dlhplo=  1.00000E+38    dleplo=  1.00000E+38',
                           '    dloplo=  1.00000E+38    dlaplo=  1.00000E+38',
                           '    ksplmx=        10000\n']))

            build.write(self.switch_grid)

            # mineral supression
            if self.suppress_min:
                build.write('     nxopt=  1\n    option= All    \n')
            else:
                build.write('     nxopt=  0\n')

            # exemptions to mineral suppressions
            if len(self.min_supp_exemp) != 0:
                build.write(f'    nxopex=  {str(int(len(self.min_supp_exemp)))}\n')
                for _ in self.min_supp_exemp:
                    build.write(f'   species= {_}\n')

            elif len(self.min_supp_exemp) == 0 and self.suppress_min:
                build.write('    nxopex=  0\n')

            # fixed gases
            if len(fixed_gases) == 0:
                build.write('      nffg=  0\n')
            else:
                build.write(f'      nffg=  {len(fixed_gases)}\n')
                for _ in fixed_gases:
                    build.write(f'   species= {_}\n')
                    build.write(f'     moffg=  {format_e(float(fixed_gases[_][2]), 5)}    xlkffg= {format_e(float(fixed_gases[_][1]), 5)}\n')

            build.write('\n'.join([
                '    nordmx=   6',
                '     tolbt=  0.00000E+00     toldl=  0.00000E+00',
                '    itermx=   0',
                '    tolxsf=  0.00000E+00',
                '    tolsat=  0.00000E+00',
                '    ntrymx=   0',
                '    dlxmx0=  0.00000E+00',
                '    dlxdmp=  0.00000E+00',
                '*-----------------------------------------------------------------------------\n']))  # noqa (E501)

            for _ in pickup_lines:
                build.write(_)


class WorkingDirectory(object):
    """
    A context manager for changing the current working directory.

    :param path: The path of the new current working directory
    :type path: str
    """
    def __init__(self, path):
        self.path = os.path.realpath(path)
        self.cwd = os.getcwd()

    def __enter__(self):
        """
        Change into the new current working directory that path.

        :return: the absolute path of the new current working directory
        :rtype: str
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd
        return self.cwd

    def __exit__(self, *args):
        """
        Change back to the original current working directory.
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd


def hash_file(filename, hasher=None):
    """
    TODO, @Doug
    """
    if hasher is None:
        hasher = hashlib.sha256()
    with open(filename, 'rb') as handle:
        for bytes in iter(lambda: handle.read(4096), b''):
            hasher.update(bytes)
    return hasher.hexdigest()


def hash_dir(dirname, hasher=None):
    """
    Compute the hash of a named directory (sha256 by default). The hash is computed in a
    depth-first fashion. For a given directory, this function is called on each subdirectory in
    sorted order. Then :func:`hash_file` is called on each file at that level.

    :param dirname: path to a directory
    :type dirname: str
    :param hasher: an optional hasher, defaults to `hasherlib.sha256()`
    :return: the hex-encode sha256 hash of the file contents
    :rtype: str
    """
    if hasher is None:
        hasher = hashlib.sha256()

    contents = list(map(lambda f: os.path.join(dirname, f), os.listdir(dirname)))

    for dir in sorted(filter(os.path.isdir, contents)):
        hash_dir(dir, hasher)

    for filename in sorted(filter(os.path.isfile, contents)):
        hash_file(filename, hasher)

    return hasher.hexdigest()
