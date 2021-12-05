###
### data0 analysis tools
### Tucker Ely 
### April 8th 2020

import numpy, math, itertools, os, re
import pandas as pd

import matplotlib
import matplotlib.pyplot as plt

from .tool_room import *

data0_repo = '/Users/tuckerely/data0/data0/'

slop_df = pd.read_csv('test_worm_data.csv', index_col=0)

def species_info(sp):
	"""
	in: 
		'species namr in worm slop file 'slop_df'
	out:
		dict['ele'] = sto containing ele,ents in species
	"""
	comp_dict = {}
	formula_ox = slop_df['formula_ox'][sp]
	for _ in formula_ox.split():
		front = (re.sub(r'[-+][0-9]{0,2}', '', _))
		if re.findall('^[A-Za-z]', front):
			front = '1{}'.format(front)
		sto, ele = re.findall('([0-9+\.]{1,}|[A-Za-z]+)', front)
		comp_dict[ele] = sto
	return comp_dict


def determine_ele_set(path = ''):
	"""
	Use the verbose test.3o file run by the huffer to determine the loaded elements
	in:
		path = campaign huffer path where test.3o is located
	out:
		list of elements

	"""
	elements = []
	grab_ele = False
	with open('{}output'.format(path), 'r') as f:
		for line in f:
			if '           --- Elemental Composition of the Aqueous Solution ---' in line:
				grab_ele = True
			elif grab_ele and re.findall('^     [A-Z]', line):
				elements.append(grab_str(line, 0)) 
			elif '--- Numerical Composition of the Aqueous Solution ---' in line:				
				return elements


def determine_loaded_sp(path = ''):
	"""
	Use the verbose test.3o file run by the huffer to determine the loaded species 
	in:
		path = campaign huffer path where test.3o is located
	out:
		list of loaded sp
	"""
	loaded_sp = []
	with open('{}output'.format(path), 'r') as f:
		lines = f.readlines()
		grab_loaded_sp = False
		for _ in range(len(lines)):
			### search for loaded species. These only appear if verbose 'v' is set with local_3i.write() above
			if ' --- Listing of Species and Reactions ---' in lines[_]:
				grab_loaded_sp = True
			elif ' - - BEGIN ITERATIVE CALCULATIONS  - - - ' in lines[_]:
				break
			elif grab_loaded_sp and '------------------' in lines[_]:
				### the two options below avoid the 'BEGIN ITERATIVE . .'
				### which is also caught with the above string.
				if '1.000' in lines[_ + 2]:
					### exclude basis species
					### grab full string (with spaces) after the stochiometry
					### this correctly differentiates solid solution endmemebrs 
					### fromt their stand alone counterparts ie: 'CA-SAPONITE' 
					### vs 'CA-SAPONITE (SAPONITE)' 
					loaded_sp.append(lines[_ + 2].split('1.000  ')[-1].strip())
				elif 'is a strict' in lines[_ + 2]:
					### grabs basis species 
					loaded_sp.append(
						lines[_ + 2].split(' is a strict ')[0].strip())

		### O2(g) shows up as a strict basis species, and again with the gasses
		### so its basis form is removed here. Also, H2O shows up 2 times, and 
		### regardless is separately tracked via the aH2O variable.
		loaded_sp = [_ for _ in loaded_sp if _ != 'H2O' and _ != 'O2(g)']

		### alter loaded_sp to reflect correct search names required for 6o
		aq_and_s   = [_ for _ in loaded_sp if ' (' not in _]
		ss_and_gas = [_ for _ in loaded_sp if ' (' in _]
		gas        = [_.split(' (')[0] for _ in ss_and_gas if '(Gas)'     in _]
		ss         = [_.split(' (')[1].strip(')(') for _ in ss_and_gas if '(Gas)' not in _]

		sp_names = aq_and_s + gas + list(set(ss))

	return sp_names


def basis_to_ele_dict(slop_file):
	"""
	determin species-element relationships vis worm slop.csv.
	in:
		path = campaign huffer path where test.3o is located
	out:
		list of loaded sp
	"""
	df = pd.read_csv('/Users/tuckerely/NPP_dev/0_slop_OBIGT_Data0/{}'.format(file), index_col=0)
	basis_df = df[df['tag'] == 'basis']


def data0_suffix(T, P):
    
    """ 
    organizes the construction of multiple data0 files, each with a small t range, at constant pressure
    The family of data0s this function refers to, are built one at a time by graysons worm code, and then 
    stored appropriately in the the db folder. They are intended for spot calculations, and not sutiable
    for 6i runs which explore dT, as each only covers a small T range.

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
    ### by using 'floor' below. the correct file is returned for T near the file cutoffs
    ### for example, T = 7.99 (P=1), does in fact call the data0.002 file. The data0 files 
    ### themselves overlap in their lowest and highest values for consecutive files.
    t_char = char[math.floor(T/data0_system_T_interval)]                         
    tp_char = '{}{}'.format(t_char, dualchar[math.floor(P/data0_system_P_interval)])


    return tp_char


def data0_TP(suffix):
    """
    reutrn T/P rangte of a data0 file given its suffix
    """     
    t = suffix[0]
    p = suffix[1:]
    char = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    t_pos = char.index(t)
    t_rng = [t_pos*data0_system_T_interval, t_pos*data0_system_T_interval+7]
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.join([i, j]))

    p_pos = dualchar.index(p)
    p_val = p_pos*data0_system_P_interval
    
    return t_rng, p_val

def check_data0s_loaded():
	"""
	what data1 files are currently active in eq3_68.0a/db
	"""
	file_name, file_list = read_inputs('data1', 'EQ3_6v8.0a/db', str_loc = 'prefix')

	suf_list = [_[-3:] for _ in file_list if _.startswith('EQ3_6v8.0a/db/data1')]
	
	# for _ in suf_list

	plt.figure()
	plt.subplot(111)

	for _ in suf_list:
		t_rng, p_val = data0_TP(_)
		plt.plot(t_rng, [p_val, p_val], color = 'black', linewidth=0.1)

	plt.xlabel('T (˚C)')
	plt.ylabel('P (bars)')

	plt.title('data0 family coverage\n(∆P = descrete 0.5 bars)\n∆T = 7C contineuous')
	
	plt.show()




mw = {
    'O':    15.99940,
    'Ag':  107.86820,
    'Al':   26.98154,
    'Am':  243.00000,
    'Ar':   39.94800,
    'Au':  196.96654,
    'B':    10.81100,
    'Ba':  137.32700,
    'Be':    9.01218,
    'Bi':  208.98000,
    'Br':   79.90400,
    'Ca':   40.07800,
    'Cd':  112.41100,
    'Ce':  140.11500,
    'Cl':   35.45270,
    'Co':   58.93320,
    'Cr':   51.99610,
    'Cs':  132.90543,
    'Cu':   63.54600,
    'Dy':  162.50000,
    'Er':  167.26000,
    'Eu':  151.96500,
    'F':    18.99840,
    'Fe':   55.84700,
    'Fr':  223.00000,
    'Ga':   69.72300,
    'Gd':  157.25000,
    'H':     1.00794,
    'As':   74.92159,
    'C':    12.01100,
    'P':    30.97362,
    'He':    4.00206,
    'Hf':  178.49000,
    'Hg':  200.59000,
    'Ho':  164.93032,
    'I':   126.90447,
    'In':  114.82000,
    'K':    39.09830,
    'Kr':   83.80000,
    'La':  138.90550,
    'Li':    6.94100,
    'Lu':  174.96700,
    'Mg':   24.30500,
    'Mn':   54.93085,
    'Mo':   95.94000,
    'N':    14.00674,
    'Na':   22.98977,
    'Nb':   92.90600,
    'Nd':  144.24000,
    'Ne':   20.17970,
    'Ni':   58.69000,
    'Pb':  207.20000,
    'Pd':  106.42000,
    'Pm':  145.00000,
    'Pr':  140.90765,
    'Pt':  195.08000,
    'Ra':  226.02500,
    'Rb':   85.46780,
    'Re':  186.20700,
    'Rh':  102.90600,
    'Rn':  222.00000,
    'Ru':  101.07000,
    'S':    32.06600,
    'Sb':  127.76000,
    'Sc':   44.95591,
    'Se':   78.96000,
    'Si':   28.08550,
    'Sm':  150.36000,
    'Sn':  118.71000,
    'Sr':   87.62000,
    'Tb':  158.92534,
    'Tc':   98.00000,
    'Th':  232.03800,
    'Ti':   47.88000,
    'Tl':  204.38330,
    'Tm':  168.93421,
    'U':   238.02890,
    'V':    50.94150,
    'W':   183.85000,
    'Xe':  131.29000,
    'Y':    88.90585,
    'Yb':  173.04000,
    'Zn':   65.39000,
    'Zr':   91.22400
    }
