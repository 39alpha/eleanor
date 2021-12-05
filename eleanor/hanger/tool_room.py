### tool_room
### Developed by Tucker Ely 
### 2018-
### general EQ3/6 dependencies

### contains functions and variables
### related to running and manipulating EQ3/6.
### This file is my attempt to stremaline the development 
### process, as the functions contained herein are 
### commonily duplicated between projects.
### the 'local' here refers to its use on my local machine
### differentiating it from the copy being built within
### the NPP project


import os, shutil, sys, re, math, itertools

import numpy as np
from subprocess import * 
from time import *


from .db_comms import *
from .constants import *

os.environ['EQ36CO']="/Users/tuckerely/NPP_dev/EQ3_6v8.0a/bin"
os.environ['PATH']="{}:{}".format(os.environ['PATH'], os.environ['EQ36CO'])
os.environ['EQ36DA']="/Users/tuckerely/NPP_dev/EQ3_6v8.0a/db"


##################################################################
#########################  small pieces  #########################
##################################################################

def read_inputs(file_extension, location, str_loc = 'suffix'):
    ### this function can find all 'file_extension' files in all downstream folders, of the 'location'
    file_name = []      #     file names
    file_list = []      #     file names with paths

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
    if not os.path.exists(path):            #    Check if the dir is alrady pessent
        os.makedirs(path)                   #    Build desired output directory
    else:
        answer = input('\n Directory {} already exists.\n\
    Are you sure you want to overwrite its contents? (Y E S/N)\n'.format(path))
        if answer == 'Y E S':
            shutil.rmtree(path)             #    Remove directory and contents if it is already present.
            os.makedirs(path)
        else:
            sys.exit("ABORT !")

def mk_check_del_file(path):
    ###  This code checks for the file being created/moved already exists at the destination. And if so, delets it.
    if os.path.isfile(path):                #    Check if the file is alrady pessent
        os.remove(path)                     #    Delete file

def ck_for_empty_file(f):
    if     os.stat(f).st_size == 0:
        print('file: ' + str(f) + ' is empty.')
        sys.exit()

def format_e(n, p):
    ####     n = number, p = precisions
    return "%0.*E"%(p,n)
    # return b.split('E')[0].rstrip('0').rstrip('.') + 'E' + b.split('E')[1]

def format_n(n, p):
    ####     n = number, p = precisions
    return "%0.*f"%(p,n)

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
    ### grabs the 'n'th string split component of a 'line' as a float.
    a = str(line)
    b = a.split()
    ###    designed to catch exponents of 3 digits, which are misprinted in EQ3/6 outputs,
    ### ommiting the 'E'. Such numebr have
    if re.findall('[0-9][-\+][0-9]', b[pos]):
        return 0.000
    else:
        ### handle attached units if present (rid of letters) without bothering the E+ in scientific notation if present.
        c = re.findall('[0-9Ee\+\.-]+', b[pos])
        return float(c[0])

def runeq(ver, suffix, input_file):
    """executes EQ(ver=version = 3, 6), with data file  data0.'suffix', on 'input file' 
    returns standard out and standard error
    """
    # print(' Calling EQ{} on '.format(ver), input_file, ' using ', suffix)
    code_path = None
    if ver == 3:
        code_path= '/home/colemathis/eq3_6/bin/eq3nr' # Generalize the formating
    elif ver == 6:
        code_path = '/home/colemathis/eq3_6/bin/eq6' # Generalize the formating
    else:
        raise ValueError("runeq called with ver arugment set to something besides 3 or 6, you've fucked it")
    
    data1_file = "../db/data1." + suffix # Generalize
    # print(os.path.isfile(data1_file))
    input_file =  input_file
    # print(os.path.isfile(input_file))
    this_cwd = os.path.dirname(os.path.realpath(__file__)) 
    # print(this_cwd)
    test_wd = os.path.join(this_cwd, "../CSS0_huffer")
    # print([code_path, data1_file, input_file])
    process = Popen([code_path, data1_file, input_file], cwd = test_wd,  stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    # print(stdout)
    return stdout, stderr


def mine_pickup_lines(pp, file, position):
    """
    pp = project path
    file = file name

    position = s or d (statis or dynamic)

    a pickup file contains two blocks, allowing the described system
    to be employed in two different ways. The top of a 3p or 6p file
    presents the fluid as a reactant (to be reloaded into the reactant bloack)
    of another 6i file. This can also be thought of as the dynamic system/fluid,
    as it is the fluid that is changing during a titration, being added as a 
    function of Xi. The second block, below the reactant pickup lines,
    contains a traditional pickup file. THis can also be thought of as a static 
    system/fluid, as it is the system that is initiated at a fixed mass during a titration
    """

    p_lines = grab_lines(os.path.join(pp,file))

    if position == 'd':
        ### mine the reactant block (dynamic fluid)
        x = 0
        while not re.findall('^\*------------------', p_lines[x]):
            x += 1
        x += 1
        start_sw = x
        while not re.findall('^\*------------------', p_lines[x]):
            ### replace morr value to excess, so that it can be continuesly titrated in pickup fluid, without exhaustion
            ### this is a default standin. note that other codes may alter this later, such as when some limited amount of seawater
            ### entrainment is accounted for.
            if re.findall('^      morr=', p_lines[x]):
                p_lines[x] = p_lines[x].replace('morr=  1.00000E+00','morr=  1.00000E+20')
                x += 1
            else:
                x += 1

        end_sw = x        
        return p_lines[start_sw:end_sw]
    

    elif position == 's':
        ### mine fluid in the 'pickup' position from the bottom of the 3p file
        x = len(p_lines) - 1
        while not re.findall('^\*------------------', p_lines[x]):
            x -= 1
        x += 1
        return p_lines[x:]


    else:
        print('Ya Fucked up!')
        print('  Pickup file choice not set correctly.')
        print('  must be either "d" (dynamic), referring')
        print('  to the system entered in the reactant block')
        print('  or "s" (static), reffereing to fluid in  the ')
        print('  pickup position which exists at a fixed mass.')
        sys.exit()


def log_rng(mid, error_in_frac):
    return [np.log10(mid*_) for _ in [1-error_in_frac, 1+error_in_frac]]


def norm_list(data):
    return list((data - np.min(data)) / (np.max(data) - np.min(data)))



def reset_sailor(order_path, start, conn, camp_name, file, uuid, code, delete_local = False):
    """ the sailor has failed to run the 'file'
    (1) report to vs database 'camp_name' via server connection 'conn' the exit 'code'
        for 'file' with unique vs_table id 'uuid'
    (2) step back into order folder 'order_path' for next vs point.
    """
    sql = "UPDATE {} SET {} = {} WHERE uuid = '{}';".format('{}_vs'.format(camp_name), 'code', code, uuid)
    execute_postgres_statement(conn, sql)
    print("  {}     {}      {} s".format(file, code, round(time()-start, 4)))
    os.chdir(order_path)

    if delete_local:
        # print('deleting {}'.format(file[:-3]))
        shutil.rmtree(file[:-3])


##################################################################
###########################    debug   ###########################
##################################################################

def track_times():
    profile = cProfile.Profile()
    profile.enable()
    return profile

def report_times(profile):
    profile.disable()
    ps = pstats.Stats(profile)
    ps.sort_stats('cumtime') 
    ps.print_stats()






######################################################################
############################  3i/6i  #################################
######################################################################


##############    Old function from Gale database work.

def oxide_conversion(dat, oxide, fe3_frac):
    """
    WARNING: This function was used purely for Gale alteration work, and requires a specific rock db file column format
    
    Converts wt% oxides listed in desired database to mols/kg, as required by eq6. 
    This function  uses the information listed in the oxide dictionary ‘wt_dict’ 
    to handle the correct oxygen mol numbers properly. 
    This function also handles oxygen as it relates to accounting for Fe(III)/Fe(tot). 
    This function DOES NOT normalize to 100 wt%.

     """

    rock = dat[3:] 

    ### rock = line from database csv file, rock_name in [0], ridge_name in [1], oxides from there.
    ### Oxide is a list of just these oxides
    ### Fe3_frac is the fraction of fe2 that is to me simulated as fe3
    
    deci = 5        #   number of decimal places for oxide mol numbers printed on 6i file
    
    print_list = []
    O_build = 0
    H_build = 0

    for i in oxide:
        name = wt_dict[i][0]                                   #    element name
        amount = float(rock[(oxide.index(i) + 4)]) / 100.0     #    pul wt% value from rock csv line
        val = wt_dict[i][1] * (amount*1000.0 / float(wt_dict[i][3]))       #    element mol value
        

        ### Account for Fe+3 fraction of O to be added
        if i == 'FeO':
            ### fe3_frac * r_Fe_mols * 0.5     (0.5 is the number of adidional O, beyond the 1 in FeO, 
            ### needed to pull an additional e- from Fe2, coverting it to Fe3). 
            ### The one oxygen in FeO is account for in full below, 
            ### when Fe goes on to be treated like any other oxide. 
            O_build += 0.5*fe3_frac*val 

        ### if S-2 is desired, then offset S with 2 mol equivalent H
        if i == 'S':
            H_build += 2*val

        if i == 'H2O': 
            H_build += val
        
        val = format_e(val, deci)    
        O_val = wt_dict[i][2] * (float(amount)*1000.0 / float(wt_dict[i][3]))    #    o mol value
        O_build += O_val


        if i != 'H2O':
            print_list.append( '   ' + name + ' '*(12 - len(name)) + val + '\n')

        
        
    O_build = format_e(O_build, deci)
    name = 'O'
    print_list.append( '   ' + name + ' '*(12 - len(name)) + O_build + '\n')

    H_build = format_e(H_build, deci)
    name = 'H'
    print_list.append( '   ' + name + ' '*(12 - len(name)) + H_build + '\n')

    return print_list

def determine_xi_grab_steps(dlxprn, ximax, starting):
    """ build list of linear xi print steps to grab output data from """
    l = int(ximax / dlxprn)
    xi_str_list = [format_e(x*dlxprn, 5) for x in range( 1, l + 1)]
    xi_str_list.insert(0, format_e(starting, 5))        #  prepend first xi step
    return xi_str_list
 
##############    Reactant Blocks 

def build_special_rnt(phase, phase_dat):
    """
    The function returns a 6i reactant block for special reactant 'phase' of type jcode = 2.
    pahse_dat is the data in the reactant dictionary build for a specific VS by a sailor.
    THis dictionary has the same structure as the camp.target_rnt dictionary in the loaded campaign
    file, but without any ranges, as values have already been selected by the navigator function which
    built the campaigns VS table and generated the local set of orders.

    This function accepts lone elements 'ele' or custom species 'sr' existing in the special reactant dictionary (sr_dict)
    The reactants which may be passed are interations within the camp.target_rnt dictionary
    defined in th eloaded campaign file.
    """
    
    ### special reactant is specified and it is not a lone element
    if phase_dat[0] == 'sr':

        ### does special reactnat exists in sr_dict
        try:
            sr_dat = sr_dict[phase]
        
        except Exception as e: 
            print('Special reactant not installed:')
            sys.exit(e)

        ### transpose to create [ele, sto] pairs and iterate
        middle = []
        for _ in [list(i) for i in zip(*sr_dat)]: 
            middle.append('   {}{}          {}\n'.format(_[0], ' '*(2-len(_[0])),  format_e(_[1], 5)))

    ### special reactant is a lone element
    else:
        middle = '   {}{}          1.00000E+00\n'.format(phase, ' '*(2-len(phase))),
        
    ### the top and bottom of the reactant block is the same for ele and sr, 
    ### as the reactant is titrated as a single unit (rk1b).    
    top = '\n'.join(['*-----------------------------------------------------------------------------',
        '  reactant=  {}'.format(phase),
        '     jcode=  2               jreac=  0',
        '      morr=  {}      modr=  0.00000E+00'.format(format_e(10**phase_dat[1], 5)),
        '     vreac=  0.00000E+00\n'])

    bottom = '\n'.join(['   endit.',
        '* Reaction',
        '   endit.',
        '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
        '      fkrc=  0.00000E+00',
        '      nrk1=  1                nrk2=  0',
        '      rkb1=  {}      rkb2=  0.00000E+00      rkb3=  0.00000E+00\n'.format(format_e(phase_dat[2], 5))
        ])

    return top + ''.join(middle) + bottom


def build_mineral_rnt(phase, morr, rk1b):
    """
    The function builds a 6i reactant block for mineral 'phase' of type jcode = 0.
    of moles  = morr, and a titration rate relative to xi=1 of rk1b
    """

    ############ example block ##############
    #   *-----------------------------------------------------------------------------
    # reactant= Quartz
    #    jcode=  0               jreac=  0
    #     morr=  9.40100E+01      modr=  0.00000E+00
    #      nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00
    #     fkrc=  0.00000E+00
    #     nrk1=  1                nrk2=  0
    #     rkb1=  9.40100E-03      rkb2=  0.00000E+00      rkb3=  0.00000E+00

    return '\n'.join(['*-----------------------------------------------------------------------------',
                '  reactant= {}'.format(phase),
                '     jcode=  0               jreac=  0',
                '      morr=  {}      modr=  0.00000E+00'.format(format_e(float(morr), 5)),
                '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                '      fkrc=  0.00000E+00',
                '      nrk1=  1',
                '       rk1=  {}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'.format(format_e(rk1b, 5))])


def build_aqueous_rnt(phase, morr, rk1b):

    ######## example block #####################
    # *-----------------------------------------------------------------------------
    #   reactant= Aqueous H2SO4, 0.1 N
    #      jcode=  2               jreac=  0
    #       morr=  1.00000E+00      modr=  0.00000E+00
    #      vreac=  0.00000E+00
    # * Elemental composition
    #    O           5.570895364010290E+01
    #    H           1.111168701265550E+02
    #    C           1.059405461284710E-05
    #    S           5.000000274353950E-02
    #    endit.
    # * Reaction
    #    Aqueous H2SO4, 0.1 N       -1.000000000000000E+00
    #    HCO3-                       1.059405461284710E-05
    #    SO4--                       5.000000274353950E-02
    #    H+                          1.000105995416918E-01
    #    H2O                         5.550842446647936E+01
    #    O2(g)                       2.486902427776272E-04
    #    endit.
    #        nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00
    #       fkrc=  0.00000E+00
    #       nrk1=  1                nrk2=  0
    #       rkb1=  1.00000E+00      rkb2=  0.00000E+00      rkb3=  0.00000E+00
    pass



def build_gas_rnt(phase, morr, rk1b):
    """
    build gas reactant block
    """

    ############# example block ###############
    ### *-----------------------------------------------------------------------------
    ### reactant= CH4(g)
    ### jcode=  4               jreac=  0
    ### morr=  1.50000E-03      modr=  0.00000E+00
    ### nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00
    ### fkrc=  0.00000E+00
    ### nrk1=  1                nrk2=  0
    ### rkb1=  1.00000E+00      rkb2=  0.00000E+00      rkb3=  0.00000E+00

    return '\n'.join(['*-----------------------------------------------------------------------------',
                '  reactant= {}'.format(phase),
                '     jcode=  4               jreac=  0',
                '      morr=  {}      modr=  0.00000E+00'.format(format_e(float(10**morr), 5)),
                '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                '      fkrc=  0.00000E+00',
                '      nrk1=  1',
                '       rk1=  {}       rk2=  0.00000E+00       rk3=  0.00000E+00\n'.format(format_e(rk1b, 5))])

##################################################################
###########################  classes  ############################
##################################################################

class Three_i(object):
    """ 
        Instantiates 3i document template that contains the correct
        format (all run setings).
        Any feature of 6i files can be added to the __init__ function,
        to be made amdendable between campaigns.
    """
    
    def __init__(self, cb,
        iopt4  = '0',    # SS    1 (permit), (ignor)
        iopt11 = '0',    # Auto basis switching   0 (turn on), 1 (turn off)
        iopt17 = '0',    # Pickup file:  -1 (dont write), 0 (write)
        iopt19 = '3',    # pickup type:  0 (normal), 3 (fluid1 set up for fluid mixing)
        iopr1  = '0',
        iopr2  = '0',
        iopr4  = '1',    # incliude all aq species (not just > -100)
        iopr5  = '0',    # dont print aq/H+ ratios
        iopr6  = '-1',   # dont print 99% table
        iopr7  = '-1',   # dont print SI /affinity table
        iopr9  = '0'
        ):
        """
        instantiates three_i constants
        
        """
        self.cb     = cb
        self.iopt4  = iopt4
        self.iopt11 = iopt11
        self.iopt17 = iopt17
        self.iopt19 = iopt19
        self.iopr1 = iopr1
        self.iopr2 = iopr2
        self.iopr4 = iopr4
        self.iopr5 = iopr5
        self.iopr6 = iopr6
        self.iopr7 = iopr7
        self.iopr9 = iopr9

    def write(self, local_name, v_state, v_basis, output_details = 'n'):
        """
        local_name = actual file name
        v_state = dict['state_parameter_name'] = value
        v_basis = dict['basis_species_name']   = value

        output_details = 'n' (normal), 'v' (verbose, for debugging chemical space).
            normal = the instantiation defaults (self.)

        """

        if output_details == 'v':
            ### maximal infomration sought from the 3o file, to added chemiocal space investigations:
            ### note extra space in front of number value. this is needed.
            l_iopt4 = ' 1'  #   turn on SS so that they are listed in 3o loaded sp.
            l_iopr1 = ' 1'
            l_iopr2 = ' 3'
            l_iopr4 = ' 1'
            l_iopr5 = ' 3'
            l_iopr6 = ' 1'
            l_iopr7 = ' 1'
            l_iopr9 = ' 1'
            l_iodb1 = ' 2'
            l_iodb3 = ' 4'
            l_iodb4 = ' 4'
            l_iodb6 = ' 2'


        elif output_details == 'n':
            ### normal olutput sought = instantiation defaults (self.)

            ### no string leading space addition is needed for iopt, 
            ### becuas ei am not intersted in - values there.

            ### adjust leading space for iopr strings, as they may have 
            ### leading negative values
            l_iopt4 = ' '*(2-len(self.iopt4)) + self.iopt4
            l_iopr1 = ' '*(2-len(self.iopr1)) + self.iopr1
            l_iopr2 = ' '*(2-len(self.iopr2)) + self.iopr2
            l_iopr4 = ' '*(2-len(self.iopr4)) + self.iopr4
            l_iopr5 = ' '*(2-len(self.iopr5)) + self.iopr5
            l_iopr6 = ' '*(2-len(self.iopr6)) + self.iopr6
            l_iopr7 = ' '*(2-len(self.iopr7)) + self.iopr7
            l_iopr9 = ' '*(2-len(self.iopr9)) + self.iopr9
            l_iodb1 = ' 0'
            l_iodb3 = ' 0'
            l_iodb4 = ' 0'
            l_iodb6 = ' 0'

        else:
            ### output_details set improperly
            print('Error: {} is not recognized'.format(output_details))
            print('  as a valid output_details value. Must be "n" = ')
            print('  normal or "v" = verbose (for debugging)')
            sys.exit()

        ### write template to file, amending values into the variable vars
        with open(local_name, 'w') as build:
            build.write('EQ3NR input file name= local' + '\n' +
                'endit.' + '\n' +
                '* Special basis switches' + '\n' +
                '    nsbswt=   0' + '\n' +
                '* General' + '\n' +
                '     tempc=  ' + format_e(v_state['T_cel'], 5) + '\n' +
                '    jpres3=   0' + '\n' +
                '     press=  ' + format_e(v_state['P_bar'], 5) + '\n' +
                '       rho=  1.00000E+00' + '\n' +
                '    itdsf3=   0' + '\n' +
                '    tdspkg=  0.00000E+00     tdspl=  0.00000E+00' + '\n' +
                '    iebal3=   1' + '\n' +
                '     uebal= ' + self.cb + '\n' +
                '    irdxc3=   0' + '\n' +
                '    fo2lgi= ' + format_e(v_state['fO2'], 5) + '       ehi=  0.00000E+00' + '\n' +
                '       pei=  0.00000E+00    uredox= None' + '\n' +
                '* Aqueous basis species' + '\n')

            for _ in v_basis.keys():
                if _ == 'H+':
                    build.write('species= {}\n   jflgi= 16    covali=  {}\n'.format(_, v_basis[_]))
                else:
                    build.write('species= {}\n   jflgi=  0    covali=  {}\n'.format(_, format_e(10**v_basis[_], 5)))

            build.write('endit.' + '\n' +
                '* Ion exchangers' + '\n' +
                '    qgexsh=        F' + '\n' +
                '       net=   0' + '\n' +
                '* Ion exchanger compositions' + '\n' +
                '      neti=   0' + '\n' +
                '* Solid solution compositions' + '\n' +
                '      nxti=   0' + '\n' +
                '* Alter/suppress options' + '\n' +
                '     nxmod=   2' + '\n' +
                '   species= METHANE' + '\n' +
                '    option= -1              xlkmod=  0.00000E+00' + '\n' +
                '   species= ETHYLENE(g)' + '\n' +
                '    option= -1              xlkmod=  0.00000E+00' + '\n' +
                '* Iopt, iopg, iopr, and iodb options' + '\n' +
                '*               1    2    3    4    5    6    7    8    9   10' + '\n' +
                '  iopt1-10=     0    0    0   ' + l_iopt4 + '    0    0    0    0    0    0' + '\n' +
                ' iopt11-20=     ' + self.iopt11 + '    0    0    0    0    0    ' + self.iopt17 + '    0    ' + self.iopt19 + '    0' + '\n' +
                '  iopg1-10=     0    0    0    0    0    0    0    0    0    0' + '\n' +
                ' iopg11-20=     0    0    0    0    0    0    0    0    0    0' + '\n' +
                '  iopr1-10=    ' + l_iopr1 + '   ' + l_iopr2 + '    0   ' + l_iopr4 + '   ' + l_iopr5 + '   ' + l_iopr6 + '   ' + l_iopr7 + '    0   ' + l_iopr9 + '    0' + '\n' +
                ' iopr11-20=     0    0    0    0    0    0    0    0    0    0' + '\n' +
                '  iodb1-10=    ' + l_iodb1 + '    0   ' + l_iodb3 + '   ' + l_iodb4 + '    0   ' + l_iodb6 + '    0    0    0    0' + '\n' +
                ' iodb11-20=     0    0    0    0    0    0    0    0    0    0' + '\n' +
                '* Numerical parameters' + '\n' +
                '     tolbt=  0.00000E+00     toldl=  0.00000E+00' + '\n' +
                '    itermx=   0' + '\n' +
                '* Ordinary basis switches' + '\n' +
                '    nobswt=   0' + '\n' +
                '* Saturation flag tolerance' + '\n' +
                '    tolspf=  0.00000E+00' + '\n' +
                '* Aqueous phase scale factor' + '\n' +
                '    scamas=  1.00000E+00')



class Six_i(object):
    """ 
        Instantiates 6i document template that contains the correct
        format (all run setings).
        Any feature of 6i files can be added to the __init__ function,
        to be made amdendable between campaigns
    """
    
    def __init__(self,
        suppress_min = False,   #   mineral suppression
        min_supp_exemp = [],    #   exemptions ot mineral suppression
        iopt1   = '1',          #   0 = closed, 1 = titration, 2 = fluid-centered flow through
        iopt2   = '0',
        iopt3   = '0',
        iopt4   = '1',
        iopt5   = '0',
        iopt6   = '0',          #   clear soldis at first step in rxn progress. When on (1) this can cause titratiosn to fail.
        iopt7   = '0',
        iopt8   = '0',
        iopt9   = '0',
        iopt10  = '0',
        iopr1   = '0',
        iopr2   = '0',
        iopr3   = '0',
        iopr4   = '1',
        iopr5   = '0',
        iopr6   = '-1',
        iopr7   = '1',
        iopr8   = '0',
        iopr9   = '0',
        iopr10  = '0',
        iopr17  = '1'
        ):
        """
        instantiates six_i constants
        
        """
        self.suppress_min     = suppress_min
        self.min_supp_exemp   = min_supp_exemp
        self.iopt1     = ' '*(2-len(iopt1)) + iopt1
        self.iopt2     = ' '*(2-len(iopt2)) + iopt2
        self.iopt3     = ' '*(2-len(iopt3)) + iopt3
        self.iopt4     = ' '*(2-len(iopt4)) + iopt4
        self.iopt5     = ' '*(2-len(iopt5)) + iopt5
        self.iopt6     = ' '*(2-len(iopt6)) + iopt6
        self.iopt7     = ' '*(2-len(iopt7)) + iopt7
        self.iopt8     = ' '*(2-len(iopt8)) + iopt8
        self.iopt9     = ' '*(2-len(iopt9)) + iopt9
        self.iopt10    = ' '*(2-len(iopt10)) + iopt10
        self.iopr1     = ' '*(2-len(iopr1)) + iopr1
        self.iopr2     = ' '*(2-len(iopr2)) + iopr2
        self.iopr3     = ' '*(2-len(iopr3)) + iopr3
        self.iopr4     = ' '*(2-len(iopr4)) + iopr4
        self.iopr5     = ' '*(2-len(iopr5)) + iopr5
        self.iopr6     = ' '*(2-len(iopr6)) + iopr6
        self.iopr7     = ' '*(2-len(iopr7)) + iopr7
        self.iopr8     = ' '*(2-len(iopr8)) + iopr8
        self.iopr9     = ' '*(2-len(iopr9)) + iopr9
        self.iopr10    = ' '*(2-len(iopr10)) + iopr10
        self.iopr17    = ' '*(2-len(iopr10)) + iopr17


    def write(self, local_name, reactants, pickup_lines, temp, output_details = 'm', xi_max = 100, morr = 100, mix_dlxprn = 1, mix_dlxprl = 1, jtemp = '0', additional_sw_rxn = False):
        """ 
        Constructs a 6i file 'local_name' with instantiated constants

        reactants = dictionary of reactant:value pairs. This dictionary has the same structure
            as the camp.target_rnt dict, except it does not contain ranges, as specific values
            on those ranges have already been selected by the na vigator function that built
            the VS postgres table.

        pickup_lines = local 3p files lines

        temp = temperature

        output_details = 'm' (minimal), 'n' (normal), 'v' (verbose, for debugging chemical space).
            normal = the instantiation defaults (self.)

        additional_sw_rxn = True, triggers the inclusion of seawater as an adidtional reactant.
            This is used to allow remixing of seawater when i am also seeking continued mienral interaction

        """

        if output_details == 'm':
            ### minimal output sought:
            pass
        elif output_details == 'v':
            ### maximal infomration sought from the 6o file for debugging
            pass


        ### reactant count
        reactant_n = len(reactants.keys())

        if additional_sw_rxn == True:
            reactant_n += 1


        if jtemp == '0':        
            ### t constant
            tempcb = temp
            ttk1   = '0.00000E+00'
            ttk2   = '0.00000E+00'
        
        elif jtemp == '3':
            ### fluid mixing desired. 
            ### this renders temp (target end temp of the reaction) something to be solved for 
            ### via xi. must check that it is possible (cant reach 25 C of the two fluids being mixed
            ### are above that.)

            ### tempcb = high T fluid temp. this is listed in the pickup lines about 
            ### to be attched to the bottom.

            for _ in pickup_lines:
                if '    tempci=  ' in _:
                    tempcb = grab_str(_, -1)

            ### temp of fluid 2 (reactant block seawater)
            ttk2   = '2.00000E+00' 
            format_e(float(temp), 5)
            
            ### mass ratio fluid 1 to fluid 2 at xi = 1. THis is solved for the desired T_sys = temp
            ### T_sys = (T_vfl*ttk1 + Xi*T_sw) / (Xi + ttk1)
            ### To get T)sys to taget 'temp' at Xi  = 1:
            ###     ttk1 = (T_sw - temp) / (temp - T_vfl)
            ttk1 = '1.00000E+00'
            ttk1 = format_e((float(ttk2) - temp) / (temp - float(tempcb)), 5)

            ### reset ximax so the xi_max = 1 lands on correct system temp, given ttk1
            xi_max = 1


        with open(local_name, 'w') as build:
            build.write('\n'.join([
                'EQ3NR input file name= local',
                'endit.',
                '     jtemp=  {}'.format(jtemp),
                '    tempcb=  {}'.format(format_e(float(tempcb), 5)),
                '      ttk1=  {}      ttk2=  {}'.format(ttk1, ttk2),
                '    jpress=  0',
                '    pressb=  0.00000E+00',
                '      ptk1=  0.00000E+00      ptk2=  0.00000E+00',
                '      nrct=  {}\n'.format(str(reactant_n))]))


            if len(reactants) > 0:
                for _ in reactants.keys():
                    ### This assumes that the reactant info read from the vs table
                    ### is passed in the same manner as the table listed in the campaign .py file
                    if reactants[_][0] == 'ele' or reactants[_][0] =='sr': 
                        ### element or special reactant
                        ### special reactants must be in sr_dict:
                        build.write(build_special_rnt(_, reactants[_]))
                    # elif reactants[_][0] == 'sr':
                    #     ### special reactant
                        # build.write(build_special_rnt(_, reactants[_][1], reactants[_][2]))
                    elif reactants[_][0] == 'solid':
                        ### mineral reactant
                        build.write(build_mineral_rnt(_, reactants[_][1], reactants[_][2]))
                    elif reactants[_][0] == 'gas':
                        ### gas reactant
                        build.write(build_gas_rnt(_, reactants[_][1], reactants[_][2]))
                    
                    # elif reactants[_][0] == 'Gale':
                    #     load_gale
                    #     build.write
            

            if additional_sw_rxn == True:
               
                ### drop in seawater as an additional reactant, to exhaustion.
                ### this is obviously incomplete, as i should be able to pick which fluid i want to
                ### add as an aditional reaction
                build.write(
                    '\n'.join([
                    '*-----------------------------------------------------------------------------',
                    '  reactant= Fluid 2',
                    '     jcode=  2               jreac=  0',
                    '      morr=  1.00000E+10      modr=  0.00000E+00',
                    '     vreac=  0.10000E+01',
                    '* Elemental composition',
                    '   O           5.562748395365903E+01',
                    '   Al          2.000000039235638E-08',
                    '   Br          8.400000000320019E-07',
                    '   Ca          1.020000004340294E-02',
                    '   Cl          5.339131409252369E-01',
                    '   Fe          1.530000029742448E-09',
                    '   H           1.110191390994818E+02',
                    '   C           2.300000303802816E-03',
                    '   K           2.300000001660159E-03',
                    '   Mg          5.270000005630820E-02',
                    '   N           3.000010000000001E-07',
                    '   Na          4.640000001062417E-01',
                    '   S           2.790000003661272E-02',
                    '   Si          1.600000002691423E-04',
                    '   endit.',
                    '* Reaction',
                    '   Fluid 2                    -1.000000000000000E+00',
                    '   H2O                         5.550846244103924E+01',
                    '   Al+3                        2.000000039235638E-08',
                    '   Br-                         8.400000000320019E-07',
                    '   Ca+2                        1.020000004340294E-02',
                    '   Cl-                         5.339131409252369E-01',
                    '   Fe+2                        3.000000003396551E-11',
                    '   H+                         -8.578380445936970E-05',
                    '   HCO3-                       2.300000003802816E-03',
                    '   K+                          2.300000001660159E-03',
                    '   Mg+2                        5.270000005630820E-02',
                    '   NO3-                        3.000000000000001E-07',
                    '   Na+                         4.640000001062417E-01',
                    '   SO4-2                       2.790000003661272E-02',
                    '   SiO2,AQ                     1.600000002691423E-04',
                    '   O2(g)                       1.003062307023703E-04',
                    '   NH4+                        1.000000000021125E-12',
                    '   Fe+3                        1.500000029708482E-09',
                    '   METHANE,AQ                  3.000000000000001E-10',
                    '   endit.',
                    '       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00',
                    '      fkrc=  0.00000E+00',
                    '      nrk1=  1                nrk2=  0',
                    '      rkb1=  1.00000E+00      rkb2=  0.00000E+00      rkb3=  0.00000E+00\n']))

            else:
                ### no reactants, closed system                    
                self.iopt1 = ' 0'

            build.write(
                '\n'.join(['*-----------------------------------------------------------------------------',
                '    xistti=  0.00000E+00    ximaxi=  {}'.format(format_e(float(xi_max), 5)),
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
                    [self.iopt1, self.iopt2, self.iopt3, self.iopt4, self.iopt5, self.iopt6, self.iopt7, self.iopt8, self.iopt9, self.iopt10]]) + '\n')
            build.write(' iopt11-20=     0    0    0    0    0   -1    0   -1    0    0\n')
            build.write(
                '  iopr1-10=    ' + '   '.join([_ for _ in 
                    [self.iopr1, self.iopr2, self.iopr3, self.iopr4, self.iopr5, self.iopr6, self.iopr7, self.iopr8, self.iopr9, self.iopr10]]) + '\n')
            build.write('\n'.join([' iopr11-20=     0    0    0    0    0    0   {}    0    0    0'.format(self.iopr17),
                                '  iodb1-10=     0    0    0    0    0    0    0    0    0    0',
                                ' iodb11-20=     0    0    0    0    0    0    0    0    0    0\n']))



            ### Handle mineral supression
            if self.suppress_min:
                build.write('     nxopt=  1\n    option= All    \n')
            else:
                build.write('     nxopt=  0\n')

                

            ### handle exemptions to suppressions    
            if len(self.min_supp_exemp) > 0:
                ### list specific mineral exeptions to the 'all' suppression statement above
                build.write('    nxopex=  {}\n'.format(str(int(len(self.min_supp_exemp)))))
                for _ in self.min_supp_exemp:
                    build.write('   species= {}\n'.format(_))


            
            elif len(self.min_supp_exemp) == 0 and self.suppress_min:
                build.write('    nxopex=  0\n')



            build.write('\n'.join([
                '      nffg=  0',
                '    nordmx=   6',
                '     tolbt=  0.00000E+00     toldl=  0.00000E+00',
                '    itermx=   0',
                '    tolxsf=  0.00000E+00',
                '    tolsat=  0.00000E+00',
                '    ntrymx=   0',
                '    dlxmx0=  0.00000E+00',
                '    dlxdmp=  0.00000E+00',
                '*-----------------------------------------------------------------------------\n']))

            ### load pickup lines
            for _ in pickup_lines:
                build.write(_)
