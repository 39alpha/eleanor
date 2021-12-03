### tool_room
### Developed by Tucker Ely 
### 2018-
### general EQ3/6 dependencies

###  contains functions and variables
### related to running and manipulating EQ3/6.
### This file is my attempt to stremaline the development 
### process, as the functions contained herein are 
### commonily duplicated between projects.
### the 'local' here refers to its use on my local machine
### differentiating it from the copy being built within
### the NPP project


import os, shutil, sys, re, math, itertools

# from memory_profiler import profile
import cProfile
import pstats



import numpy as np
from subprocess import * 
from time import *
from db_comms import *


os.environ['EQ36CO']="/Users/tuckerely/NPP_dev/EQ3_6v8.0a/bin"
os.environ['PATH']="{}:{}".format(os.environ['PATH'], os.environ['EQ36CO'])
os.environ['EQ36DA']="/Users/tuckerely/NPP_dev/EQ3_6v8.0a/db"




##################################################################
#########################  small picies  #########################
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
    code_path= '/Users/tuckerely/NPP_dev/EQ3_6v8.0a/bin/runeq{}'.format(ver)
    process = Popen(['/bin/csh', code_path, suffix, input_file], stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()

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

class three_i:
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




class six_i:
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


















##################################################################
#####################  Standard Thermo data  #####################
##################################################################

### Thermo constants for  A = RTln(K/Q)
euler       = 2.7182818284 
kelvin      = 273.15                         #    at 0 C
cal_convert = 0.23900574
R           = 8.31446 * cal_convert          #    with calory conversion (cal K-1 mol-1)


### Molecular weights
O_mwt     = 15.99940 
C_mwt     = 12.01100
S_mwt     = 32.06600
Al_mwt     = 26.98154
Ca_mwt     = 40.07800
K_mwt     = 39.09830
Fe_mwt     = 55.84700
Mg_mwt     = 24.30500
Mn_mwt     = 54.93085
Na_mwt     = 22.98977
Ni_mwt     = 58.69000
Si_mwt     = 28.08550
O_mwt     = 15.99940
H_mwt     = 1.00794
Ti_mwt     = 47.88000
P_mwt     = 30.97362



### wt_dict = dictionary of oxide to elemnt conversions.
###  key = oxide name, value = [ele_name, ele_sto, O_sto, mw_oxide]
wt_dict = {
    'SiO2':  ['Si', 1, 2, Si_mwt       + (2.0*O_mwt)],
    'TiO2':  ['Ti', 1, 2, Ti_mwt       + (2.0*O_mwt)],
    'FeO':   ['Fe', 1, 1, Fe_mwt       + O_mwt],
    'Fe2O3': ['Fe', 2, 3, (2.0*Fe_mwt) + (3.0*O_mwt)],
    'MgO':   ['Mg', 1, 1, Mg_mwt       + O_mwt],
    'Al2O3': ['Al', 2, 3, (2.0*Al_mwt) + (3.0*O_mwt)],
    'CaO':   ['Ca', 1, 1, Ca_mwt       + O_mwt],
    'Na2O':  ['Na', 2, 1, (2.0*Na_mwt) + O_mwt],
    'K2O':   ['K',  2, 1, (2.0*K_mwt)  + O_mwt],
    'P2O5':  ['P',  2, 5, (2.0*P_mwt)  + (5.0*O_mwt)],
    'MnO':   ['Mn', 1, 1, Mn_mwt       + O_mwt],
    'CO2':   ['C',  1, 2, C_mwt        + (2.0*O_mwt)],
    'S':     ['S',  1, 0, S_mwt],
    'H2O':   ['H',  2, 1, (2.0*H_mwt)  + O_mwt]}
  


# mw = {
#     'O':    15.99940,
#     'Ag':  107.86820,
#     'Al':   26.98154,
#     'Am':  243.00000,
#     'Ar':   39.94800,
#     'Au':  196.96654,
#     'B':    10.81100,
#     'Ba':  137.32700,
#     'Be':    9.01218,
#     'Bi':  208.98000,
#     'Br':   79.90400,
#     'Ca':   40.07800,
#     'Cd':  112.41100,
#     'Ce':  140.11500,
#     'Cl':   35.45270,
#     'Co':   58.93320,
#     'Cr':   51.99610,
#     'Cs':  132.90543,
#     'Cu':   63.54600,
#     'Dy':  162.50000,
#     'Er':  167.26000,
#     'Eu':  151.96500,
#     'F':    18.99840,
#     'Fe':   55.84700,
#     'Fr':  223.00000,
#     'Ga':   69.72300,
#     'Gd':  157.25000,
#     'H':     1.00794,
#     'As':   74.92159,
#     'C':    12.01100,
#     'P':    30.97362,
#     'He':    4.00206,
#     'Hf':  178.49000,
#     'Hg':  200.59000,
#     'Ho':  164.93032,
#     'I':   126.90447,
#     'In':  114.82000,
#     'K':    39.09830,
#     'Kr':   83.80000,
#     'La':  138.90550,
#     'Li':    6.94100,
#     'Lu':  174.96700,
#     'Mg':   24.30500,
#     'Mn':   54.93085,
#     'Mo':   95.94000,
#     'N':    14.00674,
#     'Na':   22.98977,
#     'Nb':   92.90600,
#     'Nd':  144.24000,
#     'Ne':   20.17970,
#     'Ni':   58.69000,
#     'Pb':  207.20000,
#     'Pd':  106.42000,
#     'Pm':  145.00000,
#     'Pr':  140.90765,
#     'Pt':  195.08000,
#     'Ra':  226.02500,
#     'Rb':   85.46780,
#     'Re':  186.20700,
#     'Rh':  102.90600,
#     'Rn':  222.00000,
#     'Ru':  101.07000,
#     'S':    32.06600,
#     'Sb':  127.76000,
#     'Sc':   44.95591,
#     'Se':   78.96000,
#     'Si':   28.08550,
#     'Sm':  150.36000,
#     'Sn':  118.71000,
#     'Sr':   87.62000,
#     'Tb':  158.92534,
#     'Tc':   98.00000,
#     'Th':  232.03800,
#     'Ti':   47.88000,
#     'Tl':  204.38330,
#     'Tm':  168.93421,
#     'U':   238.02890,
#     'V':    50.94150,
#     'W':   183.85000,
#     'Xe':  131.29000,
#     'Y':    88.90585,
#     'Yb':  173.04000,
#     'Zn':   65.39000,
#     'Zr':   91.22400
#     }



# ##### Basis/ele dict
# basis_to_ele_dict = {'H+':'H+',
#             'Ag+': 'Ag',
#             'Al+3': 'Al',
#             'Am+3': 'Am',
#             'Ar,AQ': 'Ar',
#             'Au+': 'Au',
#             'B(OH)3,AQ': 'B',
#             'Ba+2': 'Ba',
#             'Be+2': 'Be',
#             'Bi+3': 'Bi',
#             'Br-': 'Br',
#             'Ca+2': 'Ca',
#             'Cd+2': 'Cd',
#             'Ce+3': 'Ce',
#             'Cl-': 'Cl',
#             'Co+2': 'Co',
#             'CrO4-2': 'Cr',
#             'Cs+': 'Cs',
#             'Cu+2': 'Cu',
#             'Dy+3': 'Dy',
#             'Er+3': 'Er',
#             'Eu+2': 'Eu',
#             'F-': 'F',
#             'Fe+2': 'Fe',
#             'Fr+': 'Fr',
#             'Ga+3': 'Ga',
#             'Gd+3': 'Gd',
#             'H2AsO4-': 'As',
#             'HCO3-': 'C',
#             'HPO4-2': 'P',
#             'He,AQ': 'He',
#             'Hf+4': 'Hf',
#             'Hg+2': 'Hg',
#             'Ho+3': 'Ho',
#             'I-': 'I',
#             'In+3': 'In',
#             'K+': 'K',
#             'Kr,AQ': 'Kr',
#             'La+3': 'La',
#             'Li+': 'Li',
#             'Lu+3': 'Lu',
#             'Mg+2': 'Mg',
#             'Mn+2': 'Mn',
#             'MoO4-2': 'Mo',
#             'NO3-': 'N',
#             'Na+': 'Na',
#             'NbO3-': 'Nb',
#             'Nd+3': 'Nd',
#             'Ne,AQ': 'Ne',
#             'Ni+2': 'Ni',
#             'Pb+2': 'Pb',
#             'Pd+2': 'Pd',
#             'Pm+3': 'Pm',
#             'Pr+3': 'Pr',
#             'Pt+2': 'Pt',
#             'Ra+2': 'Ra',
#             'Rb+': 'Rb',
#             'ReO4-': 'Re',
#             'Rh+2': 'Rh',
#             'Rn,AQ': 'Rn',
#             'Ru+3': 'Ru',
#             'SO4-2': 'S',
#             'SbO2-': 'Sb',
#             'Sc+3': 'Sc',
#             'SeO3-2': 'Se',
#             'SiO2,AQ': 'Si',
#             'Sm+3': 'Sm',
#             'Sn+2': 'Sn',
#             'Sr+2': 'Sr',
#             'Tb+3': 'Tb',
#             'TcO4-': 'Tc',
#             'Th+4': 'Th',
#             'Ti+4': 'Ti',
#             'Tl+': 'Tl',
#             'Tm+3': 'Tm',
#             'U+4': 'U',
#             'VO+2': 'V',
#             'WO4-2': 'W',
#             'Xe,AQ': 'Xe',
#             'Y+3': 'Y',
#             'Yb+3': 'Yb',
#             'Zn+2': 'Zn',
#             'Zr+4': 'Zr'}



### basis, converted to its constiuent elemnts with stoichiometry
basis_to_ele_dict_2 = {
            'H2O':         {  'H':  2, 'O': 1},
            'Ag+':         {  'Ag':  1},
            'Al+3':        {  'Al':  1},
            'Am+3':        {  'Am':  1},
            'Ar,AQ':       {  'Ar':  1},
            'Au+':         {  'Au':  1},
            'B(OH)3,AQ':   {  'B':  1, 'H': 3, 'O': 3},
            'Ba+2':        {  'Ba':  1},
            'Be+2':        {  'Be':  1},
            'Bi+3':        {  'Bi':  1},
            'Br-':         {  'Br':  1},
            'Ca+2':        {  'Ca':  1},
            'Cd+2':        {  'Cd':  1},
            'Ce+3':        {  'Ce':  1},
            'Cl-':         {  'Cl':  1},
            'Co+2':        {  'Co':  1},
            'CrO4-2':      {  'Cr':  1, 'O': 4},
            'Cs+':         {  'Cs':  1},
            'Cu+2':        {  'Cu':  1},
            'Dy+3':        {  'Dy':  1},
            'Er+3':        {  'Er':  1},
            'Eu+2':        {  'Eu':  1},
            'F-':          {  'F':  1},
            'Fe+2':        {  'Fe':  1},
            'Fr+':         {  'Fr':  1},
            'Ga+3':        {  'Ga':  1},
            'Gd+3':        {  'Gd':  1},
            'H+':          {  'H':  1},
            'H2AsO4-':     {  'As':  1, 'H': 2, 'O': 4},
            'HCO3-':       {  'C':  1, 'H': 1, 'O': 3},
            'HPO4-2':      {  'H':  1, 'O': 4, 'P': 1},
            'He,AQ':       {  'He':  1},
            'Hf+4':        {  'Hf':  1},
            'Hg+2':        {  'Hg':  1},
            'Ho+3':        {  'Ho':  1},
            'I-':          {  'I':  1},
            'In+3':        {  'In':  1},
            'K+':          {  'K':  1},
            'Kr,AQ':       {  'Kr':  1},
            'La+3':        {  'La':  1},
            'Li+':         {  'Li':  1},
            'Lu+3':        {  'Lu':  1},
            'Mg+2':        {  'Mg':  1},
            'Mn+2':        {  'Mn':  1},
            'MoO4-2':      {  'Mo':  1, 'O': 4},
            'NO3-':        {  'N':  1, 'O': 3},
            'Na+':         {  'Na':  1},
            'NbO3-':       {  'Nb':  1, 'O': 3},
            'Nd+3':        {  'Nd':  1},
            'Ne,AQ':       {  'Ne':  1},
            'Ni+2':        {  'Ni':  1},
            'Pb+2':        {  'Pb':  1},
            'Pd+2':        {  'Pd':  1},
            'Pm+3':        {  'Pm':  1},
            'Pr+3':        {  'Pr':  1},
            'Pt+2':        {  'Pt':  1},
            'Ra+2':        {  'Ra':  1},
            'Rb+':         {  'Rb':  1},
            'ReO4-':       {  'O':  4, 'Re': 1},
            'Rh+2':        {  'Rh':  1},
            'Rn,AQ':       {  'Rn':  1},
            'Ru+3':        {  'Ru':  1},
            'SO4-2':       {  'O':  4, 'S': 1},
            'SbO2-':       {  'Sb':  1, 'O': 2},
            'Sc+3':        {  'Sc':  1},
            'SeO3-2':      {  'O':  3, 'Se': 1},
            'SiO2,AQ':     {  'O':  2, 'Si': 1},
            'Sm+3':        {  'Sm':  1},
            'Sn+2':        {  'Sn':  1},
            'Sr+2':        {  'Sr':  1},
            'Tb+3':        {  'Tb':  1},
            'TcO4-':       {  'Tc':  1, 'O': 4},
            'Th+4':        {  'Th':  1},
            'Ti+4':        {  'Ti':  1},
            'Tl+':         {  'Tl':  1},
            'Tm+3':        {  'Tm':  1},
            'U+4':         {  'U':  1},
            'VO+2':        {  'O':  1, 'V': 1},
            'WO4-2':       {  'O':  4, 'W': 1},
            'Xe,AQ':       {  'Xe':  1},
            'Y+3':         {  'Y':  1},
            'Yb+3':        {  'Yb':  1},
            'Zn+2':        {  'Zn':  1},
            'Zr+4':        {  'Zr':  1},
            'O2(g)':       {  'O':  2},



            'NH4+':        {  'H':  4, 'N': 1},
            'Ag+2':        {  'Ag':  1},
            'AsO2-':       {  'As':  1, 'O': 2},
            'H2AsO3-':     {  'As':  1, 'H': 2, 'O': 3},
            'Au+3':        {  'Au':  1},
            'Br3-':        {  'Br':  3},
            'HBrO,AQ':     {  'Br':  1, 'H': 1, 'O': 1},
            'BrO3-':       {  'Br':  1, 'O': 3},
            'BrO4-':       {  'Br':  1, 'O': 4},
            'Ce+2':        {  'Ce':  1},
            'Ce+4':        {  'Ce':  1},
            'CN-':         {  'C':  1, 'N': 1},
            'CO,AQ':       {  'C':  1, 'O': 1},
            'ClO-':        {  'Cl':  1, 'O': 1},
            'ClO2-':       {  'Cl':  1, 'O': 2},
            'ClO3-':       {  'Cl':  1, 'O': 3},
            'ClO4-':       {  'Cl':  1, 'O': 4},
            'Co+3':        {  'Co':  1},
            'Cr+2':        {  'Cr':  1},
            'Cr+3':        {  'Cr':  1},
            'Cu+':         {  'Cu':  1},
            'Dy+2':        {  'Dy':  1},
            'Dy+4':        {  'Dy':  1},
            'Er+2':        {  'Er':  1},
            'Er+4':        {  'Er':  1},
            'Eu+3':        {  'Eu':  1},
            'Eu+4':        {  'Eu':  1},
            'Fe+3':        {  'Fe':  1},
            'H2,AQ':       {  'H':  2},
            'H2O2,AQ':     {  'H':  2, 'O': 2},
            'Ho+2':        {  'Ho':  1},
            'Hg2+2':       {  'Hg':  2},
            'I3-':         {  'I':  3},
            'IO-':         {  'I':  1, 'O': 1},
            'IO3-':        {  'I':  1, 'O': 3},
            'IO4-':        {  'I':  1, 'O': 4},
            'La+2':        {  'La':  1},
            'Lu+4':        {  'Lu':  1},
            'METHANE,AQ':  {  'C':  1, 'H': 4},
            'Mn+3':        {  'Mn':  1},
            'MnO4-':       {  'Mn':  1, 'O': 4},
            'MnO4-2':      {  'Mn':  1, 'O': 4},
            'N2H5+':       {  'N':  2, 'H': 5},
            'N2,AQ':       {  'N':  2},
            'N2O2-2':      {  'N':  2, 'O': 2},
            'NO2-':        {  'N':  1, 'O': 2},
            'Nd+2':        {  'Nd':  1},
            'Nd+4':        {  'Nd':  1},
            'O2,AQ':       {  'O':  2},
            'OCN-':        {  'O':  1, 'C': 1, 'N': 1},
            'H3PO2,AQ':    {  'H':  3, 'P': 1, 'O': 2},
            'H3PO3,AQ':    {  'H':  3, 'P': 1, 'O': 3},
            'Pm+2':        {  'Pm':  1},
            'Pm+4':        {  'Pm':  1},
            'Pr+2':        {  'Pr':  1},
            'Pr+4':        {  'Pr':  1},
            'Rh+3':        {  'Rh':  1},
            'Ru+2':        {  'Ru':  1},
            'RuO4-2':      {  'Ru':  1, 'O': 4},
            'S2-2':        {  'S':  2},
            'HS-':         {  'H':  1, 'S': 1},
            'SCN-':        {  'S':  1, 'C': 1, 'N': 1},
            'SeO4-2':      {  'O':  4, 'Se': 1},
            'HSe-':        {  'H':  1, 'Se': 1},
            'SeCN-':       {  'Se':  1, 'C': 1, 'N': 1},
            'SiF6-2':      {  'F':  6, 'Si': 1},
            'Sm+2':        {  'Sm':  1},
            'Sm+4':        {  'Sm':  1},
            'Tb+2':        {  'Tb':  1},
            'Tb+4':        {  'Tb':  1},
            'Ti+3':        {  'Ti':  1},
            'Tl+3':        {  'Tl':  1},
            'Tm+2':        {  'Tm':  1},
            'Tm+4':        {  'Tm':  1},
            'U+3':         {  'U':  1},
            'UO2+':        {  'O':  2, 'U': 1},
            'UO2+2':       {  'U':  1, 'O': 2},
            'VO2+':        {  'O':  2, 'V': 1},
            'V+2':         {  'V':  1},
            'V+3':         {  'V':  1},
            'H2VO4-':      {  'H':  2, 'O': 4, 'V': 1},
            'Yb+2':        {  'Yb':  1},
            'Yb+4':        {  'Yb':  1},



            'Ag(CO3)2-3': {'Ag':1, 'C':2, 'O':6},
            'Ag(CO3)-': {'Ag':1, 'C':1, 'O':3},
            'AgCl,AQ': {'Ag':1, 'Cl':1},
            'AgCl2-': {'Ag':1, 'Cl':2},
            'AgCl3-2': {'Ag':1, 'Cl':3},
            'AgCl4-3': {'Ag':1, 'Cl':4},
            'AgF,AQ': {'Ag':1, 'F':1},
            'Ag(HS)2-': {'Ag':1, 'S':2, 'H':2},
            'AlOH+2': {'Al':1, 'H':1, 'O':1},
            'AlO+': {'Al':1, 'O':1},
            'HAlO2,AQ': {'Al':1, 'H':1, 'O':2},
            'AlO2-': {'Al':1, 'O':2},
            'AgNO3,AQ': {'Ag':1, 'N':1, 'O':3},
            'HAsO2,AQ': {'H':1, 'O':2, 'As':1},
            'HAsO4-2': {'As':1, 'H':1, 'O':4},
            'Au(HS)2-': {'Au':1, 'H':2, 'S':2},
            'AuCl,AQ': {'Au':1, 'Cl':1},
            'AuCl2-': {'Au':1, 'Cl':2},
            'AuCl3-2': {'Au':1, 'Cl':3},
            'AuCl4-': {'Au':1, 'Cl':4},
            'BO2-': {'B':1, 'O':2},
            'Ba(CO3),AQ': {'Ba':1, 'C':1, 'O':3},
            'BaCl+': {'Ba':1, 'Cl':1},
            'BaF+': {'Ba':1, 'F':1},
            'CO2,AQ': {'C':1, 'O':2},
            'CO3-2': {'C':1, 'O':3},
            'Ca(CO3),AQ': {'C':1, 'Ca':1, 'O':3},
            'CaCl+': {'Ca':1, 'Cl':1},
            'CaCl2,AQ': {'Ca':1, 'Cl':2},
            'CaF+': {'Ca':1, 'F':1},
            'Ca(HCO3)+': {'C':1, 'Ca':1, 'H':1, 'O':3},
            'Ca(HSiO3)+': {'Ca':1, 'H':1, 'O':3, 'Si':1},
            'CaOH+': {'Ca':1, 'H':1, 'O':1},
            'CaSO4,AQ': {'Ca':1, 'O':4, 'S':1},
            'CeBr+2': {'Ce':1, 'Br':1},
            'HCl,AQ': {'Cl':1, 'H':1},
            'HClO,AQ': {'Cl':1, 'H':1, 'O':1},
            'HCN,AQ': {'C':1, 'H':1, 'N':1},
            'Cr2O7-2': {'Cr':2, 'O':7},
            'HCrO4-': {'Cr':1, 'H':1, 'O':4},
            'CsBr,AQ': {'Br':1, 'Cs':1},
            'CsCl,AQ': {'Cl':1, 'Cs':1},
            'CsI,AQ': {'Cs':1, 'I':1},
            'CuOH+': {'Cu':1, 'H':1, 'O':1},
            'CuO,AQ': {'Cu':1, 'O':1},
            'HCuO2-': {'Cu':1, 'H':1, 'O':2},
            'CuO2-2': {'Cu':1, 'O':2},
            'CuCl+': {'Cu':1, 'Cl':1},
            'CuCl2,AQ': {'Cu':1, 'Cl':2},
            'CuCl3-': {'Cu':1, 'Cl':3},
            'CuCl4-2': {'Cu':1, 'Cl':4},
            'CuF+': {'Cu':1, 'F':1},
            'CuCl,AQ': {'Cu':1, 'Cl':1},
            'CuCl2-': {'Cu':1, 'Cl':2},
            'CuCl3-2': {'Cu':1, 'Cl':3},
            'FeCl+': {'Cl':1, 'Fe':1},
            'FeCl+2': {'Cl':1, 'Fe':1},
            'FeCl2,AQ': {'Cl':2, 'Fe':1},
            'FeF+': {'F':1, 'Fe':1},
            'FeF+2': {'F':1, 'Fe':1},
            'HFeO2,AQ': {'Fe':1, 'H':1, 'O':2},
            'HFeO2-': {'Fe':1, 'H':1, 'O':2},
            'FeO2-': {'Fe':1, 'O':2},
            'FeOH+2': {'Fe':1, 'H':1, 'O':1},
            'FeO+': {'Fe':1, 'O':1},
            'FeOH+': {'Fe':1, 'H':1, 'O':1},
            'FeO,AQ': {'Fe':1, 'O':1},
            'HF,AQ': {'F':1, 'H':1},
            'HF2-': {'F':2, 'H':1},
            'HO2-': {'H':1, 'O':2},
            'HSeO3-': {'H':1, 'O':3, 'Se':1},
            'H2SeO3,AQ': {'H':2, 'O':3, 'Se':1},
            'HSeO4-': {'H':1, 'O':4, 'Se':1},
            'HSiO3-': {'H':1, 'O':3, 'Si':1},
            'KBr,AQ': {'Br':1, 'K':1},
            'KCl,AQ': {'Cl':1, 'K':1},
            'KHSO4,AQ': {'H':1, 'K':1, 'O':4, 'S':1},
            'KI,AQ': {'I':1, 'K':1},
            'KOH,AQ': {'H':1, 'K':1, 'O':1},
            'KSO4-': {'K':1, 'O':4, 'S':1},
            'LiCl,AQ': {'Cl':1, 'Li':1},
            'Mg(CO3),AQ': {'C':1, 'Mg':1, 'O':3},
            'Mg(HSiO3)+': {'Mg':1, 'H':1, 'O':3, 'Si':1},
            'MgOH+': {'H':1, 'Mg':1, 'O':1},
            'MgCl+': {'Cl':1, 'Mg':1},
            'MgF+': {'F':1, 'Mg':1},
            'Mg(HCO3)+': {'C':1, 'H':1, 'Mg':1, 'O':3},
            'MgSO4,AQ': {'Mg':1, 'O':4, 'S':1},
            'MnOH+': {'Mn':1, 'O':1, 'H':1},
            'MnO,AQ': {'Mn':1, 'O':1},
            'HMnO2-': {'Mn':1, 'O':2, 'H':1},
            'MnO2-2': {'Mn':1, 'O':2},
            'MnF+': {'Mn':1, 'F':1},
            'MnCl+': {'Cl':1, 'Mn':1},
            'MnSO4,AQ': {'Mn':1, 'O':4, 'S':1},
            'NH3,AQ': {'H':3, 'N':1},
            'N2H6+2': {'N':2, 'H':6},
            'HN2O2-': {'N':2, 'O':2, 'H':1},
            'H2N2O2,AQ': {'H':2, 'N':2, 'O':2},
            'HNO2,AQ': {'N':1, 'O':2, 'H':1},
            'HNO3,AQ': {'H':1, 'N':1, 'O':3},
            'NaBr,AQ': {'Br':1, 'Na':1},
            'NaCl,AQ': {'Cl':1, 'Na':1},
            'NaF,AQ': {'F':1, 'Na':1},
            'NaHSiO3,AQ': {'H':1, 'Na':1, 'O':3, 'Si':1},
            'NaI,AQ': {'I':1, 'Na':1},
            'NaOH,AQ': {'H':1, 'Na':1, 'O':1},
            'NaSO4-': {'Na':1, 'O':4, 'S':1},
            'NiCl+': {'Cl':1, 'Ni':1},
            'OH-': {'H':1, 'O':1},
            'PO4-3': {'O':4, 'P':1},
            'H2PO4-': {'H':2, 'O':4, 'P':1},
            'H3PO4,AQ': {'H':3, 'O':4, 'P':1},
            'H2PO2-': {'H':2, 'P':1, 'O':2},
            'HPO3-2': {'H':1, 'O':3, 'P':1},
            'H2PO3-': {'H':2, 'P':1, 'O':3},
            'P2O7-4': {'P':2, 'O':7},
            'HP2O7-3': {'H':1, 'O':7, 'P':2},
            'H2P2O7-2': {'H':2, 'O':7, 'P':2},
            'H3P2O7-': {'H':3, 'O':7, 'P':2},
            'H4P2O7,AQ': {'H':4, 'O':7, 'P':2},
            'PbCl+': {'Cl':1, 'Pb':1},
            'PbCl2,AQ': {'Cl':2, 'Pb':1},
            'PbCl3-': {'Cl':3, 'Pb':1},
            'PbCl4-2': {'Cl':4, 'Pb':1},
            'PbOH+': {'Pb':1, 'O':1, 'H':1},
            'PbO,AQ': {'Pb':1, 'O':1},
            'HPbO2-': {'Pb':1, 'O':2, 'H':1},
            'PbF+': {'Pb':1, 'F':1},
            'PbF2,AQ': {'Pb':1, 'F':2},
            'Pb(HS)2,AQ': {'Pb':1, 'S':2, 'H':2},
            'Pb(HS)3-': {'Pb':1, 'S':3, 'H':3},
            'RbBr,AQ': {'Br':1, 'Rb':1},
            'RbCl,AQ': {'Cl':1, 'Rb':1},
            'RbF,AQ': {'F':1, 'Rb':1},
            'RbI,AQ': {'I':1, 'Rb':1},
            'HSbO2,AQ': {'Sb':1, 'H':1, 'O':2},
            'H2S,AQ': {'H':2, 'S':1},
            'SO2,AQ': {'O':2, 'S':1},
            'HSO4-': {'H':1, 'O':4, 'S':1},
            'Ru(OH)+': {'Ru':1, 'H':1, 'O':1},
            'RuO,AQ': {'Ru':1, 'O':1},
            'RuO+': {'Ru':1, 'O':1},
            'RuOH+2': {'Ru':1, 'O':1, 'H':1},
            'Sr(CO3),AQ': {'C':1, 'O':3, 'Sr':1},
            'SrCl+': {'Cl':1, 'Sr':1},
            'SrF+': {'F':1, 'Sr':1},
            'UOH+2': {'U':1, 'O':1, 'H':1},
            'UO+': {'U':1, 'O':1},
            'HUO2,AQ': {'U':1, 'O':2, 'H':1},
            'UO2-': {'U':1, 'O':2},
            'U(OH)+3': {'U':1, 'O':1, 'H':1},
            'UO+2': {'U':1, 'O':1},
            'HUO2+': {'U':1, 'O':2, 'H':1},
            'UO2,AQ': {'U':1, 'O':2},
            'HUO3-': {'U':1, 'O':3, 'H':1},
            'UO2OH,AQ': {'U':1, 'O':3, 'H':1},
            'UO3-': {'U':1, 'O':3},
            'UO2OH+': {'U':1, 'O':3, 'H':1},
            'UO3,AQ': {'U':1, 'O':3},
            'HUO4-': {'U':1, 'O':4, 'H':1},
            'UO4-2': {'U':1, 'O':4},
            'VOH+2': {'V':1, 'O':1, 'H':1},
            'HVO4-2': {'H':1, 'O':4, 'V':1},
            'ZnCl+': {'Cl':1, 'Zn':1},
            'ZnCl2,AQ': {'Cl':2, 'Zn':1},
            'ZnCl3-': {'Cl':3, 'Zn':1},
            'ZnOH+': {'Zn':1, 'O':1, 'H':1},
            'ZnO,AQ': {'Zn':1, 'O':1},
            'HZnO2-': {'Zn':1, 'O':2, 'H':1},
            'ZnO2-2': {'Zn':1, 'O':2},
            'ZnF+': {'Zn':1, 'F':1},



            'ACANTHITE': { 'Ag':2.0000, 'S':1.0000},
            'SILVER': { 'Ag':1.0000},
            'AKERMANITE': { 'Ca':2.0000, 'Mg':1.0000, 'O':7.0000,  'Si':2.0000},
            'ALABANDITE': { 'Mn':1.0000, 'S':1.0000},
            'ALBITE': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALBITE,LOW': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALBITE,HIGH': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALUNITE': { 'Al':3.0000, 'H':6.0000,  'K':1.0000, 'O':14.0000,  'S':2.0000},
            'ANALCIME': { 'Al':1.0000, 'H':2.0000,  'Na':1.0000,  'O':7.0000,  'Si':2.0000},
            'ANALCIME,DEHYDRATED': { 'Al':1.0000, 'Na':1.0000, 'O':6.0000,  'Si':2.0000},
            'ANATASE': { 'O':2.0000,  'Ti':1.0000},
            'ANDALUSITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'ANDRADITE': { 'Ca':3.0000, 'Fe':2.0000,  'O':12.0000,  'Si':3.0000},
            'ANGLESITE': { 'O':4.0000,  'Pb':1.0000, 'S':1.0000},
            'ANHYDRITE': { 'Ca':1.0000, 'O':4.0000,  'S':1.0000},
            'ANNITE': { 'Al':1.0000, 'Fe':3.0000, 'H':2.0000,  'K':1.0000, 'O':12.0000,  'Si':3.0000},
            'ANORTHITE': { 'Al':2.0000, 'Ca':1.0000, 'O':8.0000,  'Si':2.0000},
            'ANTHOPHYLLITE': { 'H':2.0000,  'Mg':7.0000,  'O':24.0000,  'Si':8.0000},
            'ANTIGORITE': {  'H':62.0000, 'Mg':48.0000, 'O':147.0000, 'Si':34.0000},
            'ARAGONITE': { 'C':1.0000,  'Ca':1.0000, 'O':3.0000},
            'ARTINITE': { 'C':1.0000,  'H':8.0000,  'Mg':2.0000,  'O':8.0000},
            'GOLD': { 'Au':1.0000},
            'AZURITE': { 'C':2.0000,  'Cu':3.0000, 'H':2.0000,  'O':8.0000},
            'BARITE': { 'Ba':1.0000, 'O':4.0000,  'S':1.0000},
            'BERNDTITE': { 'S':2.0000,  'Sn':1.0000},
            'BOEHMITE': { 'Al':1.0000, 'H':1.0000,  'O':2.0000},
            'BORNITE': { 'Cu':5.0000, 'Fe':1.0000, 'S':4.0000},
            'BRUCITE': { 'H':2.0000,  'Mg':1.0000, 'O':2.0000},
            'BUNSENITE': { 'Ni':1.0000, 'O':1.0000},
            'GRAPHITE': { 'C':1.0000},
            'CA-AL-PYROXENE': { 'Al':2.0000, 'Ca':1.0000, 'O':6.0000,  'Si':1.0000},
            'CALCITE': { 'C':1.0000,  'Ca':1.0000, 'O':3.0000},
            'CASSITERITE': { 'O':2.0000,  'Sn':1.0000},
            'CELESTITE': { 'O':4.0000,  'S':1.0000,  'Sr':1.0000},
            'CERUSSITE': { 'C':1.0000,  'O':3.0000,  'Pb':1.0000},
            'CHALCEDONY': { 'O':2.0000,  'Si':1.0000},
            'CHALCOCITE': { 'Cu':2.0000, 'S':1.0000},
            'CHALCOPYRITE': { 'Cu':1.0000, 'Fe':1.0000, 'S':2.0000},
            'CHLORARGYRITE': { 'Ag':1.0000, 'Cl':1.0000},
            'CHRYSOTILE': { 'H':4.0000,  'Mg':3.0000, 'O':9.0000,  'Si':2.0000},
            'CINNABAR': { 'Hg':1.0000, 'S':1.0000},
            'CLINOCHLORE,14A': { 'Al':2.0000, 'H':8.0000,  'Mg':5.0000, 'O':18.0000,  'Si':3.0000},
            'DAPHNITE,14A': { 'Al':2.0000, 'H':8.0000,  'Fe':5.0000, 'O':18.0000,  'Si':3.0000},
            'CLINOCHLORE,7A': { 'Al':2.0000, 'H':8.0000,  'Mg':5.0000, 'O':18.0000,  'Si':3.0000},
            'CLINOZOISITE': { 'Al':3.0000, 'Ca':2.0000, 'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'COESITE': { 'O':2.0000,  'Si':1.0000},
            'CORDIERITE': { 'Al':4.0000, 'Mg':2.0000,  'O':18.0000,  'Si':5.0000},
            'CORDIERITE,HYDROUS': { 'Al':4.0000, 'H':2.0000,  'Mg':2.0000, 'O':19.0000,  'Si':5.0000},
            'CORUNDUM': { 'Al':2.0000, 'O':3.0000},
            'COVELLITE': { 'Cu':1.0000, 'S':1.0000},
            'CRISTOBALITE': { 'O':2.0000,  'Si':1.0000},
            'CRISTOBALITE,ALPHA': { 'O':2.0000,  'Si':1.0000},
            'CRISTOBALITE,BETA': { 'O':2.0000,  'Si':1.0000},
            'COPPER': { 'Cu':1.0000},
            'CUPRITE': { 'Cu':2.0000, 'O':1.0000},
            'DIASPORE': { 'Al':1.0000, 'H':1.0000,  'O':2.0000},
            'DIOPSIDE': { 'Ca':1.0000, 'Mg':1.0000, 'O':6.0000,  'Si':2.0000},
            'DOLOMITE': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'DOLOMITE-DIS': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'DOLOMITE-ORD': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'ENSTATITE': { 'Mg':1.0000, 'O':3.0000,  'Si':1.0000},
            'EPIDOTE': { 'Al':2.0000, 'Ca':2.0000, 'Fe':1.0000,  'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'EPIDOTE,ORDERED': { 'Al':2.0000, 'Ca':2.0000, 'Fe':1.0000,  'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'FAYALITE': { 'Fe':2.0000, 'O':4.0000,  'Si':1.0000},
            'FERROUS-OXIDE': { 'Fe':1.0000, 'O':1.0000},
            'FERROPARGASITE': { 'Al':3.0000, 'Ca':2.0000, 'H':2.0000,  'Fe':4.0000, 'Na':1.0000,  'O':24.0000,  'Si':6.0000},
            'FERROSILITE': { 'Fe':1.0000, 'O':3.0000,  'Si':1.0000},
            'FERROTREMOLITE': { 'Ca':2.0000, 'H':2.0000,  'Fe':5.0000, 'O':24.0000,  'Si':8.0000},
            'FLUORITE': { 'Ca':1.0000, 'F':2.0000},
            'FORSTERITE': { 'Mg':2.0000, 'O':4.0000,  'Si':1.0000},
            'GALENA': { 'Pb':1.0000, 'S':1.0000},
            'GEHLENITE': { 'Al':2.0000, 'Ca':2.0000, 'O':7.0000,  'Si':1.0000},
            'GIBBSITE': { 'Al':1.0000, 'H':3.0000,  'O':3.0000},
            'GOETHITE': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'GROSSULAR': { 'Al':2.0000, 'Ca':3.0000,  'O':12.0000,  'Si':3.0000},
            'HALITE': { 'Cl':1.0000, 'Na':1.0000},
            'HEDENBERGITE': { 'Ca':1.0000, 'Fe':1.0000, 'O':6.0000,  'Si':2.0000},
            'HEMATITE': { 'Fe':2.0000, 'O':3.0000},
            'HUNTITE': { 'C':4.0000,  'Ca':1.0000, 'Mg':3.0000, 'O':12.0000},
            'HYDROMAGNESITE': { 'C':4.0000, 'H':10.0000,  'Mg':5.0000, 'O':18.0000},
            'ILMENITE': { 'Fe':1.0000, 'O':3.0000,  'Ti':1.0000},
            'IRON': { 'Fe':1.0000},
            'JADEITE': { 'Al':1.0000, 'Na':1.0000, 'O':6.0000,  'Si':2.0000},
            'K-FELDSPAR': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'POTASSIUM-OXIDE': { 'K':2.0000,  'O':1.0000},
            'KALSILITE': { 'Al':1.0000, 'K':1.0000,  'O':4.0000,  'Si':1.0000},
            'KAOLINITE': { 'Al':2.0000, 'H':4.0000,  'O':9.0000,  'Si':2.0000},
            'KYANITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'LAUMONTITE': { 'Al':2.0000, 'Ca':1.0000, 'H':8.0000, 'O':16.0000,  'Si':4.0000},
            'LAWSONITE': { 'Al':2.0000, 'Ca':1.0000, 'H':4.0000, 'O':10.0000,  'Si':2.0000},
            'LIME': { 'Ca':1.0000, 'O':1.0000},
            'LITHARGE': { 'Pb':1.0000, 'O':1.0000},
            'MAGNESITE': { 'C':1.0000,  'Mg':1.0000, 'O':3.0000},
            'MAGNETITE': { 'Fe':3.0000, 'O':4.0000},
            'MALACHITE': { 'C':1.0000,  'Cu':2.0000, 'H':2.0000,  'O':5.0000},
            'MANGANOSITE': { 'Mn':1.0000, 'O':1.0000},
            'MARGARITE': { 'Al':4.0000, 'Ca':1.0000, 'H':2.0000, 'O':12.0000,  'Si':2.0000},
            'MICROCLINE,MAXIMUM': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'MERWINITE': { 'Ca':3.0000, 'Mg':1.0000, 'O':8.0000,  'Si':2.0000},
            'METACINNABAR': { 'Hg':1.0000, 'S':1.0000},
            'MOLYBDENITE': { 'S':2.0000,  'Mo':1.0000},
            'MONTICELLITE': { 'Ca':1.0000, 'Mg':1.0000, 'O':4.0000,  'Si':1.0000},
            'MUSCOVITE': { 'Al':3.0000, 'H':2.0000,  'K':1.0000, 'O':12.0000,  'Si':3.0000},
            'SODIUM-OXIDE': { 'Na':2.0000, 'O':1.0000},
            'NEPHELINE': { 'Al':1.0000, 'Na':1.0000, 'O':4.0000,  'Si':1.0000},
            'NESQUEHONITE': { 'C':1.0000,  'H':6.0000,  'Mg':1.0000,  'O':6.0000},
            'NICKEL': { 'Ni':1.0000},
            'PARAGONITE': { 'Al':3.0000, 'H':2.0000,  'Na':1.0000, 'O':12.0000,  'Si':3.0000},
            'PARGASITE': { 'Al':3.0000, 'Ca':2.0000, 'H':2.0000,  'Mg':4.0000, 'Na':1.0000,  'O':24.0000,  'Si':6.0000},
            'PERICLASE': { 'Mg':1.0000, 'O':1.0000},
            'PEROVSKITE': { 'Ca':1.0000, 'O':3.0000,  'Ti':1.0000},
            'PHLOGOPITE': { 'Al':1.0000, 'H':2.0000,  'K':1.0000,  'Mg':3.0000,  'O':12.0000,  'Si':3.0000},
            'PREHNITE': { 'Al':2.0000, 'Ca':2.0000, 'H':2.0000, 'O':12.0000,  'Si':3.0000},
            'PYRITE': { 'Fe':1.0000, 'S':2.0000},
            'PYROPHYLLITE': { 'Al':2.0000, 'H':2.0000, 'O':12.0000,  'Si':4.0000},
            'PYRRHOTITE': { 'Fe':1.0000, 'S':1.0000},
            'QUARTZ': { 'O':2.0000,  'Si':1.0000},
            'RHODOCHROSITE': { 'C':1.0000,  'Mn':1.0000, 'O':3.0000},
            'RUTILE': { 'O':2.0000,  'Ti':1.0000},
            'ROMARCHITE': { 'O':1.0000,  'Sn':1.0000},
            'SANIDINE,HIGH': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'SEPIOLITE': {  'H':14.0000,  'Mg':4.0000,  'O':23.0000,  'Si':6.0000},
            'AMORPHOUS-SILICA': { 'O':2.0000,  'Si':1.0000},
            'SIDERITE': { 'C':1.0000,  'Fe':1.0000, 'O':3.0000},
            'SILLIMANITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'SMITHSONITE': { 'C':1.0000,  'O':3.0000,  'Zn':1.0000},
            'TIN': { 'Sn':1.0000},
            'TITANITE': { 'Ca':1.0000, 'O':5.0000,  'Si':1.0000,  'Ti':1.0000},
            'SPHALERITE': { 'S':1.0000,  'Zn':1.0000},
            'SPINEL': { 'Al':2.0000, 'Mg':1.0000, 'O':4.0000},
            'STRONTIANITE': { 'C':1.0000,  'O':3.0000,  'Sr':1.0000},
            'SYLVITE': { 'Cl':1.0000, 'K':1.0000},
            'TALC': { 'H':2.0000,  'Mg':3.0000,  'O':12.0000,  'Si':4.0000},
            'TENORITE': { 'Cu':1.0000, 'O':1.0000},
            'TREMOLITE': { 'Ca':2.0000, 'H':2.0000,  'Mg':5.0000, 'O':24.0000,  'Si':8.0000},
            'ULVOSPINEL': { 'Fe':2.0000, 'O':4.0000,  'Ti':1.0000},
            'URANINITE': { 'U':1.0000,  'O':2.0000},
            'WAIRAKITE': { 'Al':2.0000, 'Ca':1.0000, 'H':4.0000, 'O':14.0000,  'Si':4.0000},
            'WOLLASTONITE': { 'Ca':1.0000, 'O':3.0000,  'Si':1.0000},
            'WURTZITE': { 'S':1.0000,  'Zn':1.0000},
            'ZINCITE': { 'O':1.0000,  'Zn':1.0000},
            'ZOISITE': { 'Al':3.0000, 'Ca':2.0000, 'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'GREENALITE': { 'Fe':3.0000, 'H':4.0000,  'O':9.0000,  'Si':2.0000},
            'MINNESOTAITE': { 'H':2.0000,  'Fe':3.0000,  'O':12.0000,  'Si':4.0000},
            'CRONSTEDTITE,7A': { 'H':4.0000,  'Fe':4.0000, 'O':9.0000,  'Si':1.0000},
            'FE-BRUCITE': { 'H':2.0000,  'Fe':1.0000, 'O':2.0000},
            'LEPIDOCROCITE': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'FERRIHYDRITE*0H2O': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'FERRIHYDRITE': { 'Fe':1.0000, 'O':2.0270,  'H':1.0540},
            'FERRIHYDRITE*1H2O': { 'Fe':1.0000, 'O':3.0000,  'H':3.0000},
            'MAGHEMITE': { 'Fe':2.0000, 'O':3.0000},
            'CA-SAPONITE': { 'Al':0.3300, 'Ca':0.1650, 'H':2.0000,  'Mg':3.0000,  'O':12.0000,  'Si':3.6700},
            'H-SAPONITE': { 'Al':0.3300, 'H':2.3300,  'Mg':3.0000, 'O':12.0000,  'Si':3.6700},
            'K-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'K':0.3300,  'Mg':3.0000,  'O':12.0000,  'Si':3.6700},
            'MG-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'Mg':3.1650, 'O':12.0000,  'Si':3.6700},
            'NA-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'Mg':3.0000,  'Na':0.3300,  'O':12.0000,  'Si':3.6700},
            'CA-NONTRONITE': { 'Al':0.3300, 'Ca':0.1650, 'Fe':2.0000,  'H':2.0000, 'O':12.0000,  'Si':3.6700},
            'H-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.3300, 'O':12.0000,  'Si':3.6700},
            'K-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'K':0.3300, 'O':12.0000,  'Si':3.6700},
            'MG-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'Mg':0.1650,  'O':12.0000,  'Si':3.6700},
            'NA-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'Na':0.3300,  'O':12.0000,  'Si':3.6700},
            'CA-BEIDELLITE': { 'Al':2.3300, 'Ca':0.1650, 'H':2.0000, 'O':12.0000,  'Si':3.6700},
            'H-BEIDELLITE': { 'Al':2.3300, 'H':2.3300, 'O':12.0000,  'Si':3.6700},
            'K-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'K':0.3300, 'O':12.0000,  'Si':3.6700},
            'MG-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'Mg':0.1650, 'O':12.0000,  'Si':3.6700},
            'NA-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'Na':0.3300, 'O':12.0000,  'Si':3.6700},
            'CA-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'Ca':0.1650},
            'H-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.3300},
            'K-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'K':0.3300},
            'MG-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.4950,  'O':12.0000,  'Si':4.0000, 'H':2.0000},
            'NA-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'Na':0.3300},
            'FLOURAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':12.0000,  'F':1.0000},
            'HYDROXYAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':13.0000,  'H':1.0000},
            'CHLORAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':12.0000,  'Cl':1.0000},



            'Ar(g)':{ 'Ar':1.0000},
            'CH4(g)':{ 'C':1.0000, 'H':4.0000},
            'CO(g)':{ 'C':1.0000, 'O':1.0000},
            'CO2(g)':{ 'C':1.0000, 'O':2.0000},
            'ETHYLENE(g)':{ 'C':2.0000, 'H':4.0000},
            'H2(g)':{ 'H':2.0000},
            'H2O(g)':{ 'H':2.0000, 'O':1.0000},
            'H2S(g)':{ 'H':2.0000, 'S':1.0000},
            'He(g)':{ 'He':1.0000},
            'Kr(g)':{ 'Kr':1.0000},
            'N2(g)':{ 'N':2.0000},
            'N2O(g)':{ 'N':2.0000, 'O':1.0000},
            'Ne(g)':{ 'Ne':1.0000},
            'NH3(g)':{ 'H':3.0000, 'N':1.0000},
            'O2(g)':{ 'O':2.0000},
            'Rn(g)':{ 'Rn':1.0000},
            'S2(g)':{ 'S':2.0000},
            'SO2(g)':{ 'O':2.0000, 'S':1.0000},
            'Xe(g)':{ 'Xe':1.0000}}



UM_solids_dict = {
            'ACANTHITE': { 'Ag':2.0000, 'S':1.0000},
            'SILVER': { 'Ag':1.0000},
            'AKERMANITE': { 'Ca':2.0000, 'Mg':1.0000, 'O':7.0000,  'Si':2.0000},
            'ALABANDITE': { 'Mn':1.0000, 'S':1.0000},
            'ALBITE': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALBITE,LOW': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALBITE,HIGH': { 'Al':1.0000, 'Na':1.0000, 'O':8.0000,  'Si':3.0000},
            'ALUNITE': { 'Al':3.0000, 'H':6.0000,  'K':1.0000, 'O':14.0000,  'S':2.0000},
            'ANALCIME': { 'Al':1.0000, 'H':2.0000,  'Na':1.0000,  'O':7.0000,  'Si':2.0000},
            'ANALCIME,DEHYDRATED': { 'Al':1.0000, 'Na':1.0000, 'O':6.0000,  'Si':2.0000},
            'ANATASE': { 'O':2.0000,  'Ti':1.0000},
            'ANDALUSITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'ANDRADITE': { 'Ca':3.0000, 'Fe':2.0000,  'O':12.0000,  'Si':3.0000},
            'ANGLESITE': { 'O':4.0000,  'Pb':1.0000, 'S':1.0000},
            'ANHYDRITE': { 'Ca':1.0000, 'O':4.0000,  'S':1.0000},
            'ANNITE': { 'Al':1.0000, 'Fe':3.0000, 'H':2.0000,  'K':1.0000, 'O':12.0000,  'Si':3.0000},
            'ANORTHITE': { 'Al':2.0000, 'Ca':1.0000, 'O':8.0000,  'Si':2.0000},
            'ANTHOPHYLLITE': { 'H':2.0000,  'Mg':7.0000,  'O':24.0000,  'Si':8.0000},
            'ANTIGORITE': {  'H':62.0000, 'Mg':48.0000, 'O':147.0000, 'Si':34.0000},
            'ARAGONITE': { 'C':1.0000,  'Ca':1.0000, 'O':3.0000},
            'ARTINITE': { 'C':1.0000,  'H':8.0000,  'Mg':2.0000,  'O':8.0000},
            'GOLD': { 'Au':1.0000},
            'AZURITE': { 'C':2.0000,  'Cu':3.0000, 'H':2.0000,  'O':8.0000},
            'BARITE': { 'Ba':1.0000, 'O':4.0000,  'S':1.0000},
            'BERNDTITE': { 'S':2.0000,  'Sn':1.0000},
            'BOEHMITE': { 'Al':1.0000, 'H':1.0000,  'O':2.0000},
            'BORNITE': { 'Cu':5.0000, 'Fe':1.0000, 'S':4.0000},
            'BRUCITE': { 'H':2.0000,  'Mg':1.0000, 'O':2.0000},
            'BUNSENITE': { 'Ni':1.0000, 'O':1.0000},
            'GRAPHITE': { 'C':1.0000},
            'CA-AL-PYROXENE': { 'Al':2.0000, 'Ca':1.0000, 'O':6.0000,  'Si':1.0000},
            'CALCITE': { 'C':1.0000,  'Ca':1.0000, 'O':3.0000},
            'CASSITERITE': { 'O':2.0000,  'Sn':1.0000},
            'CELESTITE': { 'O':4.0000,  'S':1.0000,  'Sr':1.0000},
            'CERUSSITE': { 'C':1.0000,  'O':3.0000,  'Pb':1.0000},
            'CHALCEDONY': { 'O':2.0000,  'Si':1.0000},
            'CHALCOCITE': { 'Cu':2.0000, 'S':1.0000},
            'CHALCOPYRITE': { 'Cu':1.0000, 'Fe':1.0000, 'S':2.0000},
            'CHLORARGYRITE': { 'Ag':1.0000, 'Cl':1.0000},
            'CHRYSOTILE': { 'H':4.0000,  'Mg':3.0000, 'O':9.0000,  'Si':2.0000},
            'CINNABAR': { 'Hg':1.0000, 'S':1.0000},
            'CLINOCHLORE,14A': { 'Al':2.0000, 'H':8.0000,  'Mg':5.0000, 'O':18.0000,  'Si':3.0000},
            'DAPHNITE,14A': { 'Al':2.0000, 'H':8.0000,  'Fe':5.0000, 'O':18.0000,  'Si':3.0000},
            'CLINOCHLORE,7A': { 'Al':2.0000, 'H':8.0000,  'Mg':5.0000, 'O':18.0000,  'Si':3.0000},
            'CLINOZOISITE': { 'Al':3.0000, 'Ca':2.0000, 'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'COESITE': { 'O':2.0000,  'Si':1.0000},
            'CORDIERITE': { 'Al':4.0000, 'Mg':2.0000,  'O':18.0000,  'Si':5.0000},
            'CORDIERITE,HYDROUS': { 'Al':4.0000, 'H':2.0000,  'Mg':2.0000, 'O':19.0000,  'Si':5.0000},
            'CORUNDUM': { 'Al':2.0000, 'O':3.0000},
            'COVELLITE': { 'Cu':1.0000, 'S':1.0000},
            'CRISTOBALITE': { 'O':2.0000,  'Si':1.0000},
            'CRISTOBALITE,ALPHA': { 'O':2.0000,  'Si':1.0000},
            'CRISTOBALITE,BETA': { 'O':2.0000,  'Si':1.0000},
            'COPPER': { 'Cu':1.0000},
            'CUPRITE': { 'Cu':2.0000, 'O':1.0000},
            'DIASPORE': { 'Al':1.0000, 'H':1.0000,  'O':2.0000},
            'DIOPSIDE': { 'Ca':1.0000, 'Mg':1.0000, 'O':6.0000,  'Si':2.0000},
            'DOLOMITE': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'DOLOMITE-DIS': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'DOLOMITE-ORD': { 'C':2.0000,  'Ca':1.0000, 'Mg':1.0000,  'O':6.0000},
            'ENSTATITE': { 'Mg':1.0000, 'O':3.0000,  'Si':1.0000},
            'EPIDOTE': { 'Al':2.0000, 'Ca':2.0000, 'Fe':1.0000,  'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'EPIDOTE,ORDERED': { 'Al':2.0000, 'Ca':2.0000, 'Fe':1.0000,  'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'FAYALITE': { 'Fe':2.0000, 'O':4.0000,  'Si':1.0000},
            'FERROUS-OXIDE': { 'Fe':1.0000, 'O':1.0000},
            'FERROPARGASITE': { 'Al':3.0000, 'Ca':2.0000, 'H':2.0000,  'Fe':4.0000, 'Na':1.0000,  'O':24.0000,  'Si':6.0000},
            'FERROSILITE': { 'Fe':1.0000, 'O':3.0000,  'Si':1.0000},
            'FERROTREMOLITE': { 'Ca':2.0000, 'H':2.0000,  'Fe':5.0000, 'O':24.0000,  'Si':8.0000},
            'FLUORITE': { 'Ca':1.0000, 'F':2.0000},
            'FORSTERITE': { 'Mg':2.0000, 'O':4.0000,  'Si':1.0000},
            'GALENA': { 'Pb':1.0000, 'S':1.0000},
            'GEHLENITE': { 'Al':2.0000, 'Ca':2.0000, 'O':7.0000,  'Si':1.0000},
            'GIBBSITE': { 'Al':1.0000, 'H':3.0000,  'O':3.0000},
            'GOETHITE': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'GROSSULAR': { 'Al':2.0000, 'Ca':3.0000,  'O':12.0000,  'Si':3.0000},
            'HALITE': { 'Cl':1.0000, 'Na':1.0000},
            'HEDENBERGITE': { 'Ca':1.0000, 'Fe':1.0000, 'O':6.0000,  'Si':2.0000},
            'HEMATITE': { 'Fe':2.0000, 'O':3.0000},
            'HUNTITE': { 'C':4.0000,  'Ca':1.0000, 'Mg':3.0000, 'O':12.0000},
            'HYDROMAGNESITE': { 'C':4.0000, 'H':10.0000,  'Mg':5.0000, 'O':18.0000},
            'ILMENITE': { 'Fe':1.0000, 'O':3.0000,  'Ti':1.0000},
            'IRON': { 'Fe':1.0000},
            'JADEITE': { 'Al':1.0000, 'Na':1.0000, 'O':6.0000,  'Si':2.0000},
            'K-FELDSPAR': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'POTASSIUM-OXIDE': { 'K':2.0000,  'O':1.0000},
            'KALSILITE': { 'Al':1.0000, 'K':1.0000,  'O':4.0000,  'Si':1.0000},
            'KAOLINITE': { 'Al':2.0000, 'H':4.0000,  'O':9.0000,  'Si':2.0000},
            'KYANITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'LAUMONTITE': { 'Al':2.0000, 'Ca':1.0000, 'H':8.0000, 'O':16.0000,  'Si':4.0000},
            'LAWSONITE': { 'Al':2.0000, 'Ca':1.0000, 'H':4.0000, 'O':10.0000,  'Si':2.0000},
            'LIME': { 'Ca':1.0000, 'O':1.0000},
            'LITHARGE': { 'Pb':1.0000, 'O':1.0000},
            'MAGNESITE': { 'C':1.0000,  'Mg':1.0000, 'O':3.0000},
            'MAGNETITE': { 'Fe':3.0000, 'O':4.0000},
            'MALACHITE': { 'C':1.0000,  'Cu':2.0000, 'H':2.0000,  'O':5.0000},
            'MANGANOSITE': { 'Mn':1.0000, 'O':1.0000},
            'MARGARITE': { 'Al':4.0000, 'Ca':1.0000, 'H':2.0000, 'O':12.0000,  'Si':2.0000},
            'MICROCLINE,MAXIMUM': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'MERWINITE': { 'Ca':3.0000, 'Mg':1.0000, 'O':8.0000,  'Si':2.0000},
            'METACINNABAR': { 'Hg':1.0000, 'S':1.0000},
            'MOLYBDENITE': { 'S':2.0000,  'Mo':1.0000},
            'MONTICELLITE': { 'Ca':1.0000, 'Mg':1.0000, 'O':4.0000,  'Si':1.0000},
            'MUSCOVITE': { 'Al':3.0000, 'H':2.0000,  'K':1.0000, 'O':12.0000,  'Si':3.0000},
            'SODIUM-OXIDE': { 'Na':2.0000, 'O':1.0000},
            'NEPHELINE': { 'Al':1.0000, 'Na':1.0000, 'O':4.0000,  'Si':1.0000},
            'NESQUEHONITE': { 'C':1.0000,  'H':6.0000,  'Mg':1.0000,  'O':6.0000},
            'NICKEL': { 'Ni':1.0000},
            'PARAGONITE': { 'Al':3.0000, 'H':2.0000,  'Na':1.0000, 'O':12.0000,  'Si':3.0000},
            'PARGASITE': { 'Al':3.0000, 'Ca':2.0000, 'H':2.0000,  'Mg':4.0000, 'Na':1.0000,  'O':24.0000,  'Si':6.0000},
            'PERICLASE': { 'Mg':1.0000, 'O':1.0000},
            'PEROVSKITE': { 'Ca':1.0000, 'O':3.0000,  'Ti':1.0000},
            'PHLOGOPITE': { 'Al':1.0000, 'H':2.0000,  'K':1.0000,  'Mg':3.0000,  'O':12.0000,  'Si':3.0000},
            'PREHNITE': { 'Al':2.0000, 'Ca':2.0000, 'H':2.0000, 'O':12.0000,  'Si':3.0000},
            'PYRITE': { 'Fe':1.0000, 'S':2.0000},
            'PYROPHYLLITE': { 'Al':2.0000, 'H':2.0000, 'O':12.0000,  'Si':4.0000},
            'PYRRHOTITE': { 'Fe':1.0000, 'S':1.0000},
            'QUARTZ': { 'O':2.0000,  'Si':1.0000},
            'RHODOCHROSITE': { 'C':1.0000,  'Mn':1.0000, 'O':3.0000},
            'RUTILE': { 'O':2.0000,  'Ti':1.0000},
            'ROMARCHITE': { 'O':1.0000,  'Sn':1.0000},
            'SANIDINE,HIGH': { 'Al':1.0000, 'K':1.0000,  'O':8.0000,  'Si':3.0000},
            'SEPIOLITE': {  'H':14.0000,  'Mg':4.0000,  'O':23.0000,  'Si':6.0000},
            'AMORPHOUS-SILICA': { 'O':2.0000,  'Si':1.0000},
            'SIDERITE': { 'C':1.0000,  'Fe':1.0000, 'O':3.0000},
            'SILLIMANITE': { 'Al':2.0000, 'O':5.0000,  'Si':1.0000},
            'SMITHSONITE': { 'C':1.0000,  'O':3.0000,  'Zn':1.0000},
            'TIN': { 'Sn':1.0000},
            'TITANITE': { 'Ca':1.0000, 'O':5.0000,  'Si':1.0000,  'Ti':1.0000},
            'SPHALERITE': { 'S':1.0000,  'Zn':1.0000},
            'SPINEL': { 'Al':2.0000, 'Mg':1.0000, 'O':4.0000},
            'STRONTIANITE': { 'C':1.0000,  'O':3.0000,  'Sr':1.0000},
            'SYLVITE': { 'Cl':1.0000, 'K':1.0000},
            'TALC': { 'H':2.0000,  'Mg':3.0000,  'O':12.0000,  'Si':4.0000},
            'TENORITE': { 'Cu':1.0000, 'O':1.0000},
            'TREMOLITE': { 'Ca':2.0000, 'H':2.0000,  'Mg':5.0000, 'O':24.0000,  'Si':8.0000},
            'ULVOSPINEL': { 'Fe':2.0000, 'O':4.0000,  'Ti':1.0000},
            'URANINITE': { 'U':1.0000,  'O':2.0000},
            'WAIRAKITE': { 'Al':2.0000, 'Ca':1.0000, 'H':4.0000, 'O':14.0000,  'Si':4.0000},
            'WOLLASTONITE': { 'Ca':1.0000, 'O':3.0000,  'Si':1.0000},
            'WURTZITE': { 'S':1.0000,  'Zn':1.0000},
            'ZINCITE': { 'O':1.0000,  'Zn':1.0000},
            'ZOISITE': { 'Al':3.0000, 'Ca':2.0000, 'H':1.0000, 'O':13.0000,  'Si':3.0000},
            'GREENALITE': { 'Fe':3.0000, 'H':4.0000,  'O':9.0000,  'Si':2.0000},
            'MINNESOTAITE': { 'H':2.0000,  'Fe':3.0000,  'O':12.0000,  'Si':4.0000},
            'CRONSTEDTITE,7A': { 'H':4.0000,  'Fe':4.0000, 'O':9.0000,  'Si':1.0000},
            'FE-BRUCITE': { 'H':2.0000,  'Fe':1.0000, 'O':2.0000},
            'LEPIDOCROCITE': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'FERRIHYDRITE*0H2O': { 'Fe':1.0000, 'O':2.0000,  'H':1.0000},
            'FERRIHYDRITE': { 'Fe':1.0000, 'O':2.0270,  'H':1.0540},
            'FERRIHYDRITE*1H2O': { 'Fe':1.0000, 'O':3.0000,  'H':3.0000},
            'MAGHEMITE': { 'Fe':2.0000, 'O':3.0000},
            'CA-SAPONITE': { 'Al':0.3300, 'Ca':0.1650, 'H':2.0000,  'Mg':3.0000,  'O':12.0000,  'Si':3.6700},
            'H-SAPONITE': { 'Al':0.3300, 'H':2.3300,  'Mg':3.0000, 'O':12.0000,  'Si':3.6700},
            'K-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'K':0.3300,  'Mg':3.0000,  'O':12.0000,  'Si':3.6700},
            'MG-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'Mg':3.1650, 'O':12.0000,  'Si':3.6700},
            'NA-SAPONITE': { 'Al':0.3300, 'H':2.0000,  'Mg':3.0000,  'Na':0.3300,  'O':12.0000,  'Si':3.6700},
            'CA-NONTRONITE': { 'Al':0.3300, 'Ca':0.1650, 'Fe':2.0000,  'H':2.0000, 'O':12.0000,  'Si':3.6700},
            'H-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.3300, 'O':12.0000,  'Si':3.6700},
            'K-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'K':0.3300, 'O':12.0000,  'Si':3.6700},
            'MG-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'Mg':0.1650,  'O':12.0000,  'Si':3.6700},
            'NA-NONTRONITE': { 'Al':0.3300, 'Fe':2.0000, 'H':2.0000,  'Na':0.3300,  'O':12.0000,  'Si':3.6700},
            'CA-BEIDELLITE': { 'Al':2.3300, 'Ca':0.1650, 'H':2.0000, 'O':12.0000,  'Si':3.6700},
            'H-BEIDELLITE': { 'Al':2.3300, 'H':2.3300, 'O':12.0000,  'Si':3.6700},
            'K-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'K':0.3300, 'O':12.0000,  'Si':3.6700},
            'MG-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'Mg':0.1650, 'O':12.0000,  'Si':3.6700},
            'NA-BEIDELLITE': { 'Al':2.3300, 'H':2.0000,  'Na':0.3300, 'O':12.0000,  'Si':3.6700},
            'CA-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'Ca':0.1650},
            'H-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.3300},
            'K-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'K':0.3300},
            'MG-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.4950,  'O':12.0000,  'Si':4.0000, 'H':2.0000},
            'NA-MONTMORILLONITE': { 'Al':1.6700, 'Mg':0.3300,  'O':12.0000,  'Si':4.0000, 'H':2.0000,  'Na':0.3300},
            'FLOURAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':12.0000,  'F':1.0000},
            'HYDROXYAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':13.0000,  'H':1.0000},
            'CHLORAPATITE': { 'Ca':5.0000, 'P':3.0000, 'O':12.0000,  'Cl':1.0000}}

    
# ss_to_end_dict = {
#             "SERPENTINE": [ "CHRYSOTILE",   "GREENALITE", "CRONSTEDTITE,7A"],
#             "BRUCITE-SS": [ "BRUCITE",  "FE-BRUCITE"],
#             "TALC-SS": [ "TALC", "MINNESOTAITE"],
#             "BIOTITE": [ "ANNITE",   "PHLOGOPITE"],
#             "CARBONATE-CALCITE": [ "CALCITE",  "MAGNESITE", "RHODOCHROSITE","SIDERITE",  "SMITHSONITE",  "STRONTIANITE"],
#             "CHLORITE-SS": [ "CLINOCHLORE,14A ", "DAPHNITE,14A "],
#             "EPIDOTE-SS": [ "CLINOZOISITE", "EPIDOTE"],
#             "GARNET-SS": [ "ANDRADITE","GROSSULAR"],
#             "OLIVINE": [ "FAYALITE", "FORSTERITE"],
#             "IDEAL OLIVINE": [ "FAYALITE", "FORSTERITE"],
#             "ORTHOPYROXENE": [ "ENSTATITE","FERROSILITE"],
#             "CLINOPYROXENE": [ "DIOPSIDE", "HEDENBERGITE"],
#             "Ca-AMPHIB. BINARY": [ "TREMOLITE","FERROTREMOLITE"],
#             "AMPHIB. TERNARY": [ "TREMOLITE","FERROTREMOLITE","PARGASITE"],
#             "TREM-PARG BINARY": [ "TREMOLITE","PARGASITE"],
#             "IDEAL PLAGIOCLASE": [ "ALBITE,HIGH",  "ANORTHITE"],
#             "PLAGIOCLASE,LOW": [ "ALBITE,LOW",   "ANORTHITE"],
#             "PLAG. CUB. MAC": ["ALBITE,LOW",   "ANORTHITE"],
#             "SANIDINE-SS": [ "ALBITE,HIGH",  "SANIDINE,HIGH"],
#             "MICROCLINE-SS": [ "ALBITE,LOW",   "MICROCLINE,MAXIMUM"],
#             "ALK. FELDSPAR-SS": [ "ALBITE,LOW",   "K-FELDSPAR"],
#             "ALK FELD BIN MAR": [ "ALBITE,LOW",   "K-FELDSPAR"],
#             "FELD BIN MARG 2": [ "ALBITE,LOW",   "K-FELDSPAR"],  
#             "SAPONITE": [ "CA-SAPONITE",  "H-SAPONITE","K-SAPONITE",   "MG-SAPONITE",   "NA-SAPONITE"],
#             "NONTRONITE": [ "CA-NONTRONITE","H-NONTRONITE",  "K-NONTRONITE", "MG-NONTRONITE", "NA-NONTRONITE"],
#             "BEIDELLITE": [ "CA-BEIDELLITE","H-BEIDELLITE",  "K-BEIDELLITE", "MG-BEIDELLITE", "NA-BEIDELLITE"],
#             "MONTMORILLONITE": [ "CA-MONTMORILLONITE",   "H-MONTMORILLONITE", "K-MONTMORILLONITE","MG-MONTMORILLONITE","NA-MONTMORILLONITE"]
#             }

ss_to_end_dict = {
            'SERPENTINE':{ 'CHRYSOTILE', 'GREENALITE', 'CRONSTEDTITE,7A'},
            'BRUCITE-SS':{ 'BRUCITE', 'FE-BRUCITE'},
            'TALC-SS':{ 'TALC', 'MINNESOTAITE'},
            'BIOTITE':{ 'ANNITE', 'PHLOGOPITE'},
            'CARBONATE-CALCITE':{ 'CALCITE', 'MAGNESITE', 'RHODOCHROSITE', 'SIDERITE', 'SMITHSONITE', 'STRONTIANITE'},
            'CHLORITE-SS':{ 'CLINOCHLORE,14A', 'DAPHNITE,14A'},
            'EPIDOTE-SS':{ 'CLINOZOISITE', 'EPIDOTE'},
            'GARNET-SS':{ 'ANDRADITE', 'GROSSULAR'},
            'OLIVINE':{ 'FAYALITE', 'FORSTERITE'},
            'IDEAL OLIVINE':{ 'FAYALITE', 'FORSTERITE'},
            'ORTHOPYROXENE':{ 'ENSTATITE', 'FERROSILITE'},
            'CLINOPYROXENE':{ 'DIOPSIDE', 'HEDENBERGITE'},
            'Ca-AMPHIB. BINARY':{ 'TREMOLITE', 'FERROTREMOLITE'},
            'AMPHIB. TERNARY':{ 'TREMOLITE', 'FERROTREMOLITE', 'PARGASITE'},
            'TREM-PARG BINARY':{ 'TREMOLITE', 'PARGASITE'},
            'IDEAL PLAGIOCLASE':{ 'ALBITE,HIGH', 'ANORTHITE'},
            'PLAGIOCLASE,LOW':{ 'ALBITE,LOW', 'ANORTHITE'},
            'PLAG. CUB. MAC.':{ 'ALBITE,LOW', 'ANORTHITE'},
            'SANIDINE-SS':{ 'ALBITE,HIGH', 'SANIDINE,HIGH'},
            'MICROCLINE-SS':{ 'ALBITE,LOW', 'MICROCLINE,MAXIMUM'},
            'ALK. FELDSPAR-SS':{ 'ALBITE,LOW', 'K-FELDSPAR'},
            'ALK FELD BIN MAR':{ 'ALBITE,LOW', 'K-FELDSPAR'},
            'FELD BIN MARG 2':{ 'ALBITE,LOW', 'K-FELDSPAR'},
            'SAPONITE':{ 'CA-SAPONITE', 'H-SAPONITE', 'K-SAPONITE', 'MG-SAPONITE', 'NA-SAPONITE'},
            'NONTRONITE':{ 'CA-NONTRONITE', 'H-NONTRONITE', 'K-NONTRONITE', 'MG-NONTRONITE', 'NA-NONTRONITE'},
            'BEIDELLITE':{ 'CA-BEIDELLITE', 'H-BEIDELLITE', 'K-BEIDELLITE', 'MG-BEIDELLITE', 'NA-BEIDELLITE'},
            'MONTMORILLONITE':{ 'CA-MONTMORILLONITE', 'H-MONTMORILLONITE', 'K-MONTMORILLONITE', 'MG-MONTMORILLONITE', 'NA-MONTMORILLONITE'}
            }


### jflag dictionary for basis species input units
jflag_d = { 0:  'Total molality',
            1:  'Total molarity',
            2:  'Total mg/L',
            3:  'Total mg/kg.sol',
            4:  'ERROR',
            5:  'ERROR',
            6:  'ERROR',
            7:  'Total alkalinity, eq/kg.H2O',
            8:  'Total alkalinity, eq/L',
            9:  'Total alkalinity, eq/kg.sol',
            10: 'Total alkalinity, mg/L CaCO3',
            11: 'Total alkalinity, mg/L HCO3-',
            12: 'ERROR',
            13: 'ERROR',
            14: 'ERROR',
            15: 'ERROR',
            16: 'Log activity',
            17: '|zj| log ai +/- |zi| log aj',
            18: 'Log a(+/-,ij)',
            19: 'pX',
            20: 'pH',
            21: 'pHCl',
            22: 'pmH',
            23: 'pmX',
            24: 'ERROR',
            25: 'Heterogenous equilibrium',
            26: 'ERROR',
            27: 'Homogenous equilibrium',
            28: 'ERROR',
            29: 'ERROR',
            30: 'Make non-basis'}


eq3var_d = {'fxi': 'calculated statring value for the ionic strength in pre NR optimization (arrset.f)',
    'fje'   : 'vlaue fof the J electrostatic moment function',
    'xbrwlc': 'specifics unknow. related to setting activity of water (arrset.f)',
    'xbarwc': 'specifics unknow. related to setting activity of water (arrset.f)',
    'beta'  : 'NR residual function vector. identical to alpha, except that mass balance risdual elements are normalized by the corresponding values of total numbers of moles.',
    'betamx': 'the largest absolute value of any element of the beta vector',
    'betfnc': 'convergence fucntion for beta array',

    'bfac'  :' In the continued fraction \
    method, m(new) = m(old)/bfac, where bfac = (beta + 1)**efac. \
    If the same species dominates more than one mass balance, \
    then this algorithm can be applied to only one of the associated \
    basis species. Otherwise, oscillatory behavior will occur. In each \
    set of mass balances with a common dominating species, find the \
    mass balance with the greatest bfac factor. This is usually nearly \
    equivalent to finding the mass balance with the greater beta \
    residual, as efac often has a value of unity.',

    'btfncr': 'measures convergence on a pure NR step',
    'bbig'  : 'largest positive mass balance residual',
    'ubbig' : 'species with largest positive mass balance residual ( = bbig)', 
    'bneg'  : 'largest negative mass balance residual',
    'ubneg' : 'species with largest negative mass balance residual ( = bneg)',
    'bgamx' : 'aqueous activity coefficient residual function (max norm on the absolute values of the differences between current and previous values of the activity coefficients of aq species',
    'ubgamx': 'species associated with bgamx',
    'bsigm' : 'residual on sigma(m) function (differnce betwen current and previous states)',
    'bxi'   : 'residual on ionic strength'
    }


### Special reactant dictionary. 
### sr_dict['name'] = [[ele list], [associated sto list]]
sr_dict = {"FeCl2": [["Fe", "Cl"], [1, 2]]
    

        }



### dictionary containing custom eq3/6 exit codes that hint at the casue of the failure.
### by assigning a number, I can track errors in a lightweight fashion, and
### make it easy to color output points based on the type of error they generate.
run_codes = {0   : 'not run',
    100 : 'normal termination',
    30  : 'no 3p generated',
    31  : 'pickup present but contains errors',
    60  : 'no 6o generated',
    61  : 'unrecognized 6o error (6o present neitehr normal nor early)',
    62  : 'mine 6o function fail',
    70  : 'early 6i termination'
            }





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



















