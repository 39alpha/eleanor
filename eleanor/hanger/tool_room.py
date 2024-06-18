"""
The tool_room contains functions and classes primarily related to
construction of EQ3/6 input files.
"""
import os
import sys
import re
import numpy as np
import hashlib
from enum import IntEnum
from .constants import *  # noqa (F403)
from eleanor.exceptions import RunCode, EleanorFileException


def read_inputs(match, location, str_loc='suffix'):
    """
    Find all files in folders downstream from 'location', with extension 'file_extension'
    :param match: characters to match in file names.
    :type match: str
    :param location: outermost parent directory beign searched.
    :type location: str
    :param str_loc: are the match characters at the beginning or end of the file?
    :type str_loc:  str ('prefix' or 'suffix')
    :return: list containing file names, list containing file paths
    :rtype: list, list
    """
    file_names = []
    file_paths = []
    for root, dirs, files in os.walk(location):
        for file in files:
            if str_loc == 'suffix':
                if file.endswith(match):
                    file_names.append(file)
                    file_paths.append(os.path.join(root, file))
            if str_loc == 'prefix':
                if file.startswith(match):
                    file_names.append(file)
                    file_paths.append(os.path.join(root, file))
    return file_names, file_paths


def mk_check_directory(path):
    """
    This code checks for the dir being created. It will make the directory if it doesn't exist.
    :param path: directory path to be created
    :type path: str
    """
    if not os.path.exists(path):
        os.makedirs(path)


def mk_check_del_file(path):
    """
    Check if the file being created/moved already exists at the destination.
    """
    if os.path.isfile(path):  # Check if the file is alrady pessent
        os.remove(path)  # Delete file


def ck_for_empty_file(f):
    """
    Check if file is empty.

    :param file: file path
    :type file: str
    """
    if os.stat(f).st_size == 0:
        print('file: ' + str(f) + ' is empty.')
        sys.exit()


def format_e(n, p):
    """
    Conver number to a string with scienctific notation format

    :param n: number
    :type n: numeric
    :param p: precision
    "type n: int
    :return: scientific float as string with precision p
    :rtype: str
    """
    return "%0.*E" % (p, n)


def format_n(n, p):
    """
    Conver number to string

    :param n: number
    :type n: numeric
    :param p: precision
    "type n: int
    :return: float as string with precision p
    :rtype: str
    """
    return "%0.*f" % (p, n)


def grab_str(line, pos):
    """
    retrieve a substring from a larger string split on spaces
    :param line: srting. typically a 'line' from an eq36 output file
    :type line: str
    :param pos: position of substring in line
    :type pos: int
    :return: substring at position pos in line
    :rtype: str
    """
    a = str(line)
    b = a.split()
    return b[pos]


def grab_lines(file):
    """
    Read the lines from a text file

    :param file: path the file
    :type file: str
    :return: list of strings, 1 per line in file
    :rtype: list of str
    """
    f = open(file, "r")
    lines = f.readlines()
    f.close()
    return lines


def grab_float(line, pos):
    """
    grab a number from a line of text.


    :param line: line from a text file (or other string)
    :type line: str
    :param pos: position of number in line
    :type pos: int
    :return: number of interest
    :rtype: float
    """
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
    Grab the necessary ines from an eq3 pickup file, for use in an eq6 reaction path calculation

    :param pp: project path
    :type pp: str
    :param file: pickup file name
    :type file: str
    :param position: 's' or 'd', signifies the position of the pickup lines sought in the larger
        pickup file. Eleanor uses iopt_20 = 1, which generates a pickup file containing two blocks,
        allowing the described system to be employed in two different ways. The top of a 3p or 6p
        file presents the fluid as a reactant to be reloaded into the reactant block of another 6i
        file. This can also be thought of as the dynamic system/fluid 'd', as it is the fluid that
        is being titrated as a function of Xi. The second block, below the reactant pickup lines,
        contains a traditional pickup file. This can also be thought of as a static system/fluid
        's', as it is the system that is initiated at a fixed mass during a titration.
    :type position: str
    :return: lines within the pickup file, given 's' or 'd' above.
    :rtype: list of strings
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
                # Replace morr value to excess, so that it can be continuesly titrated in pickup
                # fluid, without exhaustion. Note that other codes may alter this later, if fluid
                # mixes to exact ratios are sought.
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
    """
    TODO, @Doug
    """
    return [np.log10(mid * _) for _ in [1 - error_in_frac, 1 + error_in_frac]]


def norm_list(data):
    """
    TODO, @Doug
    """
    return list((data - np.min(data)) / (np.max(data) - np.min(data)))


def determine_ss_kids(camp, ss, solids):
    """
    determine which solid solution (ss) endmember (kids) will be present in the system

    :param camp: campaign instance
    :type camp: class 'eleanor.campaign.Campaign'

    :param ss: solid solution sloaded given data0 and system setup
    :type ss: list of strings

    :param solids: solids loaded given data0 and system setup
    :type solids: list of strings

    :return: solid solution endmemebers
    :rtype: list of strings
    """
    ss_kids = []
    for i in ss:
        all_kids = camp.representative_data0[i].composition.keys()
        kids_we_care_about = [j for j in all_kids if j in solids]
        ss_kids = ss_kids + [f'{k}_{i}' for k in kids_we_care_about]
    return ss_kids


class JTEMP(IntEnum):
    """
    Temperature option (jtemp). This feature in eq3/6 can take on one of 4 settings,
    which correspond to 4 different treatments of temperature.
    For Eleanor version  1, we only use jtemp = 0 (constant Temperature)
    We plan to add jtemp = 3 (fluid mixing, for Eleanor version 1.1)
    """
    CONSTANT_T = 0


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

    :return: dictionary of switch settings
    :rtype: dictionary of IntEnum class instances
    """
    d = {}
    d['iopt_4'] = IOPT_4(config.get('iopt_4', 0))
    d['iopt_11'] = IOPT_11(config.get('iopt_11', 0))
    d['iopt_17'] = IOPT_17(config.get('iopt_17', 0))
    d['iopt_19'] = IOPT_19(config.get('iopt_19', 3))

    if config.get('iopt_19', 3) != 3:
        print('Please remove iopt_19 constraint on campaign json')
        print(' "3i settings" as iopt_19 = 3 is a default requirement')
        print(' for Eleanor.')
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

    :return: dictionary of switch settings
    :rtype: dictionary of IntEnum class instances
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
    :return: switch grid bloack for eq3 input file
    :rtype: str
    """
    pr = {}

    for _ in three_i_switches:
        pr[_] = ' ' * (2 - len(str(int(three_i_switches[_])))) + str(int(three_i_switches[_]))

    switches = "\n".join((
        '*               1    2    3    4    5    6    7    8    9   10',
        f'  iopt1-10=     0    0    0   {pr["iopt_4"]}    0    0    0    0    0    0',
        f' iopt11-20=    {pr["iopt_11"]}    0    0    0    0    0   {pr["iopt_17"]}    0   {pr["iopt_19"]}    0',
        f'  iopg1-10=    {pr["iopg_1"]}   {pr["iopg_2"]}    0    0    0    0    0    0    0    0',
        ' iopg11-20=     0    0    0    0    0    0    0    0    0    0',
        f' iopr11-20=    {pr["iopr_1"]}   {pr["iopr_2"]}   {pr["iopr_3"]}   {pr["iopr_4"]}   {pr["iopr_5"]}   {pr["iopr_6"]}   {pr["iopr_7"]}   {pr["iopr_8"]}   {pr["iopr_9"]}   {pr["iopr_10"]}',  # noqa: E501
        f' iopr11-20=     0    0    0    0    0    0   {pr["iopr_17"]}    0    0    0',
        f'  iodb1-10=    {pr["iodb_1"]}    0   {pr["iodb_3"]}   {pr["iodb_4"]}    0   {pr["iodb_6"]}    0    0    0    0',  # noqa: E501
        ' iodb11-20=     0    0    0    0    0    0    0    0    0    0')) + "\n"
    return switches


def switch_grid_6(six_i_switches):
    """
    build the lines containing switch information for each 3i file
    :param six_i_switches: switch values for 6i file
    :type six_i_switches: dict
    :return: switch grid bloack for eq6 input file
    :rtype: str
    """
    pr = {}

    for sis in six_i_switches:
        #  add_gap
        pr[sis] = ' ' * (2 - len(str(int(six_i_switches[sis])))) + str(int(six_i_switches[sis]))

    switches = "\n".join((
        '*               1    2    3    4    5    6    7    8    9   10',
        f'  iopt1-10=    {pr["iopt_1"]}   {pr["iopt_2"]}   {pr["iopt_3"]}   {pr["iopt_4"]}   {pr["iopt_5"]}   {pr["iopt_6"]}   {pr["iopt_7"]}    0   {pr["iopt_9"]}   {pr["iopt_10"]}',  # noqa: E501
        f' iopt11-20=    {pr["iopt_11"]}   {pr["iopt_12"]}   {pr["iopt_13"]}   {pr["iopt_14"]}   {pr["iopt_15"]}   {pr["iopt_16"]}   {pr["iopt_17"]}   {pr["iopt_18"]}    0   {pr["iopt_20"]}',  # noqa: E501
        f'  iopr1-10=    {pr["iopr_1"]}   {pr["iopr_2"]}   {pr["iopr_3"]}   {pr["iopr_4"]}   {pr["iopr_5"]}   {pr["iopr_6"]}   {pr["iopr_7"]}   {pr["iopr_8"]}   {pr["iopr_9"]}   {pr["iopr_10"]}',  # noqa: E501
        f' iopr11-20=     0    0    0    0    0    0   {pr["iopr_17"]}    0    0    0',
        f'  iodb1-10=    {pr["iodb_1"]}   {pr["iodb_2"]}   {pr["iodb_3"]}   {pr["iodb_4"]}   {pr["iodb_5"]}   {pr["iodb_6"]}   {pr["iodb_7"]}   {pr["iodb_8"]}    0    0',  # noqa: E501
        ' iodb11-20=     0    0    0    0    0    0    0    0    0    0')) + "\n"
    return switches


def format_suppress_options(suppress_sp):
    """
    Format the species suppress options for the 3i file template

    :param suppress_sp: data0 speices to be suppressed
    :type suppress_sp: list of strings
    :return: formated text for the 3i files, species suppress section
    :rtype: str
    """
    build = ''
    if suppress_sp:
        build = build + f'     nxmod=   {str(len(suppress_sp))}\n'
        for sp in suppress_sp:
            build = build + f'   species= {sp}\n'
            build = build + '    option= -1              xlkmod=  0.00000E+00\n'
    else:
        build = build + '     nxmod=   0\n'
    return build


def format_special_basis_switch(special_basis_switch):
    """
    Format the special basis switching section for the 3i file template

    :param special_basis_switch: dict. key=initial basis species, val = new basis species
    :type special_basis_switch: dictionary
    :return: formated text for the 3i files, special basis switching section
    :rtype: str

    """
    build = ''
    if special_basis_switch == {}:
        build = build + '    nsbswt=   0\n'
    else:
        build = build + f'    nsbswt=   {len(special_basis_switch)}\n'
        for sbs in special_basis_switch:
            build = build + f'species= {sbs}\n'
            build = build + f'  switch with= {special_basis_switch[sbs]}\n'
    return build


def format_limits(xi_max):
    """
    Format the limits section for the 6i file template. for Eleanor version 1, only xi_max
    is set in this block, with all other variables fixed

    :param xi_max: maximum xi valve for 6i reaction path.
    :type xi_max: int or float
    :return: formated text for the 6i files, limits section
    :rtype: str
    """
    return '\n'.join([
        '*-----------------------------------------------------------------------------',  # noqa (E501)
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
        '    ksplmx=        10000\n'
    ])


def build_mineral_rnt(mineral, morr, rk1b):
    """
    Constructs a 6i reactant block for mineral 'mineral' of type jcode = 0.

    :param mineral: mineral name, much match a solid in the loaded data0 file
    :param type: str
    :param morr: moles of reactant available for titration
    :type morr: numeric
    :param rk1b: rate dmorr/dXi for reactant titration
    :type rk1b: numeric
    of moles  = morr, and a titration rate relative to xi=1 of rk1b
    :return: formated text for 6i reactant block
    :rtype: str
    """
    return '\n'.join([
        '*-----------------------------------------------------------------------------',  # noqa (E501)
        f'  reactant= {mineral}',
        '     jcode=  0               jreac=  0',
        f'      morr=  {format_e(10**morr, 5)}      modr=  0.00000E+00',
        '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
        '      fkrc=  0.00000E+00',
        '      nrk1=  1',
        f'       rk1=  {format_e(rk1b, 5)}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'
    ])  # noqa (E501)


def build_gas_rnt(gas_sp, morr, rk1b):
    """
    Build reactant block for gas (jcode = 4)

    :param gas_sp: name of gas reactant. This must come from the gaes loaded from the employed data0
    :type gas_sp: str
    :param morr: moles of reactant available for titration
    :type morr: numeric
    :param rk1b: rate dmorr/dXi for reactant titration
    :type rk1b: numeric
    :return: formated text for 6i reactant block
    :rtype: str
    """
    return '\n'.join(
        ('*-----------------------------------------------------------------------------', f'  reactant= {gas_sp}',
         '     jcode=  4               jreac=  0', f'      morr=  {format_e(10**morr, 5)}      modr=  0.00000E+00',
         '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', '      fkrc=  0.00000E+00',
         '      nrk1=  1', f'       rk1=  {format_e(rk1b, 5)}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'))


def build_sr_rnt(sp, dat):
    """
    The function returns a 6i reactant block for special reactant 'phase' of type jcode = 2.
    pahse_dat is the data in the reactant dictionary build for a specific VS by a sailor.
    THis dictionary has the same structure as the camp.target_rnt dictionary in the loaded campaign
    file, but without any ranges, as values have already been selected by the navigator function which
    built the campaigns VS table and generated the local set of orders.
    This function accepts lone elements 'ele' or custom species 'sr' existing
    in the special reactant dictionary (sr_dict)
    The reactants which may be passed are interations within the camp.target_rnt dictionary
    defined in th eloaded campaign file.
    """
    # Special reactant dictionary.
    #
    # sr_dict['name'] = [[ele list], [associated sto list]]
    sr_dict = {"FeCl2": [["Fe", "Cl", "O"], [1, 2, 1]]}

    # Special reactant is specified and it is not a lone element
    if dat[0] == 'sr':
        # Does special reactnat exists in sr_dict?
        try:
            sr_dat = sr_dict[sp]
        except Exception as e:
            raise ValueError('Special reactant not installed:', e)

        # Transpose to create [ele, sto] pairs and iterate
        middle = []
        for l_idx in [list(i) for i in zip(*sr_dat)]:
            mid = f"   {l_idx[0]}{' '*(2-len(l_idx[0]))}          {format_e(l_idx[1], 5)}\n"
            middle.append(mid)
    # Special reactant is a lone element
    else:
        middle = f"   {sp}{' '*(2-len(sp))}          1.00000E+00\n"

    # The top and bottom of the reactant block is the same for ele and sr, as the reactant is titrated as a single unit
    # (rk1b).
    top = '\n'.join([
        '*-----------------------------------------------------------------------------', '  reactant=  {}'.format(sp),
        '     jcode=  2               jreac=  0', f'      morr=  {format_e(10**dat[1], 5)}      modr=  0.00000E+00',
        '     vreac=  0.00000E+00\n'
    ])

    bottom = '\n'.join([
        '   endit.', '* Reaction', '   endit.',
        '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', '      fkrc=  0.00000E+00',
        '      nrk1=  1                nrk2=  0',
        f'      rkb1=  {format_e(dat[2], 5)}      rkb2=  0.00000E+00      rkb3=  0.00000E+00\n'
    ])

    return top + ''.join(middle) + bottom


class Three_i(object):
    """
    3i files class.
    """

    def __init__(self, special_basis_switch, three_i_switches, suppress_sp):
        """
        File.3i template

        :param special_basis_switch: dictionary of old_basis:new_basis pairs. The old basis must be
            in the basis block of the employed data0 file, and the new_basis species must be in the
            auxillary basis block. This swithc occures before the system is evaluated.
        :type special_basis_switch: dict
        :param three_i_switches: swtich setings for the all 3i files not set to verbose (huffer)
        :type three_i_switches: dict
        :param suppress_sp: otehrwise loaded data0 species to exclude from calculations
        :type suppress_sp: list of strings
        """
        self.top_piece = "\n".join(('EQ3NR input file name= local', 'endit.', '* Special basis switches\n'))
        self.basis_switch = format_special_basis_switch(special_basis_switch)
        self.middle_piece = "\n".join(
            ('endit.', '* Ion exchangers', '    qgexsh=        F', '       net=   0', '* Ion exchanger compositions',
             '      neti=   0', '* Solid solution compositions', '      nxti=   0', '* Alter/suppress options\n'))
        self.supp = format_suppress_options(suppress_sp)
        self.switches = three_i_switches
        self.switch_grid = switch_grid_3(three_i_switches)
        self.end_piece = "\n".join(
            ('* Numerical parameters', '     tolbt=  0.00000E+00     toldl=  0.00000E+00', '    itermx=   0',
             '* Ordinary basis switches', '    nobswt=   0', '* Saturation flag tolerance', '    tolspf=  0.00000E+00',
             '* Aqueous phase scale factor', '    scamas=  1.00000E+00'))

    def write(self, local_name, v_state, v_basis, cb, suppress_sp, output_details='n'):
        """
        Write a 3i file 'local_name' to disk.

        :param local_name: file names
        :type local_name: str
        :param v_state: dict['state_parameter_name'] = value
        :type v_state: dict
        :param v_basis: dict['basis_species_name'] = value
        :type v_basis: dict
        :param cb: basis species to charge balance on. can also be None
        :type cb: str
        :param suppress_sp: data0 species to suppress
        :type suppress_sp: list of str
        :param output_details: how verbose do you want the 3o file? 'n' (normal) 'v' (verbose)
        :type output_details: str (n, or v)
        """

        if output_details == 'v':
            # Maximum information sought from the 3o file (used in huffer)
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

            # Rebuild local switch_grid
            switch_grid = switch_grid_3(self.switches)

        else:
            switch_grid = self.switch_grid

        with open(local_name, 'w') as build:
            build.write(self.top_piece)
            build.write(self.basis_switch)
            build.write("\n".join(
                ('* General', f'     tempc=  {format_e(v_state["T_cel"], 5)}', '    jpres3=   0',
                 f'     press=  {format_e(v_state["P_bar"], 5)}', '       rho=  1.00000E+00', '    itdsf3=   0',
                 '    tdspkg=  0.00000E+00     tdspl=  0.00000E+00', '    iebal3=   1', f'     uebal= {cb}\n')))

            if isinstance(v_state['fO2'], str):
                # redox set by species
                build.write("\n".join(
                    ('    irdxc3=   1', '    fo2lgi= 0.00000E+00       ehi=  0.00000E+00',
                     f'       pei=  0.00000E+00    uredox= {v_state["fO2"]}', '* Aqueous basis species\n')))
            else:
                build.write("\n".join(
                    ('    irdxc3=   0', f'    fo2lgi= {format_e(v_state["fO2"], 5)}       ehi=  0.00000E+00',
                     '       pei=  0.00000E+00    uredox= None', '* Aqueous basis species\n')))

            for k in v_basis.keys():
                if k == 'H+':
                    build.write(f'species= {k}\n   jflgi= 16    covali=  {v_basis[k]}\n')
                else:
                    wr = f'species= {k}\n   jflgi=  0    covali=  {format_e(10**v_basis[k], 5)}\n'
                    build.write(wr)
            build.write(self.middle_piece)
            build.write(self.supp)
            build.write(switch_grid)
            build.write(self.end_piece)


class Six_i(object):
    """
    6i files class
    """

    def __init__(self, reactants, six_i_switches, xi_max=100, suppress_min=False, min_supp_exemp=[]):
        """
        File.6i template.

        :param reactants: dictionary of reactant:value pairs. This dictionary has the same structure
            as the camp.target_rnt dict, except it does not contain ranges, as specific values
            on those ranges have already been selected by the navigator function that built
            the VS table.
        :type reactants: dict
        :param six_i_switches: none default 3i setup switches  (iopt, iopg, iopr, and iodb)
        :type six_i_switches: dict['switch_name'] = int
        :param xi_max: the maximum path extent (in units of reaction progress)
        :type xi_max: int or float
        :param suppress_min: do you wish to suppress mineral precipitation?
        :type suppress_min: Boolean
        :param min_supp_exemp: exemptions to mass suppress option above
        :type min_supp_exemp: list of stirngs (mineral names)
        """
        self.reactant_n = len([k for k in reactants.keys() if reactants[k][0] != 'fixed gas'])
        self.switches = six_i_switches
        self.switch_grid = switch_grid_6(six_i_switches)
        self.xi_max = xi_max
        self.suppress_min = suppress_min
        self.min_supp_exemp = min_supp_exemp
        self.jtemp = JTEMP(0)
        self.limits = format_limits(xi_max)
        self.end_piece = '\n'.join([
            '    nordmx=   6', '     tolbt=  0.00000E+00     toldl=  0.00000E+00', '    itermx=   0',
            '    tolxsf=  0.00000E+00', '    tolsat=  0.00000E+00', '    ntrymx=   0', '    dlxmx0=  0.00000E+00',
            '    dlxdmp=  0.00000E+00',
            '*-----------------------------------------------------------------------------\n'
        ])

    def write(self, local_name, reactants, pickup_lines, temp):
        """
        Write a 6i file 'local_name' to disk.

        :param local_name:
        :type local_name:
        :param reactants: dictionary of reactant:value pairs. This dictionary has the same structure
            as the camp.target_rnt dict, except it does not contain ranges, as specific values
            on those ranges have already been selected by the navigator function that built
            the VS table.
        :type reactants: dict
        :param pickup_lines: local 3p files lines
        :type pickup_lines: list of strings (1 per row)
        :param temp: systems tempeautre (celcius)
        :type temp: float
        """

        with open(local_name, 'w') as build:
            build.write('\n'.join([
                'EQ3NR input file name= local', 'endit.', f'     jtemp=  {int(self.jtemp)}',
                f'    tempcb=  {format_e(float(temp), 5)}', '      ttk1=  0.00000E+00      ttk2=  0.00000E+00',
                '    jpress=  0', '    pressb=  0.00000E+00', '      ptk1=  0.00000E+00      ptk2=  0.00000E+00',
                f'      nrct=  {str(self.reactant_n)}\n'
            ]))

            fixed_gases = {}
            if self.reactant_n > 0:
                for rk in reactants.keys():
                    if reactants[rk][0] == 'mineral':
                        build.write(build_mineral_rnt(rk, reactants[rk][1], reactants[rk][2]))
                    elif reactants[rk][0] == 'gas':
                        build.write(build_gas_rnt(rk, reactants[rk][1], reactants[rk][2]))
                    elif reactants[rk][0] == 'fixed gas':
                        # incorporated below
                        fixed_gases[rk] = reactants[rk]
                    elif reactants[rk][0] in ['sr', 'ele']:
                        build.write(build_sr_rnt(rk, reactants[rk]))
            build.write(self.limits)
            build.write(self.switch_grid)

            # mineral supression
            if self.suppress_min:
                build.write('     nxopt=  1\n    option= All    \n')
            else:
                build.write('     nxopt=  0\n')

            # exemptions to mineral suppressions
            if len(self.min_supp_exemp) != 0:
                build.write(f'    nxopex= {str(int(len(self.min_supp_exemp)))}\n')
                for mse in self.min_supp_exemp:
                    build.write(f'   species= {mse}\n')

            elif len(self.min_supp_exemp) == 0 and self.suppress_min:
                build.write('    nxopex=  0\n')

            # fixed gases
            if len(fixed_gases) == 0:
                build.write('      nffg=  0\n')
            else:
                build.write(f'      nffg=  {len(fixed_gases)}\n')
                for fg in fixed_gases:
                    build.write(f'   species= {fg}\n')
                    to_write = f'     moffg=  {format_e(float(fixed_gases[fg][2]), 5)}'
                    to_write += f'    xlkffg= {format_e(float(fixed_gases[fg][1]), 5)}\n'
                    build.write(to_write)

            build.write(self.end_piece)
            build.write(''.join(pickup_lines))


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
