### This is a campaign file, which sets all conditions needed for the
### 3i/6i generated in the orders issued by Navigator.py, indcluding:
### (1)  campaign info 					(variables beginning with 'c_' )
### (2)  variable space limitations    	(variables beginning with 'v_' )
### (3)  3i settings    				(variables beginning with 'three_' )
### (4)  6i settings    				(variables beginning with 'six_' )
###
### This file, when loaded as a package by the various codes via
### $ import campaign
### $ import campaign.'name' as camp

from tool_room import *
import numpy as np
import os, itertools


name      = os.path.basename(__file__)[:-3].lower() 	#	campaign name is the file name
notes     = 'TEOS-10 (Milero et al., 2008 table 4 column "m_i". Missing alot of important species (SiO2, N, P, etc.)'
est_date  = '10Feb2021' 						#	established project date


### Establish target reactants. could be one or many. Can be any kind of reactant 
### that has an associated build function in the tool_room. Eventually i cna use this 
### for the carbonate work., exploring affinity changes
### [[jcode, rnt_name, morr, rk1b], . . . .]       jcode = 0 (mineral) 1 (SS) 2 Special reactant
### morr and rk1b can be fixed values, or a range, interpreted int he same way as the state abd basis variables.
target_rnt = {
			"CO2(g)" :['gas', [-7, -2], 1], 
			}

cb           = 'Cl-' 							#	charge balance on

suppress_min = False # Suppress all mineral precipitation 
min_supp_exemp = [] # Only used if supress_min is True

reso = 30 		#	resolution on brute force, only used with bf

# Fluid constraints (or not element constraints)
vs_state = {'P_bar'  : 10, 
			'fO2'    : -1,
			'T_cel'  : 10
			}

### HCO3      =  HCO3- + CO3-2 + CO2,AQ   =  0.0017803 + 0.0002477 + 0.0000100
### B(OH)3,AQ =  B(OH)3,AQ + B(OH)4- = 0.0003258 + 0.0001045
# These are elemental basis species that form constraints
vs_basis = {'H+'       : [-7, -9],
			# 'Na+'      : [np.log10(   0.4860597  *_) for _ in [0.1, 1.1]],
			'Na+'      : np.log10(0.4860597),
			# 'Mg+2'     : [np.log10(   0.0547421  *_) for _ in [0.1, 1.1]],
			'Mg+2'     : np.log10(0.0547421),
			'Ca+2'     : [np.log10(   0.0106568  *_) for _ in [0.1, 1.1]],
			# 'Ca+2'     : np.log10(   0.0106568 ),
			# 'K+'       : [np.log10(   0.0105797  *_) for _ in [0.1, 1.1]],
			'K+'       : np.log10(   0.0105797),
			# 'Sr+2'     : [np.log10(   0.0000940  *_) for _ in [0.1, 1.1]],
			# 'Cl-'      : [np.log10(   0.5657647  *_) for _ in [0.1, 1.1]],
			'Cl-'      : np.log10(   0.5657647 ),
			# 'SO4-2'    : [np.log10(   0.0292643  *_) for _ in [0.1, 1.1]],
			'SO4-2'    : np.log10(   0.0292643 ),

			# 'HCO3-'    : [np.log10(   0.0020380  *_) for _ in [0.1, 1.1]],
			'HCO3-'    : np.log10(   0.0020380 ),
			# 'Br-'      : [np.log10(   0.0008728  *_) for _ in [0.1, 1.1]],
			'Br-'      : np.log10(   0.0008728 ),
			# 'B(OH)3'   : [np.log10(   0.0004303  *_) for _ in [0.1, 1.1]],
			'B(OH)3'   : np.log10(   0.0004303 ),
			# 'F-'       : [np.log10(   0.0000708  *_) for _ in [0.1, 1.1]]
			'F-'       : np.log10(   0.0000708 )
			}
			
# Just create the templates to load into navigator and helms 
local_3i = three_i(cb)
local_6i = six_i(suppress_min = suppress_min, iopt4 = '1', min_supp_exemp=min_supp_exemp)