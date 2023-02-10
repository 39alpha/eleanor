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

from .constants import wt_dict, sr_dict
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

def build_special_rnt(phase, phase_dat):
    """
    The function returns a 6i reactant block for special reactant 'phase' of type jcode = 2.
    pahse_dat is the data in the reactant dictionary build for a specific VS by a sailor.
    THis dictionary has the same structure as the camp.target_rnt dictionary in the loaded campaign
    file, but without any ranges, as values have already been selected by the navigator function
    which built the campaigns VS table and generated the local set of orders.

    This function accepts lone elements 'ele' or custom species 'sr' existing in the special
    reactant dictionary (sr_dict) The reactants which may be passed are interations within
    the camp.target_rnt dictionary defined in th eloaded campaign file.
    """

    # special reactant is specified and it is not a lone element
    if phase_dat[0] == 'sr':
        # does special reactnat exists in sr_dict
        try:
            sr_dat = sr_dict[phase]  # in constants

        except Exception as e:
            print('Special reactant not installed:')
            sys.exit(e)

        # transpose to create [ele, sto] pairs and iterate
        middle = []
        for _ in [list(i) for i in zip(*sr_dat)]:
            middle.append(f'   {_[0]}{" " * (2 - len(_[0]))}          {format_e(_[1], 5)}\n')

    # special reactant is a lone element
    else:
        middle = '   {}{}          1.00000E+00\n'.format(phase, ' ' * (2 - len(phase))),

    # the top and bottom of the reactant block is the same for ele and sr,
    # as the reactant is titrated as a single unit (rk1b).
    top = '\n'.join([
                    '*-----------------------------------------------------------------------------', # noqa (E501)
                    f'  reactant=  {phase}',
                    '     jcode=  2               jreac=  0',
                    f'      morr=  {format_e(10**phase_dat[1], 5)}      modr=  0.00000E+00',
                    '     vreac=  0.00000E+00\n'])

    bottom = '\n'.join(['   endit.',
                        '* Reaction',
                        '   endit.',
                        '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                        '      fkrc=  0.00000E+00',
                        '      nrk1=  1                nrk2=  0',
                        f'      rkb1=  {format_e(phase_dat[2], 5)}      rkb2=  0.00000E+00      rkb3=  0.00000E+00\n' # noqa (E501)
                        ])

    return top + ''.join(middle) + bottom


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

    def __init__(self,
                 iopg1='0',    # model choice: 0=DH, 1=pitzer
                 iopr1='0',
                 iopr2='0',
                 iopr4='1',    # incliude all aq species (not just > -100)
                 iopr5='0',    # dont print aq/H+ ratios
                 iopr6='-1',   # dont print 99% table
                 iopr7='1',    # print all SI /affinity table
                 iopr9='0',
                 iopt11='0',   # Auto basis switching   0 (turn on), 1 (turn off)
                 iopt17='0',   # Pickup file:  -1 (dont write), 0 (write)
                 iopt19='3',   # pickup type:  0 (normal), 3 (fluid1 set up for fluid mixing)
                 iopt4='0'     # SS    1 (permit), (ignor)
                 ):
        """
        instantiates three_i constants
        """
        self.iopt4 = iopt4
        self.iopt11 = iopt11
        self.iopt17 = iopt17
        self.iopt19 = iopt19
        self.iopg1 = iopg1
        self.iopr1 = iopr1
        self.iopr2 = iopr2
        self.iopr4 = iopr4
        self.iopr5 = iopr5
        self.iopr6 = iopr6
        self.iopr7 = iopr7
        self.iopr9 = iopr9

    def write(self, local_name, v_state, v_basis, cb, suppress_sp, output_details='n'):
        """
        local_name = actual file name
        v_state = dict['state_parameter_name'] = value
        v_basis = dict['basis_species_name']   = value

        output_details = 'n' (normal), 'v' (verbose, for debugging chemical space).
            normal = the instantiation defaults (self.)

        """

        l_iopg1 = ' ' * (2 - len(self.iopg1)) + self.iopg1

        if output_details == 'v':
            # ## maximal infomration sought from the 3o file,
            # ## to added chemiocal space investigations:
            # ## note extra space in front of number value. this is needed.
            l_iopt4 = ' 1'  # turn on SS so that they are listed in 3o loaded sp.
            l_iopr1 = ' 1'
            l_iopr1 = ' 1'
            l_iopr2 = ' 3'
            l_iopr4 = ' 1'
            l_iopr5 = ' 3'
            l_iopr6 = ' 1'
            l_iopr7 = ' 1'
            l_iopr9 = ' 1'
            l_iopg1 = ' 0'
            l_iodb1 = ' 2'
            l_iodb3 = ' 4'
            l_iodb4 = ' 4'
            l_iodb6 = ' 2'

        elif output_details == 'n':
            # ## normal olutput sought = instantiation defaults (self.)

            # ## no string leading space addition is needed for iopt,
            # ## becuas ei am not intersted in - values there.

            # ## adjust leading space for iopr strings, as they may have
            # ## leading negative values
            l_iopt4 = ' ' * (2 - len(self.iopg1)) + self.iopg1
            l_iopt4 = ' ' * (2 - len(self.iopt4)) + self.iopt4
            l_iopr1 = ' ' * (2 - len(self.iopr1)) + self.iopr1
            l_iopr2 = ' ' * (2 - len(self.iopr2)) + self.iopr2
            l_iopr4 = ' ' * (2 - len(self.iopr4)) + self.iopr4
            l_iopr5 = ' ' * (2 - len(self.iopr5)) + self.iopr5
            l_iopr6 = ' ' * (2 - len(self.iopr6)) + self.iopr6
            l_iopr7 = ' ' * (2 - len(self.iopr7)) + self.iopr7
            l_iopr9 = ' ' * (2 - len(self.iopr9)) + self.iopr9
            l_iopg1 = ' ' * (2 - len(self.iopg1)) + self.iopg1
            l_iodb1 = ' 0'
            l_iodb3 = ' 0'
            l_iodb4 = ' 0'
            l_iodb6 = ' 0'

        else:
            # ## output_details set improperly
            print('Error: {} is not recognized'.format(output_details))
            print('  as a valid output_details value. Must be "n" = ')
            print('  normal or "v" = verbose (for debugging)')
            sys.exit()

        # ## write template to file, amending values into the variable vars
        with open(local_name, 'w') as build:
            build.write("\n".join(
                ('EQ3NR input file name= local',
                 'endit.',
                 '* Special basis switches',
                 #'    nsbswt=   0',
                 '    nsbswt=   1',
                 'species= SO4-2',
                 '  switch with= HS-',
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

            build.write("\n".join(('* Iopt, iopg, iopr, and iodb options',
                                   '*               1    2    3    4    5    6    7    8    9   10',
                                  f'  iopt1-10=     0    0    0   {l_iopt4}    0    0    0    0    0    0',  # noqa (E501)
                                  f' iopt11-20=     {self.iopt11}    0    0    0    0    0    {self.iopt17}    0    {self.iopt19}    0',  # noqa (E501)
                                  f'  iopg1-10=    {l_iopg1}    0    0    0    0    0    0    0    0    0',
                                   ' iopg11-20=     0    0    0    0    0    0    0    0    0    0',
                                  f'  iopr1-10=    {l_iopr1}   {l_iopr2}    0   {l_iopr4}   {l_iopr5}   {l_iopr6}   {l_iopr7}    0   {l_iopr9}    0',  # noqa (E501)
                                   ' iopr11-20=     0    0    0    0    0    0    0    0    0    0',
                                  f'  iodb1-10=    {l_iodb1}    0   {l_iodb3}   {l_iodb4}    0   {l_iodb6}    0    0    0    0',  # noqa (E501)
                                   ' iodb11-20=     0    0    0    0    0    0    0    0    0    0',
                                   '* Numerical parameters',
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
        Instantiates 6i document template that contains the correct
        format (all run setings).
        Any feature of 6i files can be added to the __init__ function,
        to be made amdendable between campaigns
    """

    def __init__(self,
                 suppress_min=False,  # mineral suppression
                 min_supp_exemp=[],  # exemptions ot mineral suppression
                 iopt1='1',  # 0 = closed, 1 = titration, 2 = fluid-centered flow through
                 iopt2='0',
                 iopt3='0',
                 iopt4='1',
                 iopt5='0',
                 iopt6='0',  # clear solids @ 1st step in rxn progress. When on (1) this can fail.
                 iopt7='0',
                 iopt8='0',
                 iopt9='0',
                 iopt10='0',
                 iopr1='0',
                 iopr2='0',
                 iopr3='0',
                 iopr4='1',
                 iopr5='0',
                 iopr6='-1',
                 iopr7='1',
                 iopr8='0',
                 iopr9='0',
                 iopr10='0',
                 iopr17='1'
                 ):
        """
        instantiates six_i constants
        """
        self.suppress_min = suppress_min
        self.min_supp_exemp = min_supp_exemp
        self.iopt1 = ' ' * (2 - len(iopt1)) + iopt1
        self.iopt2 = ' ' * (2 - len(iopt2)) + iopt2
        self.iopt3 = ' ' * (2 - len(iopt3)) + iopt3
        self.iopt4 = ' ' * (2 - len(iopt4)) + iopt4
        self.iopt5 = ' ' * (2 - len(iopt5)) + iopt5
        self.iopt6 = ' ' * (2 - len(iopt6)) + iopt6
        self.iopt7 = ' ' * (2 - len(iopt7)) + iopt7
        self.iopt8 = ' ' * (2 - len(iopt8)) + iopt8
        self.iopt9 = ' ' * (2 - len(iopt9)) + iopt9
        self.iopt10 = ' ' * (2 - len(iopt10)) + iopt10
        self.iopr1 = ' ' * (2 - len(iopr1)) + iopr1
        self.iopr2 = ' ' * (2 - len(iopr2)) + iopr2
        self.iopr3 = ' ' * (2 - len(iopr3)) + iopr3
        self.iopr4 = ' ' * (2 - len(iopr4)) + iopr4
        self.iopr5 = ' ' * (2 - len(iopr5)) + iopr5
        self.iopr6 = ' ' * (2 - len(iopr6)) + iopr6
        self.iopr7 = ' ' * (2 - len(iopr7)) + iopr7
        self.iopr8 = ' ' * (2 - len(iopr8)) + iopr8
        self.iopr9 = ' ' * (2 - len(iopr9)) + iopr9
        self.iopr10 = ' ' * (2 - len(iopr10)) + iopr10
        self.iopr17 = ' ' * (2 - len(iopr10)) + iopr17

    def write(self, local_name, reactants, pickup_lines, temp,
              output_details='m', xi_max=100, morr=100,
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
        if output_details == 'm':
            # minimal output sought:
            pass
        elif output_details == 'v':
            # maximal information sought from the 6o file for debugging
            pass

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

            if reactant_n > 0:
                fixed_gases = {}
                self.iopt1 = ' 1'
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
                           '    ksplmx=        10000',
                           '*               1    2    3    4    5    6    7    8    9   10\n']))

            build.write(
                '  iopt1-10=    ' + '   '.join([_ for _ in
                                                [self.iopt1, self.iopt2, self.iopt3, self.iopt4,
                                                 self.iopt5, self.iopt6, self.iopt7, self.iopt8,
                                                 self.iopt9, self.iopt10]]) + '\n')
            build.write(' iopt11-20=     0    0    0    0    0   -1    0   -1    0    0\n')
            build.write(
                '  iopr1-10=    ' + '   '.join([_ for _ in
                                                [self.iopr1, self.iopr2, self.iopr3, self.iopr4,
                                                 self.iopr5, self.iopr6, self.iopr7, self.iopr8,
                                                 self.iopr9, self.iopr10]]) + '\n')
            build.write('\n'.join([f' iopr11-20=     0    0    0    0    0    0   {self.iopr17}    0    0    0',  # noqa (E501)
                                   '  iodb1-10=     0    0    0    0    0    0    0    0    0    0',
                                   ' iodb11-20=     0    0    0    0    0    0    0    0    0    0\n']))  # noqa (E501)

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
